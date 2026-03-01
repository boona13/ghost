# Ghost Architecture

This document describes the internal architecture of the Ghost system — how the daemon works, how components connect, and how data flows through the system.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        GhostDaemon                              │
│                                                                 │
│  ┌──────────┐   ┌────────────┐   ┌──────────────┐              │
│  │ Clipboard │──▶│ SmartFilter│──▶│  classify()  │              │
│  │  Watcher  │   │  (dedup +  │   │  (content    │              │
│  │           │   │  rate-limit)│  │   type)      │              │
│  └──────────┘   └────────────┘   └──────┬───────┘              │
│                                          │                      │
│  ┌──────────┐                   ┌────────▼────────┐             │
│  │Screenshot│──────────────────▶│ process_text()  │             │
│  │ Watcher  │                   │ process_image() │             │
│  └──────────┘                   └────────┬────────┘             │
│                                          │                      │
│          ┌───────────────────────────────┼──────────────┐       │
│          │                               │              │       │
│  ┌───────▼──────┐  ┌────────────┐  ┌────▼─────┐        │       │
│  │ SkillLoader  │  │  Identity   │  │ Hooks    │        │       │
│  │  (match +    │  │ (SOUL.md + │  │ (plugin  │        │       │
│  │   inject)    │  │  USER.md)  │  │  events) │        │       │
│  └───────┬──────┘  └─────┬──────┘  └──────────┘        │       │
│          │               │                              │       │
│  ┌───────▼───────────────▼──────────────────────┐       │       │
│  │              System Prompt Builder            │       │       │
│  │  identity + base prompt + matched skills     │       │       │
│  └──────────────────┬───────────────────────────┘       │       │
│                     │                                   │       │
│  ┌──────────────────▼───────────────────────────┐       │       │
│  │            ToolLoopEngine                     │       │       │
│  │  LLM call ──▶ tool execution ──▶ LLM call    │       │       │
│  │  (multi-turn until text response or max)     │       │       │
│  └──────────────────┬───────────────────────────┘       │       │
│                     │                                   │       │
│  ┌─────────┬────────┼─────────┬──────────┐              │       │
│  │         │        │         │          │              │       │
│  ▼         ▼        ▼         ▼          ▼              │       │
│ Feed    MemoryDB  Terminal  Panel    Context             │       │
│ (.json) (SQLite)  (stdout)  (native) Memory             │       │
│                                                         │       │
│  ┌──────────────┐  ┌──────────────┐                     │       │
│  │ CronService  │  │  Dashboard   │◀── Flask (bg thread)│       │
│  │  (scheduler) │  │  :3333       │                     │       │
│  └──────────────┘  └──────────────┘                     │       │
└─────────────────────────────────────────────────────────────────┘
```

## Core Modules

### `ghost.py` — Main Daemon

The central module. Contains:

- **`GhostDaemon`** — The main class that orchestrates everything.
- **`classify(text)`** — Content type classifier. Returns one of: `url`, `error`, `code`, `json`, `foreign`, `long_text`, or `skip`.
- **`SmartFilter`** — Prevents duplicate processing via content hashing and rate limiting.
- **`LLMClient`** — Single-shot OpenRouter API client (legacy fallback).
- **`ContextMemory`** — Short-term rolling context for recent actions (not persisted).
- **CLI** — Argument parser and subcommands (`start`, `log`, `status`, `context`, `cron`, `soul`, `user`, `dashboard`).

#### Daemon Lifecycle

```
main()
  └─▶ GhostDaemon.__init__()
       ├── SmartFilter, ContextMemory
       ├── LLMClient (legacy), ToolLoopEngine
       ├── ToolRegistry + built-in tools (9 system + browser + cron)
       ├── MemoryDB (SQLite + FTS5)
       ├── HookRunner
       ├── SkillLoader (scans skills/ + ~/.ghost/skills/)
       ├── PluginLoader
       └── CronService
  └─▶ GhostDaemon.run()
       ├── Print banner, start cron, start dashboard thread
       ├── Write PID file, set signal handlers
       └── Main loop:
            ├── Check PAUSE_FILE → skip if paused
            ├── Check Desktop for new screenshots → process_image()
            ├── Check clipboard for images (every 6 ticks) → process_image()
            ├── Check OWN_COPY flag → skip own copies
            ├── Check clipboard text → SmartFilter → process_text()
            └── Check for panel actions → check_actions()
