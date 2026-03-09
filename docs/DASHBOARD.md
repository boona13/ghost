# Ghost Dashboard

The Ghost Dashboard is a web-based control panel for the Ghost daemon. It provides full visibility and control over every aspect of the system — configuration, models, skills, memory, cron jobs, identity, messaging channels, autonomous growth, self-evolution, and live monitoring.

**URL:** [http://localhost:3333](http://localhost:3333) (default, configurable via `dashboard_port` in config)

## Modes

### Embedded Mode (Default)

When Ghost starts normally (`bash start.sh`), the dashboard runs as a background thread in the same process. This gives it **direct access to the live daemon state** — real-time tool counts, skill lists, memory statistics, and instant config hot-reloading.

The status API returns `"embedded": true` and includes a `live` object with real-time counters.

### Standalone Mode

Running `python ghost.py dashboard` starts the dashboard as a standalone Flask server. It reads from config files and creates its own database connections. Useful for inspecting data when the daemon isn't running.

The status API returns `"embedded": false` with no `live` data.

## Pages (28)

### Chat

Real-time messaging interface — the primary way users interact with Ghost.

- **Text messaging** with markdown rendering
- **File attachments** — drag-and-drop or click to attach files and images
- **Audio transcription** — record voice and transcribe via mic button
- **Voice Wake / Talk Mode** — toggle always-on voice from the mic button
- **Tool step streaming** — watch Ghost's tool calls execute in real-time
- **Inline evolution approvals** — approve/reject code changes without leaving chat
- **Canvas panel** — side panel showing rich HTML/CSS/JS visual output
- **Session management** — conversation history with session persistence

### Overview

Live dashboard showing daemon health and quick controls.

- **Status card** — Running/Paused/Stopped, PID, current model, uptime
- **Controls** — Pause/Resume, Reload Config (embedded only)
- **Counters** — Today's actions, total actions, uptime
- **Live stats** (embedded) — Tool count, skill count, memory entries, cron jobs
- **Feature toggles** — Click to enable/disable features in real-time
- **Type breakdown** — Bar chart of action types
- **Recent activity** — Last 5 feed entries
- **Platform info** — OS, Python version, Ghost version

### Models

Multi-provider LLM management with fallback chain visualization.

- **Provider cards** — Configure API keys/OAuth for each provider (OpenRouter, OpenAI, Codex, Anthropic, Gemini, xAI, Ollama)
- **Fallback chain** — Visual representation of the provider fallback order
- **Model browser** — Search 200+ models by name, filter by provider and tier
- **Model cards** — Name, provider, context length, pricing per million tokens
- **Connection testing** — Test each provider's connectivity
- Click any model card to switch instantly

### Skills

Browse, search, and manage all loaded skills plus the GhostHub public registry.

- **Local Skills tab:**
  - Stats bar — Total (42), Eligible, Disabled, Missing Requirements
  - Search by name, description, or trigger
  - Filter — All / Eligible / Disabled / Missing Requirements
  - Grouped by source (Bundled, User, Other)
  - Skill cards with enable/disable toggle, status badges, triggers, tools, requirements
  - Detail modal — view/edit SKILL.md content, set model override
- **GhostHub Registry tab:**
  - Search the public registry
  - Browse community skills with one-click install
  - Registry stats (skill count, tags, authors)

### Configuration

Full control over every Ghost setting with hot-reload.

- **General settings** — poll_interval, rate limits, tool_loop_max_steps, max_input_chars
- **Feature toggles** — tool_loop, memory, skills, browser, cron, evolve, growth, voice, canvas, integrations
- **Growth schedules** — Configure intervals for each autonomous routine
- **Voice controls** — Wake word, STT provider, TTS provider, voice sensitivity
- **Security** — Allowed commands, allowed roots
- **Save / Reset to Defaults**

### Soul (SOUL.md)

Editor for the agent personality file.

- Full-text editor with syntax highlighting
- Character count
- Save and Reset buttons
- Changes take effect on the daemon's next action

### User Profile (USER.md)

Editor for the user profile.

- **Quick Set** form for common fields (Name, "Call me", Pronouns, Timezone)
- Full-text editor for complete USER.md
- Save and Reset buttons

### Memory

Browse and search the persistent memory database.

- **Stats** — Total entries, total tokens, type breakdown
- **Search** — Full-text search across all memory entries
- **Recent** — Latest memory entries with delete buttons
- **Prune** — Remove old entries, keeping the N most recent
- **Semantic search** — Vector similarity search (when hybrid memory enabled)

### Activity Feed

Live feed of Ghost's actions, auto-refreshing every 5 seconds.

- Type filters — Click type badges to filter
- Entry cards with type icon, skill name, tools used, timestamp, source/result preview

### Console

Real-time SSE event stream showing everything Ghost does internally.

- **Category filters** — Filter by event type (tool calls, LLM, cron, evolve, etc.)
- **Search** — Full-text search across events
- **Pause/Resume** — Pause the stream while investigating
- **Export** — Download console output

### Cron Jobs

Create and manage scheduled tasks.

- **Stats** — Total jobs, enabled count, next wake time
- **Create job** form with schedule type (Every/Cron/At) and task type (AI Task/Notification/Shell)
- **Job list** — Enable/disable, schedule description, next/last run, status, Run Now / Delete

### Autonomy

Autonomous growth monitoring and action items.

- **Action items** — Things needing user attention (API keys, approvals, config changes)
- **Growth routines** — Status of each autonomous routine with last run, next run, errors
- **Growth log** — History of autonomous improvements
- **Crash reports** — Self-repair history

### Evolution

Self-modification history and controls.

- **Evolution history** — Every code change with diffs, status, timestamps
- **Approve/Reject** — Pending evolution changes
- **Rollback** — Revert specific changes
- **Branch viewer** — Current evolution branch state

### Future Features

Prioritized backlog for autonomous implementation.

- **Feature list** — Pending, in-progress, completed, failed features with priority (P0-P3)
- **Add feature** — Submit new features with priority and category
- **Approve/Reject** — Control which features Ghost implements
- **Stats** — Feature counts by status and category
- **Filters** — By status, priority, category, source

### Channels

Configure and manage messaging channels (Telegram, Discord, WhatsApp).

- **Channel cards** — Status, message counts, health indicators
- **Configure** — Per-channel settings, API keys, webhook URLs
- **Enable/Disable** — Toggle channels on/off
- **Test** — Send test messages
- **Onboarding wizards** — Step-by-step setup for each channel
- **Health monitoring** — Connection status, error rates, last message time

### Integrations

Third-party service configuration.

- **Google Workspace** — OAuth 2.0 flow for Gmail, Calendar, Drive, Docs, Sheets
- **Web search providers** — Configure Perplexity, Brave, etc.
- **Image generation** — Provider settings
- **Vision** — Provider configuration
- **TTS** — Provider and voice settings
- **Langfuse** — Observability configuration

### Security

AI-driven security auditing.

- **Run audit** — Trigger a security scan with real-time streaming output
- **Audit history** — Past scan results and findings
- **Auto-fix** — One-click remediation for common issues

### Setup

Multi-provider setup wizard.

- **Provider selection** — Choose which LLM providers to configure
- **API key entry** — Guided configuration for each provider
- **Connection testing** — Verify each provider works
- **Fallback chain** — Configure provider priority order
- **Setup Doctor** — Automated preflight checks and fixes

### Projects

Project management.

- **Project list** — Active projects with context
- **Create/Update** — Manage project definitions
- **Context switching** — Switch Ghost's active project context

### PRs

Internal pull request management.

- **PR list** — Evolution PRs with status
- **Review** — View diffs, comments, approve/reject
- **History** — Past PR decisions

### Nodes

GhostNode management.

- **Node list** — 23 AI capability nodes with status
- **GPU status** — VRAM usage, loaded models
- **Node details** — Configuration, health, usage stats

### Gallery (Media)

Media gallery for generated content.

- **Browse** — Generated images, audio, video
- **Search** — Find media by metadata
- **Manage** — Delete, organize generated content

### Doctor

Health diagnostics.

- **System checks** — API connectivity, disk space, dependencies
- **Repair** — Fix common issues
- **Recommendations** — Improvement suggestions

### Langfuse

Observability and tracing.

- **Trace viewer** — LLM call traces with token counts and latency
- **Configuration** — Langfuse connection settings

### Usage

Usage tracking and statistics.

- **Token usage** — Per-provider token consumption
- **Cost tracking** — Estimated costs per provider
- **Trends** — Usage over time

### Audit

Security and configuration audit log.

- **Event log** — All security-relevant events
- **Filters** — By event type, time range
- **Export** — Download audit data

### Browser Use

Extended browser automation interface.

- **Live browser** — View browser state
- **Action history** — Past browser interactions

---

## API Reference

All endpoints return JSON. The base URL is `http://localhost:3333`.

### Status

#### `GET /api/status`

Returns daemon status, stats, and platform info.

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
    "tool_loop": true, "memory": true, "skills": true,
    "plugins": true, "browser": true, "cron": true,
    "evolve": true, "growth": true, "voice": true,
    "canvas": true, "integrations": true
  },
  "live": {
    "tools": 60,
    "skills": 42,
    "memory_entries": 500,
    "cron_jobs": 12,
    "cron_enabled": 10
  }
}
```

---

### Chat

#### `POST /api/chat`

Send a message to Ghost via the dashboard chat.

**Request:**
```json
{
  "message": "What's the weather in NYC?",
  "session_id": "abc123",
  "attachments": []
}
```

**Response:** Server-sent events stream with tool calls, intermediate results, and final text response.

---

### Configuration

#### `GET /api/config`

Returns current configuration and defaults.

#### `PUT /api/config`

Updates configuration keys. Merges with existing, saves to disk, hot-reloads.

**Request:** `{"poll_interval": 1.0, "enable_skills": false}`

---

### Models

#### `GET /api/models`

Fetches available models from configured providers (cached 5 minutes).

#### `PUT /api/models`

Sets active model and/or API key. `{"model": "...", "api_key": "..."}`

---

### Identity

#### `GET /api/soul` / `PUT /api/soul` / `POST /api/soul/reset`

Read, update, or reset SOUL.md.

#### `GET /api/user` / `PUT /api/user` / `POST /api/user/reset`

Read, update, or reset USER.md.

---

### Skills

#### `GET /api/skills`

Lists all skills grouped by source with full status.

#### `GET /api/skills/<name>` / `PUT /api/skills/<name>`

Get or update a specific skill (content, enabled state, model override).

#### `GET /api/skills/model-options`

Available model aliases and providers for skill model override.

#### Registry Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/skills/registry/search?q=...` | GET | Search registry skills |
| `/api/skills/registry/<name>` | GET | Get a registry skill |
| `/api/skills/registry/<name>/install` | POST | Install a registry skill |
| `/api/skills/registry/stats` | GET | Registry statistics |
| `/api/skills/registry/refresh` | POST | Force refresh registry cache |

