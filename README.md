# Ghost

**Self-evolving AI agent** — runs locally, improves itself, gets things done while you sleep.

Ghost is an autonomous AI agent that runs on your machine. It modifies its own source code, fixes its own bugs, and grows new capabilities on a schedule — without you lifting a finger. Talk to it through a web dashboard or reach it on WhatsApp, Telegram, Discord, Slack, iMessage, and 15+ other channels. Give it a task and watch it execute with real tools: browser automation, shell commands, web research, file management, Google Workspace, and more.

> **Ghost is not a chatbot. It's a system that runs 24/7 and gets better every day.**

## Why Ghost

Most AI assistants wait for you to type something. Ghost doesn't.

- **Self-evolution** — Ghost modifies its own codebase, tests the changes, deploys, and rolls back if anything breaks. No human intervention needed.
- **Self-healing** — If Ghost crashes, it reads the crash report, diagnoses the cause, and fixes itself on restart.
- **Autonomous growth** — 10+ scheduled routines proactively improve Ghost: scouting AI news, hunting bugs, improving skills, running security audits, and patching itself — all on cron.
- **Multi-channel** — Talk to Ghost on WhatsApp, Telegram, Slack, Discord, iMessage, Signal, email, and more. Alerts and messages go wherever you want.
- **Local-first** — Runs on your machine. Your data stays on your machine. No cloud subscription. No telemetry.

## Quick Start

### Prerequisites

- Python 3.10+
- An API key from any supported provider (or none — Ghost starts a setup wizard)

### One-liner (macOS / Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/boona13/ghost/main/install.sh | bash
```

This clones the repo, creates a virtual environment, installs all dependencies, and offers to start Ghost immediately. It also accepts flags for unattended installs:

```bash
# Non-interactive with Playwright and API key
curl -fsSL https://raw.githubusercontent.com/boona13/ghost/main/install.sh | bash -s -- --with-playwright --api-key sk-or-v1-...

# Skip all prompts
curl -fsSL https://raw.githubusercontent.com/boona13/ghost/main/install.sh | bash -s -- --no-interactive
```

Or clone first, then install:

```bash
git clone https://github.com/boona13/ghost.git
cd ghost
bash install.sh
```

### Install (Windows)

```powershell
git clone https://github.com/boona13/ghost.git
cd ghost
powershell -ExecutionPolicy Bypass -File install.ps1
```

```bat
start.bat
```

### Start / Stop

| | macOS / Linux | Windows |
|---|---|---|
| **Start** | `./start.sh` | `start.bat` |
| **Stop** | `./stop.sh` | `stop.bat` |

Open [http://localhost:3333](http://localhost:3333) — the setup wizard guides you through connecting your AI providers.

### Manual Install

```bash
git clone https://github.com/boona13/ghost.git
cd ghost
python3 -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt

# Optional: browser automation
pip install playwright && python -m playwright install chromium