```

#### Text Processing Pipeline (`process_text`)

```
1. Hook: on_classify            (plugins can override content type)
2. classify(text)               → url / error / code / json / foreign / long_text / skip
3. Hook: before_analyze         (plugins can modify text)
4. ContextMemory prefix         (recent actions for context)
5. SkillLoader.match()          (find matching skills, exclude disabled)
6. Build system prompt          (identity + base prompt + skill instructions)
7. URL fetch                    (if content_type == "url", fetch page content)
8. ToolLoopEngine.run()         (multi-turn LLM ↔ tool execution)
   OR LLMClient.analyze()      (single-shot fallback if tools disabled)
9. Hook: after_analyze          (plugins can modify result)
10. Terminal output             (pretty-printed to stdout)
11. Extract fix command         (for errors, copy fix to clipboard)
12. Hook: on_feed_append        (plugins can modify feed entry)
13. Append to feed + log        (feed.json, log.json)
14. Save to MemoryDB            (persistent SQLite storage)
15. Increment actions_today
```

#### Image Processing Pipeline (`process_image`)

```
1. Hook: on_screenshot
2. ContextMemory prefix
3. SkillLoader.match("image screenshot", "image")
4. Build system prompt (identity + image prompt + skills)
5. Read image as base64
6. ToolLoopEngine.run() with image
   OR LLMClient.analyze_image() (fallback)
7. Terminal output
8. Append to feed + log
9. Save to MemoryDB
```

### `ghost_loop.py` — Tool Loop Engine

The autonomous multi-turn execution engine.

**`ToolLoopEngine`** sends messages to the LLM with available tools. When the LLM returns tool calls instead of text, the engine executes them and feeds results back. This continues until:

- The LLM returns a text response (no tool calls), or
- `max_steps` is reached (default: 20), or
- The `LoopDetector` identifies repetitive patterns and injects a break.

```
Step 1: LLM call (system prompt + user message + tools schema)
  ├── LLM returns text → done, return result
  └── LLM returns tool_calls →
       ├── Execute each tool via ToolRegistry
       ├── Append tool results to conversation
       └── Step 2: LLM call again → repeat