---

### Cron Jobs

#### `GET /api/cron/jobs` / `POST /api/cron/jobs`

List or create cron jobs.

#### `PUT /api/cron/jobs/<id>` / `DELETE /api/cron/jobs/<id>`

Update or delete a job.

#### `POST /api/cron/jobs/<id>/run`

Trigger immediate execution.

#### `GET /api/cron/status`

Scheduler status (running, job counts, next wake).

---

### Memory

#### `GET /api/memory/stats`
#### `GET /api/memory/search?q=<query>&limit=<n>`
#### `GET /api/memory/recent?limit=<n>`
#### `DELETE /api/memory/<id>`
#### `POST /api/memory/prune`

---

### Activity Feed & Logs

#### `GET /api/feed`
#### `GET /api/logs?limit=<n>`

---

### Daemon Control

#### `POST /api/ghost/pause` / `POST /api/ghost/resume`
#### `POST /api/ghost/reload`

---

### Evolution

#### `GET /api/evolve/history`
#### `POST /api/evolve/approve/<id>` / `POST /api/evolve/reject/<id>`
#### `POST /api/evolve/rollback/<id>`

---

### Future Features

#### `GET /api/future-features`
#### `POST /api/future-features`
#### `PUT /api/future-features/<id>`
#### `POST /api/future-features/<id>/approve` / `POST /api/future-features/<id>/reject`

