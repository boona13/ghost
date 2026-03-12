# Ghost Architecture

This document describes the internal architecture of the Ghost system — how the daemon works, how components connect, and how data flows through the system.

## System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                           GhostDaemon                                 │
│                                                                       │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐                    │
│  │  Dashboard  │  │  Channels  │  │  Cron Tasks  │                    │
│  │  Chat UI   │  │ (Telegram,  │  │  (scheduled  │                    │
│  │  (primary) │  │ Discord, WA)│  │   routines)  │                    │
│  └─────┬──────┘  └─────┬──────┘  └──────┬───────┘                    │
│        │               │                │                             │
│        └───────────────┼────────────────┘                             │
│                        ▼                                              │
│  ┌──────────────────────────────────────────────────────┐             │
│  │              Message Processing Pipeline              │             │
│  │  classify() → SkillLoader.match() → prompt builder   │             │
│  └──────────────────────┬───────────────────────────────┘             │
│                         │                                             │
│  ┌──────────────┐  ┌────▼──────────┐  ┌──────────────┐               │
│  │   Identity   │  │  System       │  │   Skills     │               │
│  │ (SOUL.md +   │──│  Prompt       │──│  (42 bundled │               │
│  │  USER.md)    │  │  Builder      │  │  + registry) │               │
│  └──────────────┘  └────┬──────────┘  └──────────────┘               │
│                         │                                             │
│  ┌──────────────────────▼───────────────────────────────┐             │
│  │              ToolLoopEngine                           │             │
│  │  LLM call ──▶ tool execution ──▶ LLM call            │             │
│  │  (multi-turn until text response or 200 max steps)   │             │
│  └──────────────────────┬───────────────────────────────┘             │
│                         │                                             │
│     ┌──────┬───────┬────┼────┬──────────┬──────────┐                  │
│     ▼      ▼       ▼    ▼    ▼          ▼          ▼                  │
│  Memory  Browser  Shell  Web   Vision  GhostNodes  Evolve             │
│  (4-layer)(Playwright)  Exec  Search  (5 providers)(23 nodes)(self-mod)│
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                │
│  │ CronService  │  │  Dashboard   │  │  Providers   │                │
│  │  (scheduler) │  │  :3333       │  │  (7 LLMs)    │                │
│  └──────────────┘  └──────────────┘  └──────────────┘                │
└───────────────────────────────────────────────────────────────────────┘
```

## Core Modules (77 Python files)

### `ghost.py` — Main Daemon

The central module. Contains:

- **`GhostDaemon`** — The main class that orchestrates everything.
- **`classify(text)`** — Content type classifier. Returns one of: `url`, `error`, `code`, `json`, `foreign`, `long_text`, or `skip`.
- **`SmartFilter`** — Prevents duplicate processing via content hashing and rate limiting.
- **`ContextMemory`** — Short-term rolling context for recent actions (not persisted).
- **CLI** — Argument parser and subcommands (`start`, `log`, `status`, `context`, `cron`, `soul`, `user`, `dashboard`).

#### Daemon Lifecycle

```
main()
  └─▶ GhostDaemon.__init__()
       ├── SmartFilter, ContextMemory
       ├── ToolLoopEngine + ToolRegistry
       ├── 60+ tools (system + browser + memory + cron + evolve + integrations + ...)
       ├── MemoryDB (SQLite + FTS5) + HybridMemory (vector embeddings)
       ├── HookRunner (plugin events)
       ├── SkillLoader (scans skills/ + ~/.ghost/skills/, 42 bundled)
       ├── PluginLoader
       ├── CronService (10+ autonomous routines)
       ├── Multi-provider LLM chain (7 providers)
       └── Channel gateway (Telegram, Discord, WhatsApp)
  └─▶ GhostDaemon.run()
       ├── Print banner, start cron, start dashboard thread
       ├── Write PID file, set signal handlers
       ├── Bootstrap growth routines
       └── Main loop:
            ├── Check for dashboard chat messages
            ├── Check for channel messages (WhatsApp, Telegram, etc.)
            ├── Check for panel actions
            └── Process via tool loop engine