python ghost_supervisor.py    # With supervisor (recommended)
# or
python ghost.py               # Standalone
```

### Docker

```bash
docker build -f Dockerfile.test -t ghost .
docker run -d --name ghost -p 3333:3333 ghost
```

### No API Key?

Ghost starts without one. Open [http://localhost:3333](http://localhost:3333) and the setup wizard walks you through provider selection, API key entry, connection testing, and fallback chain configuration — all from the browser.

## What Ghost Can Do

### 7 LLM Providers with Automatic Fallback

Ghost supports **OpenRouter** (200+ models), **OpenAI** (direct API), **OpenAI Codex** (ChatGPT subscription via OAuth — no extra cost), **Anthropic** (Claude), **Google Gemini** (free tier available), **DeepSeek**, and **Ollama** (local, completely free). Configure one or all — Ghost automatically falls back through your provider chain if one fails, with jittered exponential backoff, 5-minute cooldowns, and periodic probing of failed providers.

### 20+ Messaging Channels

Ghost reaches you wherever you are.

| Channel | How It Works |
|---|---|
| **WhatsApp** | QR code linking via neonize or Business API via webhook |
| **Telegram** | Bot API with reactions, threading, streaming, and polls |
| **Discord** | Webhook (zero-dependency) or full bot mode via discord.py |
| **Slack** | Webhook or Socket Mode with threads, reactions, and file uploads |
| **iMessage** | AppleScript + chat.db polling (macOS) |
| **Signal** | signal-cli REST API |
| **Email** | SMTP/IMAP with IDLE push |
| **Matrix, MS Teams, Google Chat, Mattermost, Line, IRC, Nostr** | Various integrations |
| **ntfy, Pushover** | Push notifications |
| **SMS, Webhook** | Universal fallback |

Every channel gets: message queuing with write-ahead logging, exponential backoff retries, crash recovery, per-channel formatting (Markdown to Slack mrkdwn, Telegram MarkdownV2, HTML, plain text), streaming (real-time message editing as the LLM generates), DM security policies (open/allowlist/blocklist), rate limiting, health monitoring, and per-channel onboarding wizards.

### Browser Automation

Playwright-based browser control with accessibility tree snapshots, ref-based element targeting, and full action support: navigate, click, type, fill forms, scroll, hover, upload files, paste images, execute JavaScript, read console logs, take screenshots, export PDFs, and manage tabs. Ghost uses the accessibility API for reliable element selection — no fragile CSS selectors.

### Web Intelligence

**Web search** across 6 providers with automatic fallback: Perplexity (via OpenRouter or direct), Grok/xAI, OpenAI (Responses API), Brave Search, and Gemini with Google Search grounding. Results are cached for 15 minutes.

**Web fetching** with a 5-tier extraction pipeline that auto-escalates if content quality is low:
1. Cloudflare Markdown for Agents
2. Mozilla Readability
3. Smart BeautifulSoup (semantic HTML targeting)
4. Firecrawl API (anti-bot, JS-heavy sites)
5. Regex fallback

Includes SSRF protection, prompt injection defense, and HTML sanitization.

### Vision, Image Generation, TTS, and Voice

**Vision** — Analyze images and screenshots via 5 providers with fallback: OpenAI, OpenRouter, Google Gemini, Anthropic, and Ollama (local).

**Image generation** — Create images via OpenRouter (Gemini 3 Pro), Google Gemini direct, or OpenAI (DALL-E 3 / gpt-image-1).

**Text-to-speech** — Generate audio via Edge TTS (free, no API key), OpenAI TTS (6 voices), or ElevenLabs.

**Voice Wake + Talk Mode** — Always-on speech interface with two modes:
- **Voice Wake** — Continuous wake word detection. Say "ghost" (or a custom trigger phrase) followed by a command. Ghost transcribes your speech, processes it, and speaks the response aloud. Start it from the Chat page mic button or the Configuration page.
- **Talk Mode** — Continuous conversation with no wake word needed. Every utterance is transcribed, sent to Ghost, and the reply is spoken back. Natural hands-free conversation.

Voice is an input method for the existing Chat — spoken interactions appear inline alongside typed messages, in one place. Speech-to-text supports Moonshine (on-device, offline, free), OpenRouter (multimodal), OpenAI Whisper, Groq Whisper, and Vosk (offline). TTS uses the same multi-provider pipeline (Edge TTS, OpenAI, ElevenLabs). Audio playback uses platform-native players (`afplay` on macOS, PowerShell on Windows, `mpv`/`paplay`/`aplay` on Linux) with a `sounddevice` fallback.

### Canvas

Visual output panel that lets Ghost display rich HTML/CSS/JS content alongside the chat. Instead of describing something in text, Ghost can build and show it — interactive demos, visualizations, dashboards, formatted reports, mini-apps, or any web content.

- **Agent-driven** — Ghost uses the `canvas` tool to write files, present content, navigate, and inject JavaScript
- **Live reload** — Content auto-updates in the panel when the agent modifies files
- **Session-based** — Each canvas session stores files in `~/.ghost/canvas/<session>/`
- **Side panel** — Renders in an iframe beside the chat, with open-in-tab and refresh controls
- **JS injection** — Ghost can execute JavaScript in the canvas for dynamic updates

### Google Workspace Integration

Full OAuth 2.0 integration with **Gmail** (read, send, draft, search, label, trash), **Google Calendar** (list, create, update, delete events, natural language quick-add), **Google Drive** (list, search, upload, download, share, create folders), **Google Docs** (create, read, insert, replace, batch update), and **Google Sheets** (create, read, write, append, clear, manage sheets).

### Memory System

Four layers of persistent memory:

- **Basic memory** — SQLite + FTS5 full-text search across conversations
- **Hybrid memory** — Combines FTS5 (BM25) + vector embeddings with temporal decay and MMR reranking. Supports 4 embedding providers with fallback (OpenRouter, Gemini, Ollama, offline hash-based).
- **Vector memory** — Cosine similarity search across typed memories (notes, facts, preferences, code, insights)
- **Session memory** — Auto-saves conversation summaries with LLM-generated slugs

### 42+ Skills + GhostHub Registry

Specialized knowledge that Ghost injects automatically when relevant:

| Category | Skills |
|---|---|
| **Productivity** | Apple Notes, Apple Reminders, Notion, Trello, Things (Mac) |
| **Development** | GitHub, code reviewer, fullstack development, UI development, browser automation |
| **Research** | Deep researcher (multi-source, structured output, credibility scoring), news search, blog watcher, competitive intelligence |
| **Content** | Content creator, social content, email drafting, translation, summarization |
| **Media** | Spotify player, GIF search, video frame extraction, image generation |
| **Social** | X/Twitter growth (post, like, comment, repost, follow with duplicate prevention), X account creator |
| **Finance** | Trading analysis (chart patterns, technical indicators, portfolio tracking) |
| **System** | Ghost system management, webhooks, weather, tmux, 1password, PDF tools, speech-to-text |

Plus user-created skills in `~/.ghost/skills/` and community skills from [GhostHub](https://github.com/boona13/skills-registry) — a public skill registry where anyone can publish and install skills with one click from the dashboard.

### Webhook Triggers

Event-driven automation — external services (GitHub, CI/CD, Stripe, custom apps) fire Ghost actions in real-time via HTTP POST. Each trigger has a pre-defined prompt template populated from the event payload, so the webhook sender cannot inject arbitrary instructions.

- **Built-in templates** — GitHub Push, Pull Request, Issue, and a generic template
- **Custom triggers** — write your own prompt template with `{field}` placeholders mapped to payload paths
- **Security** — Bearer token auth, optional per-trigger HMAC verification (e.g. GitHub's `X-Hub-Signature-256`), per-trigger cooldown, and global concurrency limits
- **Dashboard management** — create, edit, test, enable/disable, and delete triggers from the UI
- **LLM tools** — Ghost can create and manage triggers autonomously via `webhook_create`, `webhook_list`, `webhook_delete`, `webhook_test`

### Docker Sandboxing

Run untrusted code in isolated Docker containers with read-only root, tmpfs mounts, network isolation, dropped capabilities, and resource limits (512MB RAM, 1 CPU, 256 PIDs). Containers are auto-pruned after 24 hours idle.

### Code Intelligence

Analyze Python codebases: LOC, cyclomatic complexity, maintainability index, function/class extraction, import analysis, and bug pattern detection (bare except, eval/exec, shell injection, hardcoded secrets). Repository-wide aggregate metrics with recommendations.

### Plugin System

Extend Ghost with plugins in `~/.ghost/plugins/`. Hook into: before_analyze, after_analyze, before_tool_call, after_tool_call, on_classify, on_screenshot, on_feed_append, on_startup, on_shutdown, on_action, on_session_end. Plugins can register custom tools, access config and memory, and store plugin-specific data.

## Self-Evolution

Ghost modifies its own source code. When a change is needed — from a user request, a bug hunter scan, a tech scout discovery, or a security audit — it flows through the **Serial Evolution Queue**:

1. **Queue** — Changes are added to the Future Features backlog with priority (P0–P3)
2. **Pick** — The Evolution Runner selects the highest-priority pending item
3. **Plan** — Creates a full project backup, identifies files to change
4. **Apply** — Makes changes using search/replace patches
5. **Test** — Runs syntax checks, import checks, smoke tests, API route validation
6. **Deploy** — Waits for running cron jobs to finish, then restarts Ghost
7. **Rollback** — If anything breaks, restores from backup automatically

All evolution is serialized — only one change deploys at a time, preventing concurrent restarts from killing in-progress work. P0/P1 items trigger immediate processing. The supervisor auto-rolls back after 5 consecutive crashes.

## Autonomous Growth

Ghost improves itself on configurable schedules:

| Routine | Schedule | What It Does |
|---|---|---|
| **Tech Scout** | Every 12h | Browses AI/tech news, queues improvements |
| **Health Check** | Every 2h | Tests APIs, tools, disk, connectivity |
| **User Context** | Every 4h | Learns from email/calendar to anticipate needs |
| **Skill Improver** | Daily 3am | Reviews and upgrades skill definitions |
| **Soul Evolver** | Weekly Sun | Reflects on interactions, refines personality |
| **Bug Hunter** | Every 6h | Scans logs for errors, queues fixes |
| **Competitive Intel** | Mon/Fri 6am | Researches competitor communities for ideas |
| **Security Patrol** | Daily 5am | Runs security audits, queues patches |
| **Content Health** | Weekly Sun | Tests web extraction pipeline quality |
| **Visual Monitor** | Every 8h | Screenshot analysis for visual issues |
| **Feature Implementer** | Event-driven | The only routine with evolve tools — processes the queue serially |
| **Implementation Auditor** | Event-driven | Verifies recently implemented features are properly wired |

### Self-Healing

If Ghost crashes, the supervisor captures the traceback and writes a crash report. On restart, Ghost reads the report, diagnoses the cause, and fixes itself via the evolution engine. If it can't self-repair after 5 attempts, the supervisor rolls back to the last known good backup.

### State Repair

On every startup, Ghost validates its critical state files (config.json, memory.db, x_tracker.db, debug logs, evolution history), repairs corruption, and creates backups before any fix.

## Dashboard

The web dashboard at [http://localhost:3333](http://localhost:3333) is a full management interface with 29 pages:

| Page | What It Does |
|---|---|
| **Chat** | Real-time messaging with file attachments, audio transcription, tool step streaming, inline evolution approvals, voice mic toggle, and Canvas panel |
| **Overview** | Live daemon status, PID, uptime, action counts, feature toggles, platform info |
| **Activity Feed** | Live feed of all actions with type filtering and auto-refresh |
| **Console** | Real-time SSE event stream with category filters, search, and pause/resume |
| **Soul** | Edit Ghost's personality (SOUL.md) |
| **User Profile** | Edit user info (USER.md) with quick-set form |
| **Memory** | Search, browse, and prune the memory database |
| **Models** | Multi-provider management, fallback chain visualization, model browser with pricing |
| **Skills** | Browse, search, enable/disable, edit 42+ skills with requirements checking + GhostHub Registry |
| **Autonomy** | Action items, growth routine status, growth log, crash reports |
| **Evolution** | Self-modification history, approve/reject pending changes, view diffs, rollback |
| **Future Features** | Prioritized backlog for autonomous implementation — add, approve, reject, track |
| **Channels** | Configure, enable/disable, test, and monitor 20+ messaging channels |
| **Integrations** | Google OAuth, Grok, ElevenLabs, web search providers, image gen, vision, TTS |
| **Configuration** | All settings with hot-reload — feature toggles, rate limits, growth schedules, security, voice controls |
| **Cron Jobs** | Create and manage scheduled tasks |
| **Security** | AI-driven security audits with real-time streaming and auto-fix |
| **Accounts** | Credential management |
| **Setup** | Multi-provider wizard with connection testing and Setup Doctor |

## Architecture

```
ghost.py                    Main daemon — LLM routing, action handling, GhostDaemon class
ghost_loop.py               ToolLoopEngine — multi-turn LLM + tool execution (up to 200 steps)
ghost_tools.py              Core tools — shell, files, web fetch, notifications
ghost_browser.py            Browser automation — Playwright with accessibility tree
ghost_memory.py             Basic memory — SQLite + FTS5
ghost_hybrid_memory.py      Hybrid memory — FTS5 + vector embeddings + temporal decay + MMR
ghost_vector_memory.py      Vector memory — cosine similarity search
ghost_session_memory.py     Session memory — auto-save conversation summaries
ghost_web_search.py         Web search — 6 providers with fallback and caching
ghost_web_fetch.py          Web fetch — 5-tier extraction pipeline with SSRF protection
ghost_vision.py             Vision — 5-provider image analysis
ghost_image_gen.py          Image generation — 3 providers
ghost_tts.py                Text-to-speech — Edge TTS, OpenAI, ElevenLabs
ghost_voice.py              Voice Wake + Talk Mode — wake word detection, STT, chat integration, TTS playback
ghost_canvas.py             Canvas — visual output panel, session management, file serving
ghost_cron.py               Cron service — at/every/cron schedule types
ghost_skills.py             Skill loader — auto-discovery and trigger matching
ghost_plugins.py            Plugin system — hooks, custom tools, plugin data
ghost_evolve.py             Evolution engine — backup, validate, test, deploy, rollback
ghost_autonomy.py           Autonomous growth — 10+ routines, action items, self-repair
ghost_future_features.py    Feature backlog — prioritized queue for serial evolution
ghost_providers.py          LLM providers — 7 providers with format adapters
ghost_auth_profiles.py      Auth store — API keys, OAuth tokens, credential sync
ghost_oauth.py              OAuth — Codex PKCE flow
ghost_integrations.py       Google Workspace + Grok integration
ghost_webhooks.py           Webhook triggers — event-driven automation via HTTP POST
ghost_code_intel.py         Code intelligence — analysis, metrics, bug detection
ghost_data_extract.py       Data extraction — structured data from unstructured text
ghost_security_audit.py     Security audits — AI-driven with auto-fix
ghost_state_repair.py       State repair — validate and fix config/DB/logs on startup
ghost_setup_doctor.py       Setup doctor — preflight checks and safe auto-fixes
ghost_console.py            Event bus — real-time SSE streaming
ghost_email.py              Disposable email — instant accounts via mail.tm
ghost_credentials.py        Credential storage — structured service credentials
ghost_x_tracker.py          X/Twitter tracker — duplicate prevention for social actions
ghost_supervisor.py         Process supervisor — crash recovery, auto-rollback
ghost_dashboard/            Flask web dashboard — 29 pages, real-time SSE
  routes/                   31 API blueprint modules
  static/js/pages/          Frontend page modules (SPA, no build step)
  templates/                HTML shell
