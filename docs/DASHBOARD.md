# Ghost Dashboard

The Ghost Dashboard is a web-based control panel for the Ghost daemon. It provides full visibility and control over every aspect of the system — configuration, models, skills, memory, cron jobs, identity, and live monitoring.

**URL:** [http://localhost:3333](http://localhost:3333) (default, configurable via `dashboard_port` in config)

## Modes

### Embedded Mode (Default)

When Ghost starts normally (`python ghost.py start`), the dashboard runs as a background thread in the same process. This gives it **direct access to the live daemon state** — real-time tool counts, skill lists, memory statistics, and instant config hot-reloading.

The status API returns `"embedded": true` and includes a `live` object with real-time counters.

### Standalone Mode

Running `python ghost.py dashboard` starts the dashboard as a standalone Flask server. It reads from config files and creates its own database connections. Useful for inspecting data when the daemon isn't running.

The status API returns `"embedded": false` with no `live` data.

## Pages

### Overview

Live dashboard showing daemon health and quick controls.

- **Status card** — Running/Paused/Stopped, PID, current model
- **Controls** — Pause/Resume, Reload Config (embedded only)
- **Counters** — Today's actions, total actions, uptime
- **Live stats** (embedded) — Tool count, skill count, memory entries, cron jobs
- **Feature toggles** — Click to enable/disable features in real-time
- **Type breakdown** — Bar chart of action types
- **Recent activity** — Last 5 feed entries

### Models

Browse and select from 300+ models fetched live from the OpenRouter API.

- **Current model** display + custom model input
- **API key** management (masked display, save new key)
- **Search** by model name, ID, or description
- **Filter** by provider (Google, Anthropic, OpenAI, Meta, etc.) and tier (Free, Fast, Standard, Premium)
- **Model cards** showing name, provider, context length, pricing per million tokens
- Click any card to switch models instantly

Models are cached for 5 minutes. Tier classification is based on pricing:
- **Free**: $0/M tokens or `:free` suffix
- **Fast**: < $0.50/M tokens
- **Standard**: $0.50 – $3.00/M tokens
- **Premium**: > $3.00/M tokens

### Configuration

Full control over every Ghost setting.

- **General settings** — poll_interval, min_length, rate_limit_seconds, max_input_chars, max_feed_items, tool_loop_max_steps
- **Feature toggles** — enable_tool_loop, enable_memory_db, enable_plugins, enable_skills, enable_system_tools, enable_browser_tools, enable_cron
- **Allowed commands** — Whitelist of shell commands the LLM can execute
- **Allowed roots** — Directory whitelist for file operations
- **Save / Reset to Defaults** buttons

Changes are saved to `~/.ghost/config.json` and hot-reloaded into the running daemon.

### Soul (SOUL.md)

Editor for the agent personality file.

- Full-text editor with syntax highlighting
- Character count
- Save and Reset to Default buttons
- Changes take effect on the daemon's next action (mtime-based cache)

### User Profile (USER.md)

Editor for the user profile file.

- **Quick Set** form for common fields (Name, "Call me", Pronouns, Timezone)
- Full-text editor for complete USER.md
- Save and Reset to Default buttons

### Skills

Browse, search, and manage all loaded skills.

- **Stats bar** — Total, Eligible, Disabled, Missing Requirements
- **Search** by skill name, description, or trigger keywords
- **Filter** — All / Eligible / Disabled / Missing Requirements
- **Grouped** by source (Bundled, User, Other)
- **Skill cards** showing:
  - Name, priority, description
  - Enable/disable toggle
  - Status badges (eligible, disabled, missing bins/env)
  - Trigger keywords
  - Required tools
  - Binary requirements with ✓/✗ status
  - Environment variable requirements with ✓/✗ status
- **Detail panel** — Click a skill to view/edit its full SKILL.md content

### Cron Jobs

Create and manage scheduled tasks.

- **Stats** — Total jobs, enabled count, next wake time
- **Create job** form:
  - Name, description
  - Schedule type: Every (interval), Cron (expression), At (one-shot)
  - Task type: AI Task (prompt), Notification, Shell command
  - Delete after run option
- **Job list** showing:
  - Enable/disable toggle
  - Schedule description (human-readable)
  - Next run / Last run times
  - Last status and errors
  - Run Now / Delete buttons

### Memory

Browse and search the persistent memory database.

- **Stats** — Total entries, total tokens, type breakdown
- **Search** — Full-text search across all memory entries
- **Recent** — Last 20 memory entries with delete buttons
- **Prune** — Remove old entries, keeping the N most recent

### Activity Feed

Live feed of Ghost's actions, auto-refreshing every 5 seconds.

- **Type filters** — Click type badges to filter
- **Entry cards** showing:
  - Type icon and badge
  - Skill name (if applicable)
  - Tools used count
  - Relative timestamp
  - Source preview
  - Result preview
  - Fix command (for errors)

### Logs

Full action history with filtering.

- **Type filter** dropdown
- **Limit** selector (20 / 50 / 100 / 500)
- **Table** with columns: Time, Type, Input, Output

---

## API Reference

All endpoints return JSON. The base URL is `http://localhost:3333`.

### Status

#### `GET /api/status`

Returns daemon status, stats, and platform info.

**Response:**
```json
{
  "running": true,
  "embedded": true,
  "paused": false,
  "pid": 12345,
  "platform": "Darwin",
  "uptime_seconds": 3600,
  "total_actions": 150,
  "today_actions": 42,
  "type_breakdown": {"code": 30, "url": 25, "error": 15, "long_text": 80},
  "model": "google/gemini-2.0-flash-001",
  "features": {
    "tool_loop": true,
    "memory": true,
    "skills": true,
    "plugins": true,
    "browser": true,
    "cron": true
  },
  "live": {
    "tools": 18,
    "tool_names": ["shell_exec", "file_read", "..."],
    "skills": 25,
    "memory_entries": 150,
    "cron_jobs": 3,
    "cron_enabled": 2
  },
  "soul_exists": true,
  "user_exists": true
}
```

The `live` field is only present in embedded mode. `uptime_seconds` is only present in embedded mode.

---

### Configuration

#### `GET /api/config`

Returns the current configuration and defaults.

**Response:**
```json
{
  "config": { "model": "...", "poll_interval": 0.5, "..." },
  "defaults": { "model": "google/gemini-2.0-flash-001", "..." }
}
```

#### `PUT /api/config`

Updates configuration keys. Merges with existing config, saves to disk, and hot-reloads into the running daemon.

**Request:**
```json
{
  "poll_interval": 1.0,
  "enable_skills": false
}
```

**Response:**
```json
{
  "ok": true,
  "config": { "..." }
}
```

---

### Models

#### `GET /api/models`

Fetches available models from the OpenRouter API (cached 5 minutes).

**Response:**
```json
{
  "current": "google/gemini-2.0-flash-001",
  "models": [
    {
      "id": "google/gemini-2.0-flash-001",
      "name": "Gemini 2.0 Flash",
      "provider": "Google",
      "tier": "fast",
      "context_length": 1048576,
      "modality": "text+image->text",
      "pricing": {
        "prompt_per_m": 0.10,
        "completion_per_m": 0.40
      },
      "description": "Fast and efficient model..."
    }
  ],
  "total": 337,
  "has_api_key": true,
  "api_key_masked": "sk-or-v1...abcd"
}
```

#### `PUT /api/models`

Sets the active model and/or API key.

**Request:**
```json
{
  "model": "anthropic/claude-3.5-sonnet",
  "api_key": "sk-or-v1-..."
}
```

Both fields are optional. If embedded, the model change takes effect immediately on the running daemon.

**Response:**
```json
{
  "ok": true,
  "model": "anthropic/claude-3.5-sonnet"
}
```

---

### Identity

#### `GET /api/soul`

**Response:**
```json
{
  "content": "# Ghost Soul\n\nYou are Ghost...",
  "path": "/Users/you/project/SOUL.md"
}
```

#### `PUT /api/soul`

**Request:** `{"content": "new soul content"}`
**Response:** `{"ok": true, "chars": 1500}`

#### `POST /api/soul/reset`

Resets SOUL.md to the default content.

**Response:** `{"ok": true, "content": "# Ghost Soul\n..."}`

#### `GET /api/user`

**Response:**
```json
{
  "content": "# About the User\n\n**Name:** Alice...",
  "path": "/Users/you/project/USER.md"
}
```

#### `PUT /api/user`

**Request:** `{"content": "new user content"}`
**Response:** `{"ok": true, "chars": 500}`

#### `POST /api/user/reset`

Resets USER.md to the default content (includes current OS).

**Response:** `{"ok": true, "content": "# About the User\n..."}`

---

### Skills

#### `GET /api/skills`

Lists all skills grouped by source with full status.

**Response:**
```json
{
  "groups": {
    "bundled": [
      {
        "name": "browser",
        "description": "Browser automation for web tasks",
        "triggers": ["browse", "website", "url"],
        "tools": ["browser"],
        "priority": 5,
        "os_filter": null,
        "path": "/path/to/skills/browser/SKILL.md",
        "source": "bundled",
        "disabled": false,
        "eligible": true,
        "os_ok": true,
        "requirements": {"bins": ["playwright"], "env": []},
        "missing": {"bins": [], "env": []}
      }
    ],
    "user": [],
    "other": []
  },
  "stats": {"total": 25, "eligible": 20, "disabled": 2, "missing_reqs": 3},
  "bundled_dir": "/path/to/skills",
  "user_dir": "/Users/you/.ghost/skills"
}
```

#### `GET /api/skills/<name>`

Returns full skill detail including file content.

**Response:** Same as list item, plus `"content": "---\nname: browser\n..."`.

#### `PUT /api/skills/<name>`

Update skill content and/or enabled state.

**Request:**
```json
{
  "content": "---\nname: my-skill\n...",
  "enabled": true
}
```

Both fields optional. Content writes to the SKILL.md file and triggers a skill reload. Enabled state updates `disabled_skills` in config.

**Response:** `{"ok": true}`

---

### Cron Jobs

#### `GET /api/cron/jobs`

**Response:**
```json
{
  "jobs": [
    {
      "id": "abc123",
      "name": "Daily Summary",
      "description": "Summarize the day's activity",
      "enabled": true,
      "deleteAfterRun": false,
      "schedule": {"kind": "cron", "expr": "0 18 * * *"},
      "schedule_human": "Every day at 6:00 PM",
      "payload": {"type": "task", "prompt": "Summarize today's actions"},
      "next_run": "2026-02-24 18:00:00",
      "last_run": "2026-02-23 18:00:00",
      "last_status": "ok",
      "last_error": null,
      "last_duration_ms": 1250,
      "consecutive_errors": 0
    }
  ]
}
```

#### `POST /api/cron/jobs`

Create a new cron job.

**Request:**
```json
{
  "name": "Health Check",
  "schedule_type": "every",
  "interval_seconds": 3600,
  "task_type": "task",
  "task": "Check system health and notify if issues",
  "description": "Hourly health check",
  "delete_after_run": false
}
```

Schedule types and their required fields:
- `"every"` → `interval_seconds` (number)
- `"cron"` → `cron_expr` (string, e.g. `"0 9 * * *"`)
- `"at"` → `run_at` (ISO datetime string)

Task types:
- `"task"` → Runs prompt through tool loop
- `"notify"` → Sends system notification
- `"shell"` → Executes shell command

**Response:** `{"ok": true, "job": {...}}` (status 201)

#### `PUT /api/cron/jobs/<job_id>`

Update a job. Send `{"enabled": false}` to disable, or other fields to update.

**Response:** `{"ok": true}`

#### `DELETE /api/cron/jobs/<job_id>`

**Response:** `{"ok": true}`

#### `POST /api/cron/jobs/<job_id>/run`

Trigger immediate execution.

**Response:** `{"ok": true, "message": "Job queued"}`

#### `GET /api/cron/status`

**Response:**
```json
{
  "running": true,
  "total_jobs": 3,
  "enabled_jobs": 2,
  "executing": [],
  "next_wake_ms": 1708765200000,
  "next_wake": "2026-02-24 18:00:00"
}
```

---

### Memory

#### `GET /api/memory/stats`

**Response:**
```json
{
  "total": 150,
  "total_tokens": 45000,
  "by_type": {"analysis": 50, "code": 30, "error": 20, "note": 10, "long_text": 40}
}
```

#### `GET /api/memory/search?q=<query>&limit=<n>`

Full-text search using FTS5. Default limit: 50.

**Response:**
```json
{
  "results": [
    {
      "id": 42,
      "timestamp": "2026-02-24T10:30:00",
      "type": "code",
      "content": "This function implements...",
      "source_preview": "def calculate_shipping...",
      "tags": "code-reviewer",
      "skill": "code-reviewer",
      "tools_used": "file_read,shell_exec",
      "rank": -2.5
    }
  ],
  "query": "shipping function"
}
```

#### `GET /api/memory/recent?limit=<n>`

Returns the most recent entries. Default limit: 20.

**Response:** `{"results": [...]}`

#### `DELETE /api/memory/<id>`

Delete a single memory entry.

**Response:** `{"ok": true}`

#### `POST /api/memory/prune`

Remove old entries, keeping the N most recent.

**Request:** `{"keep": 1000}`

**Response:** `{"ok": true, "stats": {"total": 1000, "..."}}`

---

### Activity Feed & Logs

#### `GET /api/feed`

Returns the activity feed (most recent first, up to 50 entries).

**Response:**
```json
{
  "entries": [
    {
      "time": "2026-02-24T10:30:00",
      "type": "code",
      "source": "def calculate_shipping(weight)...",
      "result": "This function calculates shipping cost...",
      "skill": "code-reviewer",
      "tools_used": ["file_read"],
      "fix_command": null
    }
  ]
}
```

#### `GET /api/logs?limit=<n>`

Returns action log entries (most recent first). Default limit: 100.

**Response:**
```json
{
  "entries": [
    {
      "time": "2026-02-24T10:30:00",
      "type": "code",
      "input": "def calculate_shipping...",
      "output": "This function calculates..."
    }
  ]
}
```

---

### Daemon Control

#### `POST /api/ghost/pause`

Pauses clipboard watching. The daemon continues running but skips processing.

**Response:** `{"ok": true, "paused": true}`

#### `POST /api/ghost/resume`

Resumes clipboard watching.

**Response:** `{"ok": true, "paused": false}`

#### `POST /api/ghost/reload`

Hot-reloads configuration into the running daemon (embedded mode only). Updates config, model references, and reloads skills.

**Response:**
```json
{
  "ok": true,
  "reloaded": true
}
```

In standalone mode: `{"ok": true, "reloaded": false, "note": "standalone mode"}`

---

## Frontend Architecture

The dashboard is a single-page application with no build step.

### Tech Stack
- **HTML**: Single `index.html` template with sidebar + content area
- **CSS**: Tailwind CSS (CDN) + custom `dashboard.css`
- **JS**: Vanilla ES modules, no framework

### Routing
Hash-based routing (`#overview`, `#models`, `#skills`, etc.). The `app.js` module maps hash segments to page modules and calls their `render(container)` function.

### Page Modules
Each page in `static/js/pages/` exports a single `async render(container)` function that:
1. Fetches data from the API
2. Generates HTML
3. Sets `container.innerHTML`
4. Binds event listeners

### Real-time Updates
- Sidebar status dot polls `GET /api/status` every 5 seconds
- Activity Feed page auto-refreshes every 5 seconds when active