```

#### Message Processing Pipeline

```
1. classify(text)               → url / error / code / json / foreign / long_text / skip
2. Hook: before_analyze         (plugins can modify text)
3. ContextMemory prefix         (recent actions for context)
4. SkillLoader.match()          (find matching skills, exclude disabled)
5. Build system prompt          (identity + base prompt + skill instructions)
6. URL fetch                    (if content_type == "url", fetch page content)
7. ToolLoopEngine.run()         (multi-turn LLM ↔ tool execution)
8. Hook: after_analyze          (plugins can modify result)
9. Stream to chat / channel     (real-time response delivery)
10. Append to feed + log        (feed.json, log.json)
11. Save to MemoryDB            (persistent SQLite storage)
```

### `ghost_loop.py` — Tool Loop Engine

The autonomous multi-turn execution engine.

**`ToolLoopEngine`** sends messages to the LLM with available tools. When the LLM returns tool calls instead of text, the engine executes them and feeds results back. This continues until:

- The LLM returns a text response (no tool calls), or
- `max_steps` is reached (default: 200), or
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

### `ghost_tools.py` — Built-in System Tools

Core tools registered by default:

| Tool | Description |
|---|---|
| `shell_exec` | Execute shell commands (sandboxed to allowed commands and roots) |
| `file_read` | Read file contents |
| `file_write` | Write or append to files |
| `file_search` | Search files by name or content |
| `web_fetch` | Fetch URL content (5-tier extraction pipeline) |
| `web_search` | Multi-provider web search (6 providers) |
| `clipboard_read` | Read current clipboard text |
| `clipboard_write` | Write text to clipboard |
| `notify` | Send system notification |
| `app_control` | Open/activate applications |
| `generate_image` | AI image generation |

Additional tool sets registered from other modules:

| Module | Tools |
|---|---|
| `ghost_browser.py` | `browser` (multi-action: navigate, snapshot, click, type, fill, etc.) |
| `ghost_memory.py` | `memory_search`, `memory_save` |
| `ghost_hybrid_memory.py` | `semantic_memory_search`, `semantic_memory_save` |
| `ghost_cron.py` | `cron_list`, `cron_add`, `cron_remove`, `cron_run`, `cron_status`, `cron_enable` |
| `ghost_evolve.py` | `evolve_plan`, `evolve_apply`, `evolve_test`, `evolve_deploy`, `evolve_rollback` |
| `ghost_future_features.py` | `add_future_feature`, `list_future_features`, `get_future_feature`, `approve_future_feature`, etc. |
| `ghost_integrations.py` | `google_gmail`, `google_calendar`, `google_drive`, `google_docs`, `google_sheets` |
| `ghost_credentials.py` | `credential_save`, `credential_get`, `credential_list`, `credential_delete` |
| `ghost_autonomy.py` | `add_action_item`, `log_growth_activity`, `repair_state` |
| `ghost_webhooks.py` | `webhook_create`, `webhook_list`, `webhook_delete`, `webhook_test` |
| `ghost_skill_registry.py` | `search_registry_skills`, `install_registry_skill`, `refresh_registry_cache` |
| `ghost_canvas.py` | `canvas` (create/update visual output panels) |
| `ghost_code_tools.py` | `code_analyze`, `code_metrics` |
| `ghost_x_tracker.py` | `x_check_action`, `x_log_action`, `x_action_history`, `x_action_stats` |
| `ghost_node_manager.py` | 20+ GhostNode tools (text_to_image_local, text_to_video, bark_speak, etc.) |
| `ghost_tool_builder.py` | `tools_create`, `tools_install_github`, `tools_list` |
| `ghost_voice.py` | Voice Wake + Talk Mode tools |

Total: **60+ tools** active simultaneously depending on configuration.

### `ghost_providers.py` — Multi-Provider LLM

7 LLM providers with automatic fallback:

| Provider | Access | Key Models |
|---|---|---|
| OpenRouter | 200+ models via single API key | Any model on the platform |
| OpenAI | Direct API | gpt-5.3-codex, gpt-4.1, o3 |
| OpenAI Codex | ChatGPT subscription via OAuth | No extra cost |
| Anthropic | Direct API | claude-opus-4-6, claude-sonnet-4-6 |
| Google Gemini | Direct API (free tier) | gemini-2.5-pro, gemini-2.5-flash |
| xAI | Direct API | grok-4, grok-3 |
| Ollama | Local models | llama3, mistral, etc. |

Features: jittered exponential backoff, 5-minute cooldown with periodic probing, automatic API format adaptation (OpenAI ↔ Anthropic Messages ↔ Codex Responses), OAuth auto-refresh.

### `ghost_browser.py` — Browser Automation

Playwright-based browser automation exposed as a single `browser` tool with action-based dispatch.

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

### `ghost_memory.py` — Persistent Memory

SQLite database with FTS5 full-text search at `~/.ghost/memory.db`.

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

**FTS5 virtual table** indexes `content`, `tags`, and `source_preview` for fast full-text search.

**Hybrid Memory** (`ghost_hybrid_memory.py`) adds vector embeddings (4 providers with fallback: OpenRouter, Gemini, Ollama, offline hash) with temporal decay and MMR reranking on top of FTS5.

**Vector Memory** (`ghost_vector_memory.py`) provides typed cosine similarity search across notes, facts, preferences, code, and insights.

**Session Memory** (`ghost_session_memory.py`) auto-saves conversation summaries with LLM-generated slugs.

### `ghost_evolve.py` — Self-Evolution Engine

Ghost can modify its own source code through a controlled pipeline:

```
evolve_plan → evolve_apply (1-5x) → evolve_test → evolve_deploy → restart
                                                    ↓ (if failure)
                                              evolve_rollback
