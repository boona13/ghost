# Ghost Skills

Skills extend Ghost's capabilities by injecting specialized instructions into the LLM's system prompt when clipboard content matches their triggers. A skill is a single markdown file (`SKILL.md`) with YAML frontmatter and a body of instructions.

## How Skills Work

1. You copy text to the clipboard
2. Ghost classifies the content type
3. The **SkillLoader** checks each skill's triggers against the text and content type
4. Matching skills (sorted by priority) have their body injected into the system prompt
5. The LLM receives the specialized instructions along with the content

This means skills don't add new tools — they teach Ghost *how to use existing tools* for specific tasks.

## Bundled Skills

Ghost ships with 25 bundled skills in the `skills/` directory:

| Skill | Triggers | Tools | Description |
|---|---|---|---|
| `1password` | 1password, op, password, secret | shell_exec | 1Password CLI integration |
| `apple-notes` | notes, apple notes, note to self | shell_exec | Create/search Apple Notes |
| `apple-reminders` | reminder, remind me, todo | shell_exec | Create Apple Reminders |
| `blogwatcher` | blog, rss, feed, article | web_fetch, shell_exec | Monitor blogs/RSS feeds |
| `browser` | browse, website, web page, url | browser | Browser automation |
| `code-reviewer` | review, code review, PR | file_read, shell_exec | Code review assistance |
| `general` | (low priority catch-all) | shell_exec, file_read, file_write | General-purpose assistance |
| `gifgrep` | gif, giphy, reaction | web_fetch | Search for GIFs |
| `github` | github, PR, issue, repo | shell_exec, web_fetch | GitHub CLI integration |
| `himalaya` | email, mail, inbox | shell_exec | Email via Himalaya CLI |
| `nano-pdf` | pdf, document | shell_exec | PDF processing |
| `notion` | notion, page, database | shell_exec | Notion integration |
| `openai-image-gen` | generate image, create image, dall-e | web_fetch | AI image generation |
| `peekaboo` | screenshot, screen, capture | shell_exec | Screenshot tools |
| `researcher` | research, find, look up, search | web_fetch, shell_exec | Web research |
| `spotify-player` | spotify, music, play, song | shell_exec | Spotify control |
| `summarize` | summarize, summary, tldr | (none) | Text summarization |
| `things-mac` | things, task, project | shell_exec | Things 3 integration |
| `tmux` | tmux, terminal, session | shell_exec | Tmux session management |
| `trader` | stock, crypto, trade, price | web_fetch | Market data and trading |
| `translator` | translate, translation, language | (none) | Translation |
| `trello` | trello, board, card | shell_exec | Trello integration |
| `video-frames` | video, frame, extract | shell_exec | Video frame extraction |
| `weather` | weather, forecast, temperature | web_fetch | Weather information |
| `webhooks` | webhook, trigger, github webhook | webhook_create, webhook_list, webhook_delete, webhook_test | Webhook trigger management |

## SKILL.md Format

A skill file has two parts: YAML frontmatter (between `---` markers) and a markdown body.

### Minimal Example

```markdown
---
name: my-skill
description: "A brief description of what this skill does"
triggers:
  - "keyword1"
  - "keyword2"
---

When the user copies content related to keyword1 or keyword2,
follow these instructions to help them.

Use the `shell_exec` tool to run commands as needed.
```

### Full Example

```markdown
---
name: weather
description: "Get weather forecasts and current conditions"
triggers:
  - "weather"
  - "forecast"
  - "temperature"
  - "rain"
  - "snow"
tools:
  - "web_fetch"
priority: 5
os:
  - "Darwin"
  - "Linux"
requires:
  bins:
    - "curl"
  env:
    - "WEATHER_API_KEY"
---

# Weather Skill

When the user asks about weather, use the `web_fetch` tool to query
a weather API and present the results in a clear format.

## Steps

1. Parse the location from the user's input
2. Use `web_fetch` to call the weather API
3. Present current conditions and forecast

## Output Format

- Current temperature and conditions
- Today's high/low
- 3-day forecast summary
```

### Frontmatter Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | **Yes** | — | Unique skill identifier |
| `description` | string | No | `""` | Brief description shown in dashboard |
| `triggers` | list | **Yes** | — | Keywords or content types that activate this skill |
| `tools` | list | No | `[]` | Tools this skill uses (for tool filtering) |
| `priority` | integer | No | `0` | Higher priority skills are matched first |
| `os` | string or list | No | `null` | OS filter: `"Darwin"`, `"Linux"`, `"Windows"`, or a list |
| `requires` | object | No | `{}` | Requirements that must be met |
| `requires.bins` | list | No | `[]` | Binary executables that must be on PATH |
| `requires.env` | list | No | `[]` | Environment variables that must be set |

### Triggers

Triggers are case-insensitive substring matches. A skill activates when **any** trigger matches the clipboard text or content type.

```yaml
triggers:
  - "github"       # Matches text containing "github"
  - "PR"           # Matches text containing "PR"
  - "pull request" # Matches text containing "pull request"
  - "code"         # Matches the content type "code"
  - "error"        # Matches the content type "error"
  - "image"        # Matches screenshot/image processing
```