---

### Channels

#### `GET /api/channels`
#### `GET /api/channels/<id>` / `PUT /api/channels/<id>`
#### `POST /api/channels/<id>/test`

---

### Autonomy

#### `GET /api/autonomy/status`
#### `GET /api/autonomy/action-items`
#### `GET /api/autonomy/growth-log`

---

### Webhooks

#### `GET /api/webhooks`
#### `POST /api/webhooks` / `DELETE /api/webhooks/<id>`
#### `POST /api/webhooks/<id>/test`

---

### Nodes

#### `GET /api/nodes`
#### `GET /api/nodes/<id>`
#### `GET /api/nodes/gpu-status`

---

### Security

#### `POST /api/security/audit`
#### `GET /api/security/audit/history`

---

### Other Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/console/stream` | SSE event stream |
| `GET /api/usage` | Token usage statistics |
| `GET /api/doctor` | Health diagnostics |
| `GET /api/projects` | Project list |
| `GET /api/media` | Media gallery |
| `GET /api/audit` | Audit log |
| `GET /api/langfuse` | Observability config |
| `GET /api/voice/status` | Voice mode status |

---

## Frontend Architecture

The dashboard is a single-page application with no build step.

### Tech Stack
- **HTML**: Single `index.html` template with sidebar + content area
- **CSS**: Tailwind CSS (CDN) + custom `dashboard.css` (dark theme)
- **JS**: Vanilla ES modules, no framework
- **i18n**: 4 languages (English, Arabic, Chinese, Brazilian Portuguese)

### Routing
Hash-based routing (`#chat`, `#overview`, `#models`, `#skills`, etc.). The `app.js` module maps hash segments to page modules and calls their `render(container)` function.

### Page Modules
Each page in `static/js/pages/` exports a single `async render(container)` function that:
1. Fetches data from the API
2. Generates HTML
3. Sets `container.innerHTML`
4. Binds event listeners

### Real-time Updates
- Sidebar status dot polls `GET /api/status` every 5 seconds
- Chat uses SSE for streaming responses
- Console page uses SSE for real-time events
- Activity Feed auto-refreshes every 5 seconds when active