```

Protected by: backup creation before changes, syntax + import + smoke testing, max evolutions per hour, protected files list, and supervisor auto-rollback after 5 consecutive crashes.

### `ghost_cron.py` — Cron Scheduler

Background scheduler for repeating and one-shot tasks.

| Kind | Format | Example |
|---|---|---|
| `every` | Interval in milliseconds | `{"kind": "every", "everyMs": 300000}` (every 5 min) |
| `cron` | Standard cron expression | `{"kind": "cron", "expr": "0 9 * * *"}` (daily at 9 AM) |
| `at` | One-shot at datetime | `{"kind": "at", "at": "2026-12-31T23:59:00"}` |

Payload types: `task` (runs through tool loop), `notify` (system notification), `shell` (command execution). Max 3 concurrent executions.

### `ghost_skills.py` — Skill System

42 bundled skills plus user-created and registry-installed skills.

**Discovery:**
1. Bundled: `<project>/skills/*/SKILL.md`
2. User: `~/.ghost/skills/*/SKILL.md`
3. Auto-reload every 30 seconds

**Matching:** When a message arrives, the `SkillLoader` checks each skill's trigger keywords against the text and content type. Matched skills are sorted by priority (highest first) and their body is injected into the system prompt.

See [SKILLS.md](SKILLS.md) for the full authoring guide.

### `ghost_node_manager.py` — GhostNodes

23 bundled AI capability nodes for local inference:

| Category | Nodes |
|---|---|
| Image | stable-diffusion, image-upscale, background-remove, image-inpaint, style-transfer, face-enhance |
| Video | video-gen, video-router, video-composer, image-to-video, kling-video, minimax-video, runway-video, runware-video |
| Audio | bark-tts, music-gen, sound-effects, whisper-stt, voice-clone, voice-fx |
| Vision | florence-vision, surya-ocr, depth-estimation |

Nodes are managed by the `NodeManager` with GPU-aware scheduling via `ghost_pipeline.py` for multi-step workflows.

### `ghost_channels/` — Messaging Channels

3 messaging platform integrations. Each channel gets: message queuing with WAL, exponential backoff retries, crash recovery, per-channel formatting, streaming, DM security policies, rate limiting, health monitoring, and onboarding wizards.

| Channel | Implementation |
|---|---|
| Telegram | Bot API with reactions, threading, streaming |
| Discord | Webhook + discord.py bot mode |
| WhatsApp | neonize QR + Business API webhook |

### `ghost_dashboard/` — Web Dashboard

Flask web application with 28 page modules and 31 API blueprints.

**Architecture:**
```
ghost_dashboard/
  __init__.py              App factory, get_daemon(), start/stop
  routes/                  31 API blueprint modules

    status.py, config.py, models.py, identity.py, skills.py,
    cron.py, memory.py, feed.py, daemon.py, evolve.py, chat.py,
    integrations.py, autonomy.py, setup.py, security.py,
    console.py, channels.py, future_features.py,
    voice.py, canvas.py, usage.py, webhooks.py, projects.py,
    prs.py, doctor.py, nodes.py,
    media.py, audit.py, tools.py
  templates/
    index.html             SPA shell (Tailwind CDN)
  static/
    css/dashboard.css      Custom dark theme
    js/
      api.js, utils.js     HTTP client, utilities
      app.js               Hash-based router, sidebar polling
      i18n/                Internationalization (en, ar, zh-CN, pt-BR)
      pages/               28 page modules
