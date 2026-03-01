# Ghost Configuration

Ghost stores its configuration at `~/.ghost/config.json`. Every setting can be changed through:

1. **Web Dashboard** — Configuration page at [http://localhost:3333/#config](http://localhost:3333/#config)
2. **Direct edit** — Edit `~/.ghost/config.json` with any text editor
3. **API** — `PUT /api/config` with a JSON body

Changes made via the dashboard or API are hot-reloaded into the running daemon instantly.

## Configuration Reference

### Model & API

| Key | Type | Default | Description |
|---|---|---|---|
| `model` | string | `"google/gemini-2.0-flash-001"` | OpenRouter model ID. Browse available models at the dashboard's Models page or [openrouter.ai/models](https://openrouter.ai/models). |
| `api_key` | string | `""` | OpenRouter API key. Can also be set via `OPENROUTER_API_KEY` environment variable (takes precedence). |

### Polling & Rate Limits

| Key | Type | Default | Description |
|---|---|---|---|
| `poll_interval` | float | `0.5` | How often to check the clipboard, in seconds. Lower = more responsive, higher = less CPU. |
| `min_length` | int | `30` | Minimum character length for text to be processed. Text shorter than this is skipped. |
| `rate_limit_seconds` | int | `3` | Minimum seconds between processing actions. Prevents rapid-fire API calls when pasting repeatedly. |
| `max_input_chars` | int | `4000` | Maximum characters sent to the LLM per request. Longer text is truncated. |
| `max_feed_items` | int | `50` | Maximum entries kept in the activity feed (`feed.json`). Oldest are removed when exceeded. |

### Feature Toggles

| Key | Type | Default | Description |
|---|---|---|---|
| `enable_tool_loop` | bool | `true` | Enable multi-turn tool use. When `true`, Ghost can call tools and iterate. When `false`, falls back to single-shot LLM calls with no tool access. |
| `tool_loop_max_steps` | int | `40` | Maximum iterations in the tool loop. Prevents runaway tool chains. The LLM usually finishes in 1-5 steps. |
| `enable_memory_db` | bool | `true` | Enable persistent memory. When `true`, every action is saved to `~/.ghost/memory.db` and the LLM can search/save memories. |
| `enable_plugins` | bool | `true` | Enable the plugin system. Plugins can register hooks, tools, and modify behavior. |
| `enable_skills` | bool | `true` | Enable skill matching. When `true`, clipboard content is matched against SKILL.md files and matching instructions are injected into the system prompt. |
| `enable_system_tools` | bool | `true` | Enable built-in system tools (shell_exec, file_read, file_write, etc.). |
| `enable_browser_tools` | bool | `true` | Enable browser automation tool. Requires Playwright. |
| `enable_cron` | bool | `true` | Enable the cron scheduler for scheduled tasks. |

### Security

| Key | Type | Default | Description |
|---|---|---|---|
| `allowed_commands` | list | *(see below)* | Whitelist of shell commands the LLM can execute via `shell_exec`. Commands not in this list are rejected. |
| `allowed_roots` | list | `["/Users/<you>"]` | Directory whitelist for file operations. `file_read`, `file_write`, and `file_search` are restricted to paths under these roots. |

**Default `allowed_commands`:**

```json
[
  "ls", "pwd", "echo", "date", "cat", "head", "tail", "wc",
  "grep", "find", "which", "whoami", "uname", "df", "du",
  "mv", "cp", "mkdir", "rm", "rmdir", "touch", "chmod", "chown",
  "ln", "open", "sort", "uniq", "awk", "sed", "tr", "cut",
  "xargs", "tee", "diff", "zip", "unzip", "tar", "gzip",
  "python3", "python", "node", "pip", "npm", "brew",
  "git", "curl", "wget", "ssh", "scp", "rsync",
  "ps", "kill", "top", "lsof", "stat", "file", "md5", "shasum",
  "pbcopy", "pbpaste", "say", "defaults", "sw_vers",
  "jq", "rg", "fd", "bat", "exa"
]
```

### Dashboard

| Key | Type | Default | Description |
|---|---|---|---|
| `dashboard_port` | int | `3333` | Port for the web dashboard. If the port is busy, Ghost tries the next 9 ports. |

### Skill Management

| Key | Type | Default | Description |
|---|---|---|---|
| `disabled_skills` | list | `[]` | List of skill names to exclude from matching. Managed via the dashboard's Skills page. |

## Environment Variables

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter API key. Overrides `api_key` in config. |

## File Locations

| Path | Description |
|---|---|
| `~/.ghost/config.json` | Main configuration file |
| `~/.ghost/log.json` | Action history (last 500 entries) |
| `~/.ghost/feed.json` | Activity feed (last 50 entries) |
| `~/.ghost/ghost.pid` | Running daemon PID |
| `~/.ghost/memory.db` | SQLite persistent memory database |
| `~/.ghost/paused` | Pause flag (file presence = paused) |
| `~/.ghost/own_copy` | Own-copy flag (skip own clipboard writes) |
| `~/.ghost/action.json` | Panel-to-daemon communication |
| `~/.ghost/screenshots/` | Processed screenshot storage |
| `~/.ghost/cron/jobs.json` | Cron job definitions |
| `~/.ghost/skills/` | User-created skills directory |
| `~/.ghost/plugins/` | User plugins directory |
| `<project>/SOUL.md` | Agent personality definition |
| `<project>/USER.md` | User profile for personalization |

## Default Configuration

The full default configuration:

```json
{
  "model": "google/gemini-2.0-flash-001",
  "poll_interval": 0.5,
  "min_length": 30,
  "rate_limit_seconds": 3,
  "max_input_chars": 4000,
  "max_feed_items": 50,
  "enable_tool_loop": true,
  "tool_loop_max_steps": 40,
  "enable_memory_db": true,
  "enable_plugins": true,
  "enable_skills": true,
  "enable_system_tools": true,
  "enable_browser_tools": true,
  "enable_cron": true,
  "allowed_commands": [
    "ls", "pwd", "echo", "date", "cat", "head", "tail", "wc",
    "grep", "find", "which", "whoami", "uname", "df", "du",
    "mv", "cp", "mkdir", "rm", "rmdir", "touch", "chmod", "chown",
    "ln", "open", "sort", "uniq", "awk", "sed", "tr", "cut",
    "xargs", "tee", "diff", "zip", "unzip", "tar", "gzip",
    "python3", "python", "node", "pip", "npm", "brew",
    "git", "curl", "wget", "ssh", "scp", "rsync",
    "ps", "kill", "top", "lsof", "stat", "file", "md5", "shasum",
    "pbcopy", "pbpaste", "say", "defaults", "sw_vers",
    "jq", "rg", "fd", "bat", "exa"
  ],
  "allowed_roots": ["/Users/<your-username>"]
}
```

## Content Types

Ghost classifies clipboard content into these types, each with a tailored system prompt:

| Type | Detection | LLM Behavior |
|---|---|---|
| `url` | Starts with `http://` or `https://` | Fetches page content, summarizes in 2-3 sentences |
| `error` | Contains `Traceback`, `Error:`, `Exception:`, etc. | Debugs the error, suggests a fix command |
| `code` | Contains `def`, `class`, `import`, `function`, `const`, etc. | Explains the code snippet in 2-3 sentences |
| `json` | Starts with `{` or `[` | Describes the JSON data structure |
| `foreign` | More than 30% non-Latin characters | Translates to English |
| `long_text` | Longer than 150 characters | Analyzes for scams + provides summary |
| `image` | Screenshot file or clipboard image | Describes image content in 2-4 sentences |
| `skip` | Too short, looks like a file path, empty | Not processed |

## CLI Configuration

Settings can also be passed as CLI arguments (these override config file values for that session):

```bash
python ghost.py --api-key sk-or-v1-...    # Override API key
python ghost.py --model anthropic/claude-3.5-sonnet  # Override model
python ghost.py --poll 1.0                 # Override poll interval
```

## Resetting Configuration

### Via Dashboard

Go to Configuration page → click "Reset to Defaults".

### Via CLI

```bash
rm ~/.ghost/config.json
python ghost.py start   # Recreates with defaults
```

### Via API

```bash
curl -X PUT http://localhost:3333/api/config \
  -H "Content-Type: application/json" \
  -d '{"model":"google/gemini-2.0-flash-001","poll_interval":0.5}'
```