```

**`ToolRegistry`** stores tool definitions and executes them. Each tool has:
- `name` — Unique identifier
- `description` — For the LLM to understand the tool
- `parameters` — JSON Schema of accepted arguments
- `execute` — Python callable that runs the tool

**`ToolLoopResult`** returned after loop completion:
- `text` — Final text response
- `tool_calls` — List of all tool calls made
- `total_tokens` — Token usage across all turns
- `steps` — Number of loop iterations

### `ghost_tools.py` — Built-in Tools

Nine system tools registered by default:

| Tool | Description |
|---|---|
| `shell_exec` | Execute shell commands (sandboxed to allowed commands and roots) |
| `file_read` | Read file contents |
| `file_write` | Write or append to files |
| `file_search` | Search files by name or content |
| `web_fetch` | Fetch URL content |
| `clipboard_read` | Read current clipboard text |
| `clipboard_write` | Write text to clipboard |
| `notify` | Send macOS notification |
| `app_control` | Open/activate macOS applications |

Additional tool sets:
- **Browser tools** (`ghost_browser.py`): `browser` — a single multi-action tool with subcommands for navigation, inspection, and interaction.
- **Memory tools** (`ghost_memory.py`): `memory_search`, `memory_save` — registered when memory is enabled.
- **Cron tools** (`ghost_cron.py`): `cron_list`, `cron_add`, `cron_remove`, `cron_run`, `cron_status`, `cron_enable` — registered when cron is enabled.

Total: up to **18 tools** active simultaneously.

### `ghost_browser.py` — Browser Automation

Playwright-based browser automation exposed as a single `browser` tool with action-based dispatch.

**Actions:**

| Category | Actions |
|---|---|
| Navigation | `navigate`, `new_tab`, `close_tab`, `tabs` |
| Inspection | `snapshot` (accessibility tree), `content` (page text), `console` |
| Interaction | `click`, `type`, `fill`, `press`, `scroll`, `hover`, `select` |
| Advanced | `evaluate` (run JS), `screenshot`, `pdf`, `wait`, `stop` |

**Accessibility Snapshot** is central to how the LLM interacts with pages:
1. `snapshot()` returns an accessibility tree with element refs (`e0`, `e1`, `e2`...)
2. The LLM reads the tree, identifies the element it wants
3. `click(ref="e5")` or `type(ref="e5", text="hello")` targets that element
4. After page changes, `snapshot()` is called again

Security: SSRF guard blocks localhost/private IPs; external page content is wrapped with boundary markers to prevent prompt injection.

### `ghost_memory.py` — Persistent Memory

SQLite database with FTS5 full-text search at `~/.ghost/memory.db`.

**Schema:**

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-increment ID |
| `timestamp` | TEXT | ISO timestamp |
| `type` | TEXT | Content type (analysis, code, error, note, etc.) |
| `source_hash` | TEXT | MD5 hash for deduplication |
| `content` | TEXT | The LLM's response (up to 10,000 chars) |
| `source_preview` | TEXT | Truncated source input |
| `tags` | TEXT | Tags / skill name |
| `skill` | TEXT | Skill that handled it |
| `tools_used` | TEXT | Comma-separated tool names |
| `tokens_used` | INTEGER | Token count |

**FTS5 virtual table** indexes `content`, `tags`, and `source_preview` for fast full-text search with ranked results. Falls back to `LIKE` search if FTS5 fails.

**Automatic maintenance:**
- Auto-prune to 5,000 entries on daemon shutdown
- Dashboard provides manual prune control

### `ghost_cron.py` — Cron Scheduler

Background scheduler for repeating and one-shot tasks.

**Three schedule types:**

| Kind | Format | Example |
|---|---|---|
| `every` | Interval in milliseconds | `{"kind": "every", "everyMs": 300000}` (every 5 min) |
| `cron` | Standard cron expression | `{"kind": "cron", "expr": "0 9 * * *"}` (daily at 9 AM) |
| `at` | One-shot at datetime | `{"kind": "at", "at": "2026-12-31T23:59:00"}` |

**Three payload types:**

| Type | Description |
|---|---|
| `task` | Runs a prompt through the tool loop engine |
| `notify` | Sends a system notification |
| `shell` | Executes a shell command |

**Execution model:**
- Timer-based: wakes at the next earliest job, sleeps between
- Max 3 concurrent job executions
- Error backoff with `consecutiveErrors` tracking
- Atomic file persistence at `~/.ghost/cron/jobs.json`
- Thread-safe with locking

### `ghost_skills.py` — Skill System

Skills are markdown files that inject domain-specific instructions into the LLM's system prompt when their triggers match clipboard content.

**Discovery:**
1. Bundled: `<project>/skills/*/SKILL.md`
2. User: `~/.ghost/skills/*/SKILL.md`
3. Auto-reload every 30 seconds

**Matching:** When text is copied, the `SkillLoader` checks each skill's trigger keywords against the text and content type. Matched skills are sorted by priority (highest first) and their body is injected into the system prompt.

**Skill filtering:** Skills can require specific binaries or environment variables. The dashboard shows requirement status and allows enabling/disabling skills.

See [SKILLS.md](SKILLS.md) for the full authoring guide.

### `ghost_dashboard/` — Web Dashboard

Flask web application that runs as a background thread inside the daemon (or standalone).

**Two modes:**
- **Embedded** — Started by `GhostDaemon.run()`, shares the same process, reads live daemon state (tools, skills, memory, cron) directly from memory.
- **Standalone** — Started by `python ghost.py dashboard`, reads from config files and creates its own connections to SQLite/cron.

**Architecture:**
```
ghost_dashboard/
  __init__.py          App factory, get_daemon(), start/stop
  routes/
    __init__.py        Blueprint registration
    status.py          GET /api/status (live daemon state)
    config.py          GET/PUT /api/config (hot-reload)
    models.py          GET/PUT /api/models (OpenRouter API)
    identity.py        GET/PUT /api/soul, /api/user
    skills.py          GET/PUT /api/skills (live loader)
    cron.py            CRUD /api/cron/jobs (live scheduler)
    memory.py          GET/DELETE /api/memory/* (live DB)
    feed.py            GET /api/feed, /api/logs
    daemon.py          POST /api/ghost/pause|resume|reload
  templates/
    index.html         SPA shell (Tailwind CDN)
  static/
    css/dashboard.css  Custom dark theme styles
    js/
      api.js           HTTP client (get/put/post/del)
      utils.js         Toast, escapeHtml, timeAgo
      app.js           Hash-based router, sidebar polling
      pages/           One module per page (10 total)
```

See [DASHBOARD.md](DASHBOARD.md) for the full API reference.

## Data Flow

### Clipboard → Response

```
User copies text
  → Clipboard watcher detects change (every 0.5s)
  → SmartFilter: hash dedup + rate limit + min length
  → classify(): determine content type
  → SkillLoader.match(): find relevant skills
  → Build system prompt: identity + base + skills
  → ToolLoopEngine: LLM call(s) + tool execution(s)
  → Result: text response from LLM
  → Terminal output + panel update
  → Feed entry (feed.json) + log entry (log.json)
  → MemoryDB save (SQLite)
```

### Dashboard → Daemon

```
User clicks in dashboard
  → Frontend JS: api.put('/api/config', {model: "..."})
  → Flask route: update config.json
  → _notify_daemon(): daemon.cfg.update(fresh)
  → daemon.llm.model = new_model (live update)
  → Next clipboard event uses new model
```

### Cron → Action

```
Timer fires for due job
  → CronService._execute_job(job)
  → if payload.type == "task":
      → ToolLoopEngine.run(prompt=payload.prompt)
  → if payload.type == "notify":
      → System notification
  → if payload.type == "shell":
      → subprocess.run(command)
  → Update job state (lastRunAtMs, nextRunAtMs, status)
  → Compute next run time
```

## Threading Model

Ghost runs in a single process with multiple threads:

| Thread | Purpose |
|---|---|
| Main thread | Clipboard polling loop (`while self.running`) |
| Processing threads | `process_text()` / `process_image()` in `threading.Thread(daemon=True)` |
| Dashboard thread | Flask server (`make_server(...).serve_forever()`, daemon thread) |
| Cron timer thread | `threading.Timer` for scheduled wake-ups |
| Cron execution threads | Job execution (max 3 concurrent, daemon threads) |

All daemon threads are marked `daemon=True`, so they die when the main thread exits.

## File Layout

```
~/.ghost/                      Persistent data directory
  config.json                  User configuration
  log.json                     Action history (last 500 entries)
  feed.json                    Activity feed (last 50 entries)
  ghost.pid                    Running daemon PID
  memory.db                    SQLite memory database
  paused                       Pause flag file (presence = paused)
  own_copy                     Flag to skip own clipboard writes
  action.json                  Panel-to-daemon communication
  screenshots/                 Processed screenshot storage
  cron/
    jobs.json                  Cron job definitions
  skills/                      User-created skills
  plugins/                     User plugins

<project>/                     Project directory
  ghost.py                     Main daemon
  ghost_loop.py                Tool loop engine + registry
  ghost_tools.py               Built-in tool definitions
  ghost_browser.py             Browser automation
  ghost_memory.py              Memory database
  ghost_skills.py              Skill loader
  ghost_cron.py                Cron scheduler
  ghost_dashboard/             Web dashboard (Flask)
  skills/                      Bundled skills (25)
  SOUL.md                      Agent personality
  USER.md                      User profile
```