ghost_channels/             20+ messaging channel implementations
  imessage.py               AppleScript + chat.db (macOS)
  whatsapp.py               neonize (QR) + Business API
  telegram.py               Bot API (zero dependencies)
  discord.py                Webhook + discord.py bot mode
  slack.py                  Webhook + Socket Mode
  signal.py                 signal-cli REST API
  ...and 14 more
skills/                     42 bundled skill definitions
SOUL.md                     Agent personality and development standards
USER.md                     User profile for personalization
```

## CLI

```bash
python ghost.py                        # Start daemon + dashboard
python ghost.py status                 # Daemon stats
python ghost.py log                    # Action history
python ghost.py context                # Current user context
python ghost.py cron list              # Scheduled jobs
python ghost.py soul show              # View personality
python ghost.py soul edit              # Edit SOUL.md
python ghost.py user show              # View user profile
python ghost.py dashboard              # Dashboard standalone
python ghost.py dashboard 8080         # Custom port
```

## Data Storage

All runtime data lives in `~/.ghost/`:

```
~/.ghost/
  config.json               Configuration
  auth_profiles.json        Provider credentials (API keys + OAuth tokens)
  memory.db                 SQLite memory database
  log.json                  Action history
  feed.json                 Activity feed
  ghost.pid                 Running daemon PID
  action_items.json         Things needing user attention
  growth_log.json           Autonomous improvement history
  future_features.json      Evolution backlog
  feature_changelog.json    Completed features log
  integrations.json         Google OAuth tokens
  channels.json             Channel configurations
  cron/jobs.json            Scheduled job definitions
  evolve/backups/           Project backups before self-modifications
  audio/                    Generated TTS audio files
  voice/                    Voice capture temp files and STT models
  canvas/                   Canvas session files (HTML/CSS/JS)
  generated_images/         Generated images
  memory/sessions/          Session summaries
  skills/                   User-created skills
  plugins/                  User plugins
  screenshots/              Captured screenshots
  state_backups/            State file backups from repair