Content types you can trigger on: `url`, `error`, `code`, `json`, `foreign`, `long_text`, `image`.

### Tools

The `tools` field tells Ghost which tools this skill needs. When a skill is matched, Ghost narrows the tool registry to only the listed tools (plus `memory_search`, `memory_save`, and `notify` which are always available).

If `tools` is empty, the full tool registry is available.

```yaml
tools:
  - "shell_exec"   # Execute shell commands
  - "file_read"    # Read files
  - "file_write"   # Write files
  - "file_search"  # Search for files
  - "web_fetch"    # Fetch URLs
  - "browser"      # Full browser automation
  - "notify"       # System notifications
  - "app_control"  # Open applications
  - "clipboard_read"   # Read clipboard
  - "clipboard_write"  # Write to clipboard
```

### Requirements

Requirements let you declare what a skill needs to function. The dashboard shows ✓/✗ for each requirement and marks skills as ineligible if requirements aren't met.

```yaml
requires:
  bins:
    - "gh"         # GitHub CLI must be installed
    - "jq"         # jq must be installed
  env:
    - "GITHUB_TOKEN"   # Environment variable must be set
```

Requirements are **advisory** — they affect the dashboard UI and eligibility status but don't prevent the skill from being matched.

### Priority

Skills are matched in priority order (highest first). If multiple skills match the same content, higher-priority skills appear first in the system prompt.

```yaml
priority: 10   # High priority, matched first
priority: 0    # Default
priority: -5   # Low priority, catch-all
```

### OS Filter

Restrict a skill to specific operating systems.

```yaml
os: "Darwin"              # macOS only
os: ["Darwin", "Linux"]   # macOS and Linux
```

Omit this field to make the skill available on all platforms.

## Creating a Custom Skill

### Step 1: Create the Directory

```bash
mkdir -p ~/.ghost/skills/my-skill
```

### Step 2: Write SKILL.md

```bash
cat > ~/.ghost/skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: "Does something useful when you copy specific text"
triggers:
  - "my keyword"
  - "another trigger"
tools:
  - "shell_exec"
  - "web_fetch"
priority: 5
---

# My Custom Skill

When the user copies text containing "my keyword", follow these steps:

1. Use `shell_exec` to check the current state
2. Use `web_fetch` to get additional data if needed
3. Present a clear, actionable response

## Important Notes

- Always confirm before making destructive changes
- Format output as markdown
EOF
```

### Step 3: Verify

The skill is auto-discovered within 30 seconds, or you can restart Ghost. Check the dashboard's Skills page to verify it loaded.

### Step 4: Test

Copy text containing one of your trigger keywords. Ghost should match your skill and follow your instructions.

## Writing Effective Skills

### Be Specific

Tell the LLM exactly what to do, step by step. Vague instructions produce vague results.

```markdown
# Bad
Help the user with their email.

# Good
1. Use `shell_exec` to run `himalaya list --page-size 5` to check recent emails
2. Parse the output and present a summary of unread messages
3. If the user copied an email address, draft a reply template
```

### Declare Tools

List the tools your skill needs in the `tools` field. This lets Ghost narrow the tool set, reducing confusion and improving accuracy.

### Use Constraints

Tell the LLM what *not* to do.

```markdown
## Constraints
- Never delete files without explicit confirmation
- Limit shell commands to read-only operations
- Don't expose API keys or tokens in output
```

### Provide Output Format

Define how the response should look.

```markdown
## Output Format
Present results as a markdown table:
| Stock | Price | Change |
|-------|-------|--------|
| AAPL  | $185  | +1.2%  |
```

## Managing Skills via Dashboard

The Skills page at [http://localhost:3333/#skills](http://localhost:3333/#skills) provides:

- **Search** across all skills by name, description, or trigger
- **Filter** by status (Eligible, Disabled, Missing Requirements)
- **Enable/Disable** toggle on each skill card
- **Edit** skill content directly in the browser
- **Requirements** status with ✓/✗ indicators for each binary and environment variable

Disabled skills are stored in `config.json` under `disabled_skills` and are excluded from matching even if their triggers hit.

## Managing Skills via CLI

```bash
# Skills are auto-loaded from these directories:
ls skills/                 # Bundled skills
ls ~/.ghost/skills/        # User skills

# Check loaded skills
python ghost.py status     # Shows skill count in features
```

## Skill Discovery Directories

| Directory | Priority | Description |
|---|---|---|
| `<project>/skills/` | Bundled | Ships with Ghost, updated with the codebase |
| `~/.ghost/skills/` | User | Your custom skills, persisted across updates |

Both directories are scanned for `SKILL.md` files. Skills can be at the root or in subdirectories:

```
skills/
  my-skill/SKILL.md        ✓ Found (subdirectory)
  standalone/SKILL.md       ✓ Found (subdirectory)
```

The loader reloads skills every 30 seconds, so changes take effect without restarting Ghost.