```

See [DASHBOARD.md](DASHBOARD.md) for the full page and API reference.

## Module Map

### Core Infrastructure
| Module | Purpose |
|---|---|
| `ghost.py` | Main daemon, action handling, GhostDaemon class |
| `ghost_loop.py` | ToolLoopEngine: multi-turn LLM + tool execution |
| `ghost_tools.py` | System tools: shell_exec, file_read, file_write, web_fetch, etc. |
| `ghost_cron.py` | CronService: scheduled job execution |
| `ghost_plugins.py` | PluginLoader + HookRunner |
| `ghost_hook_debug.py` | Hook debug event store with redaction and replay |
| `ghost_supervisor.py` | Process supervisor for safe restarts (OFF-LIMITS) |

### Self-Evolution
| Module | Purpose |
|---|---|
| `ghost_evolve.py` | EvolutionEngine: backup, validate, test, deploy, rollback |
| `ghost_autonomy.py` | Autonomous growth engine, action items, self-repair |
| `ghost_future_features.py` | Prioritized feature queue for serial evolution |
| `ghost_model_dispatch.py` | Budget-aware coding model selection for evolution & bug hunting |
| `ghost_state_repair.py` | State file validation and repair |

### Memory
| Module | Purpose |
|---|---|
| `ghost_memory.py` | MemoryDB: SQLite + FTS5 persistent memory |
| `ghost_hybrid_memory.py` | Semantic memory with vector embeddings |
| `ghost_vector_memory.py` | Vector store for semantic search |
| `ghost_session_memory.py` | Per-session memory isolation |

### LLM Providers
| Module | Purpose |
|---|---|
| `ghost_providers.py` | Multi-provider LLM registry + API format adapters |
| `ghost_auth_profiles.py` | Auth profile store (API keys + OAuth tokens) |
| `ghost_oauth.py` | OpenAI Codex OAuth PKCE flow |
| `ghost_llm_task.py` | Structured LLM subtasks with JSON output |
| `ghost_interrupt.py` | Generation interrupt and injection |
| `ghost_reasoning.py` | Reasoning mode directives and prompt shaping |

### Browser & Web
| Module | Purpose |
|---|---|
| `ghost_browser.py` | Browser automation (Playwright) |
| `ghost_browser_use.py` | Extended browser-use integration |
| `ghost_web_fetch.py` | Web content extraction (5-tier pipeline) |
| `ghost_web_search.py` | Multi-provider web search |

### Voice & Vision & Media
| Module | Purpose |
|---|---|
| `ghost_voice.py` | Voice Wake + Talk Mode, STT integration |
| `ghost_tts.py` | Text-to-speech (Edge, OpenAI, ElevenLabs) |
| `ghost_vision.py` | Image analysis (5 providers) |
| `ghost_image_gen.py` | Image generation |
| `ghost_canvas.py` | Visual output panel for HTML/CSS/JS |
| `ghost_media_store.py` | Media gallery storage and indexing |

### Skills & Projects
| Module | Purpose |
|---|---|
| `ghost_skills.py` | SkillLoader: discover and match skills |
| `ghost_skill_manager.py` | Managed skill installation with validation |
| `ghost_skill_registry.py` | GhostHub: public skill registry client |
| `ghost_projects.py` | Project management |

### GhostNodes
| Module | Purpose |
|---|---|
| `ghost_node_manager.py` | Node lifecycle and execution management |
| `ghost_node_registry.py` | Node discovery and metadata registry |
| `ghost_node_sdk.py` | Node development SDK |
| `ghost_pipeline.py` | Multi-step AI pipeline orchestration |
| `ghost_nodes/` | 23 bundled AI capability nodes |

### Integrations & Channels
| Module | Purpose |
|---|---|
| `ghost_integrations.py` | Google Workspace + third-party integrations |
| `ghost_channels/` | 3 messaging channel implementations |
| `ghost_webhooks.py` | Webhook triggers for event-driven automation |
| `ghost_mcp.py` | MCP client for external tool servers |

### Security
| Module | Purpose |
|---|---|
| `ghost_security_audit.py` | AI-driven security auditing |
| `ghost_tool_intent_security.py` | Tool intent signing and verification |
| `ghost_api_key_posture.py` | API key risk analysis |
| `ghost_secret_refs.py` | Secret reference management |
| `ghost_credentials.py` | Secure credential storage |
| `ghost_audit_log.py` | Security audit event logging |

### Code Intelligence
| Module | Purpose |
|---|---|
| `ghost_code_tools.py` | Code analysis and repository tools |
| `ghost_code_intel.py` | Code intelligence and indexing |
| `ghost_tool_builder.py` | ToolManager for ghost_tools/ directory |

### Diagnostics & Setup
| Module | Purpose |
|---|---|
| `ghost_doctor.py` | Health diagnostics and repair |
| `ghost_setup_doctor.py` | Setup wizard and onboarding |
| `ghost_setup_providers.py` | Provider configuration wizard |
| `ghost_config_tool.py` | Configuration management |

### Utilities
| Module | Purpose |
|---|---|
| `ghost_data_extract.py` | Smart data extraction (emails, phones, URLs) |
| `ghost_platform.py` | Cross-platform OS utility helpers |
| `ghost_shell_sessions.py` | Persistent shell session management |
| `ghost_console.py` | Console logging and SSE event bus |
| `ghost_usage.py` | Usage tracking and statistics |
| `ghost_uptime.py` | Uptime monitoring |
| `ghost_query_expansion.py` | Query expansion for search quality |
| `ghost_subagents.py` | Subagent task delegation |
| `ghost_resource_manager.py` | Runtime resource tracking |
| `ghost_git.py` | Git helper operations |
| `ghost_pr.py` | Internal PR review workflow |
| `ghost_session_export.py` | Session export and archiving |
| `ghost_community_hub.py` | Community Hub client |
| `ghost_x_tracker.py` | X/Twitter interaction tracking |

## Data Flow

### User Message → Response

```
User sends message (dashboard chat / channel / voice)
  → classify(): determine content type
  → SkillLoader.match(): find relevant skills
  → Build system prompt: identity + base + skills
  → ToolLoopEngine: LLM call(s) + tool execution(s)
  → Result: streamed text response
  → Chat / channel delivery
  → Feed entry + log entry
  → MemoryDB save (SQLite)