```

## Configuration

Ghost stores configuration at `~/.ghost/config.json`. Every setting is editable from the dashboard with hot-reload (no restart needed).

| Key | Default | Description |
|---|---|---|
| `model` | `google/gemini-2.0-flash-001` | LLM model ID |
| `enable_tool_loop` | `true` | Multi-turn tool execution |
| `tool_loop_max_steps` | `40` | Max tool-loop iterations per task |
| `enable_evolve` | `true` | Allow self-modification |
| `evolve_auto_approve` | `false` | Skip approval for evolution changes |
| `enable_growth` | `true` | Autonomous improvement routines |
| `enable_browser_tools` | `true` | Browser automation |
| `enable_memory_db` | `true` | Persistent memory |
| `enable_cron` | `true` | Cron scheduler |
| `enable_voice` | `true` | Voice Wake + Talk Mode |
| `enable_canvas` | `true` | Canvas visual output panel |
| `enable_integrations` | `true` | Google/Grok integrations |

## Cross-Platform

Ghost runs on **macOS**, **Linux**, and **Windows**. No system-level dependencies required — all Python packages are pip-installable with pure-Python fallbacks where system libraries are needed (e.g., `python-magic` shim for WhatsApp media detection). File paths use `pathlib.Path` everywhere. OS-specific behavior is centralised in `ghost_platform.py` and gated with `platform.system()`.

- **Install & launch scripts**: `install.sh` / `start.sh` / `stop.sh` (macOS/Linux) and `install.ps1` / `start.bat` / `stop.bat` (Windows)
- **Process management**: `SIGTERM` on Unix, `taskkill` on Windows, with cross-platform detached-process and process-group helpers
- **Notifications**: `osascript` (macOS), `notify-send` (Linux), PowerShell balloon tips (Windows)
- **Audio playback**: `afplay` (macOS), `mpv`/`paplay`/`aplay` (Linux), PowerShell `SoundPlayer` (Windows), with `sounddevice` pure-Python fallback
- **Memory detection**: `sysctl` (macOS), `/proc/meminfo` (Linux), `Win32_ComputerSystem` (Windows)
- **Shell sessions**: `/bin/sh` on Unix, `cmd.exe` on Windows, with platform-appropriate exit-code markers

## Disclaimer

Ghost is open-source software provided as-is. It can execute shell commands, modify files, browse the web, and send messages on your behalf. **You are responsible for how you use it.** Ghost is not financial advice, not a licensed professional service, and not liable for any actions taken based on its output. Review what it does. Use at your own risk.

## License

MIT