```

### Dashboard → Daemon

```
User clicks in dashboard
  → Frontend JS: api.put('/api/config', {model: "..."})
  → Flask route: update config.json
  → _notify_daemon(): daemon.cfg.update(fresh)
  → daemon.llm.model = new_model (live update)
  → Next task uses new model
```

### Cron → Action

```
Timer fires for due job
  → CronService._execute_job(job)
  → _cron_fire():
      → If coding job (feature_implementer, bug_hunter):
          → If budget == "free": skip (self-evolution disabled)
          → Else: ModelDispatcher.select("coding") → model_override
      → if payload.type == "task":
          → ToolLoopEngine.run(prompt=payload.prompt, model_override=coding_model)
      → if payload.type == "notify":
          → System notification
      → if payload.type == "shell":
          → subprocess.run(command)
  → Update job state, compute next run time
```

## Threading Model

Ghost runs in a single process with multiple threads:

| Thread | Purpose |
|---|---|
| Main thread | Event loop (chat messages, channel messages, panel actions) |
| Processing threads | `process_text()` in `threading.Thread(daemon=True)` |
| Dashboard thread | Flask server (`make_server(...).serve_forever()`, daemon thread) |
| Cron timer thread | `threading.Timer` for scheduled wake-ups |
| Cron execution threads | Job execution (max 3 concurrent, daemon threads) |
| Channel threads | Per-channel message polling/receiving |
| Voice thread | Wake word detection + audio capture |

All daemon threads are marked `daemon=True`, so they die when the main thread exits.

## File Layout

```
~/.ghost/                        Persistent data directory
  config.json                    User configuration
  auth_profiles.json             Provider credentials
  log.json                       Action history (last 500 entries)
  feed.json                      Activity feed (last 50 entries)
  ghost.pid                      Running daemon PID
  memory.db                      SQLite memory database
  coding_benchmarks.json         SWE-bench scores for coding model selection
  model_dispatch_cache.json      Cached coding model selection (24h TTL)
  cron/jobs.json                 Cron job definitions
  future_features.json           Evolution backlog
  action_items.json              User action items
  growth_log.json                Autonomous growth history
  integrations.json              Google OAuth tokens
  channels.json                  Channel configurations
  evolve/backups/                Project backups before self-modifications
  audio/                         Generated TTS audio files
  voice/                         Voice capture and STT models
  canvas/                        Canvas session files
  generated_images/              AI-generated images
  memory/sessions/               Session summaries
  skill_registry/                GhostHub registry cache
  skills/                        User-created + registry-installed skills
  plugins/                       User plugins
  screenshots/                   Captured screenshots
  state_backups/                 State file backups from repair

<project>/                       Project directory
  ghost.py                       Main daemon (77 Python modules in root)
  ghost_loop.py                  Tool loop engine + registry
  ghost_tools.py                 Built-in tool definitions
  ghost_browser.py               Browser automation
  ghost_memory.py                Memory database
  ghost_skills.py                Skill loader
  ghost_cron.py                  Cron scheduler
  ghost_evolve.py                Evolution engine
  ghost_providers.py             Multi-provider LLM
  ghost_channels/                3 messaging channels (Telegram, Discord, WhatsApp)
  ghost_nodes/                   23 AI capability nodes
  ghost_dashboard/               Web dashboard (Flask, 31 blueprints, 28 pages)
  skills/                        Bundled skills (42)
  SOUL.md                        Agent personality
  USER.md                        User profile
```
