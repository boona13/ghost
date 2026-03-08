# Ghost Skills

Skills extend Ghost's capabilities by injecting specialized instructions into the LLM's system prompt when a user's message or task matches their triggers. A skill is a single markdown file (`SKILL.md`) with YAML frontmatter and a body of instructions.

## How Skills Work

1. A user sends a message (via chat, channel, or cron task)
2. The **SkillLoader** checks each skill's triggers against the message text and content type
3. Matching skills (sorted by priority) have their body injected into the system prompt
4. The LLM receives the specialized instructions along with the user's message
5. Ghost executes the task with focused tool access and domain-specific guidance

Skills don't add new tools — they teach Ghost *how to use existing tools* for specific tasks.

## Bundled Skills

Ghost ships with 42 bundled skills in the `skills/` directory:

| Skill | Triggers | Tools | Description |
|---|---|---|---|
| `1password` | 1password, password, secret, credential, op, vault | shell_exec | 1Password CLI integration |
| `apple-notes` | note, notes, apple notes, memo | shell_exec | Apple Notes via memo CLI |
| `apple-reminders` | reminder, reminders, todo, remindctl | shell_exec | Apple Reminders via remindctl CLI |
| `blogwatcher` | rss, blog, feed, subscribe, articles | shell_exec, web_fetch | Monitor blogs/RSS feeds |
| `browser` | browse, open website, go to, visit, fill form, scrape | browser, shell_exec | Browser automation with snapshot+ref |
| `code-reviewer` | code, function, class, def, const, import | file_read, shell_exec, memory_search | Code review and analysis |
| `competitive-intel` | competitor, ai landscape, feature gap, ai agent trends | web_search, web_fetch, browser, memory | AI ecosystem research |
| `email-creator` | create email, email account, new email, check inbox | email_create, email_inbox, email_read, credential_* | Disposable email creation |
| `fullstack-development` | implement, feature, build, create, new endpoint | file_*, shell_exec, browser, evolve_* | Full-stack implementation standards |
| `future_features` | future feature, feature backlog, queue feature | add_future_feature, list_future_features, get_feature_stats | Evolution queue management |
| `general` | *(low priority catch-all)* | memory_search, web_search, file_read, shell_exec | Default fallback skill |
| `ghost-creative-studio` | creative workflow, ai workflow, generate content | text_to_image_local, text_to_video, pipeline_*, bark_speak | Multi-step creative AI workflows |
| `ghost-mistakes` | evolve, evolution, bug fix | *(none)* | Query past mistakes before evolution |
| `ghost-node-developer` | create node, new node, build node, add tool | file_*, shell_exec, nodes_list, gpu_status | Guide for building new AI nodes |
| `ghost-nodes-pipelines` | pipeline, create video, multi-step, workflow | pipeline_*, text_to_image_local, text_to_video | Chain AI tools into pipelines |
| `ghost-system` | evolve, self-modify, add feature, ghost code | file_*, shell_exec, evolve_*, browser | Ghost's self-knowledge and architecture |
| `gifgrep` | gif, meme, reaction, tenor, giphy | shell_exec, clipboard_write | GIF search and download |
| `github` | github, PR, pull request, commit, issue, CI | shell_exec, web_fetch, clipboard_read | GitHub CLI integration |
| `google_workspace` | gmail, calendar, google drive, google docs, sheets | google_gmail, google_calendar, google_drive, google_docs, google_sheets | Full Google Workspace integration |
| `himalaya` | email, mail, inbox, himalaya, send email | shell_exec, file_read, file_write | CLI email via IMAP/SMTP |
| `image-generation` | generate image, create image, concept art, thumbnail | generate_image | AI image generation |
| `moonshine-stt` | moonshine, transcribe, speech to text, .mp3, .wav | shell_exec, file_read, notify | Moonshine speech-to-text |
| `nano-pdf` | pdf, document, edit pdf, modify pdf | shell_exec, file_read | AI-powered PDF editing |
| `news-search` | news, latest news, headlines, current events | web_search, web_fetch, memory_search | Real news search (not summaries) |
| `notion` | notion, workspace, database, notion page | shell_exec, file_read, web_fetch | Notion API integration |
| `openai-image-gen` | generate image, create image, draw, ai image | generate_image | Image generation via DALL-E |
| `peekaboo` | peekaboo, ui, window, screenshot, automation | shell_exec, file_read | macOS UI automation |
| `pr-reviewer` | pr review, code review, pull request | read_pr_diff, read_pr_file, leave_comment, submit_review | Internal PR review workflow |
| `researcher` | url, article, paper, research, deep dive | web_fetch, web_search, memory_search, browser | Deep multi-source research |
| `spotify-player` | spotify, music, song, play, playlist | shell_exec | Spotify CLI control |
| `summarize` | summarize, summary, tldr, transcript, youtube | shell_exec, web_fetch, file_read | Text and media summarization |
| `things-mac` | things, task, project, things 3 | shell_exec | Things 3 on macOS |
| `tmux` | tmux, session, terminal, pane | shell_exec | tmux session management |
| `trader` | stock, crypto, trading, chart, BTC, price, market | web_fetch, memory_search | Trading and market analysis |
| `translator` | foreign, translate, translation | memory_search | Language detection and translation |
| `trello` | trello, board, card, kanban | shell_exec, web_fetch | Trello board management |
| `ui-development` | dashboard, ui, ux, frontend, css, design | file_*, browser, evolve_* | Dashboard UI/UX standards |
| `video-frames` | video, frame, extract, ffmpeg | shell_exec, file_read | Video frame extraction |
| `weather` | weather, forecast, temperature, rain | shell_exec, web_fetch | Weather via wttr.in |
| `webhooks` | webhook, trigger, github webhook, stripe webhook | webhook_create, webhook_list, webhook_delete, webhook_test | Webhook trigger management |
| `x-account-creator` | create x account, sign up twitter | browser, email_*, credential_* | X/Twitter account setup |
| `x-growth` | post on x, tweet, like, repost, x growth | browser, generate_image, x_*_action, memory | X/Twitter growth automation |

## GhostHub Registry

GhostHub is a public skill registry hosted on GitHub. Community members can publish skills for anyone to install.

**Browse:** Dashboard → Skills → **GhostHub Registry** tab

**Install:** Click **Install** on any skill card, or ask Ghost:
```
install the weather skill from ghosthub
```

**Submit:** Fork [boona13/skills-registry](https://github.com/boona13/skills-registry), add your skill to `skills/<name>/SKILL.md`, and open a PR. CI validates the frontmatter and auto-rebuilds the index on merge.

Registry skills install to `~/.ghost/skills/<name>/SKILL.md` and are picked up by the SkillLoader within 30 seconds.

### Registry Configuration

| Config Key | Default | Description |
|---|---|---|
| `enable_skill_registry` | `true` | Enable the GhostHub registry feature |

The registry client fetches from `https://raw.githubusercontent.com/boona13/skills-registry/main/index.json` and caches locally for 1 hour.

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

When the user asks about keyword1 or keyword2,
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
model: "google/gemini-2.5-flash"
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
| `model` | string | No | `null` | Preferred LLM model for this skill (can be overridden in config) |
| `os` | string or list | No | `null` | OS filter: `"Darwin"`, `"Linux"`, `"Windows"`, or a list |
| `requires` | object | No | `{}` | Requirements that must be met |
| `requires.bins` | list | No | `[]` | Binary executables that must be on PATH |
| `requires.env` | list | No | `[]` | Environment variables that must be set |
| `content_types` | list | No | `[]` | Content types this skill specializes in |

### Triggers

Triggers are case-insensitive substring matches. A skill activates when **any** trigger matches the user's message text or the classified content type.

```yaml
triggers:
  - "github"       # Matches text containing "github"
  - "PR"           # Matches text containing "PR"
  - "pull request" # Matches text containing "pull request"
  - "code"         # Matches the content type "code"
  - "error"        # Matches the content type "error"
  - "image"        # Matches screenshot/image processing
```

Content types you can trigger on: `url`, `error`, `code`, `json`, `foreign`, `long_text`, `image`, `email`, `calendar`, `document`, `audio`, `transcription`.

### Tools

The `tools` field tells Ghost which tools this skill needs. When a skill is matched, Ghost narrows the tool registry to only the listed tools (plus `memory_search`, `memory_save`, and `notify` which are always available).

If `tools` is empty, the full tool registry is available.

```yaml
tools:
  - "shell_exec"        # Execute shell commands
  - "file_read"         # Read files
  - "file_write"        # Write files
  - "file_search"       # Search for files
  - "web_fetch"         # Fetch URLs
  - "web_search"        # Search the web
  - "browser"           # Full browser automation
  - "notify"            # System notifications
  - "app_control"       # Open applications
  - "clipboard_read"    # Read clipboard
  - "clipboard_write"   # Write to clipboard
  - "generate_image"    # AI image generation
  - "memory_search"     # Search memory
  - "memory_save"       # Save to memory
```

### Model Override

Skills can specify a preferred LLM model via the `model` frontmatter field. This is useful for skills that need stronger reasoning or specific provider capabilities.

```yaml
model: "google/gemini-2.5-pro"
```

Users can override a skill's model from the dashboard's skill detail panel (Skills → click a skill → Model dropdown). Config overrides take precedence over frontmatter values.

Priority: config override > frontmatter `model` > global default model.

### Requirements

Requirements let you declare what a skill needs to function. The dashboard shows checkmark/cross status for each requirement and marks skills as ineligible if requirements aren't met.

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

Skills are matched in priority order (highest first). If multiple skills match the same message, higher-priority skills appear first in the system prompt.

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
description: "Does something useful when you ask about specific topics"
triggers:
  - "my keyword"
  - "another trigger"
tools:
  - "shell_exec"
  - "web_fetch"
priority: 5
---

# My Custom Skill

When the user asks about "my keyword", follow these steps:

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

Send a message containing one of your trigger keywords. Ghost should match your skill and follow your instructions.

## Writing Effective Skills

### Be Specific

Tell the LLM exactly what to do, step by step. Vague instructions produce vague results.

```markdown
# Bad
Help the user with their email.

# Good
1. Use `shell_exec` to run `himalaya list --page-size 5` to check recent emails
2. Parse the output and present a summary of unread messages
3. If the user mentions an email address, draft a reply template
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

- **Local Skills tab** — Browse all loaded skills grouped by source (Bundled, User, Other)
- **GhostHub Registry tab** — Search and install community skills from the public registry
- **Search** across all skills by name, description, or trigger
- **Filter** by status (Eligible, Disabled, Missing Requirements)
- **Enable/Disable** toggle on each skill card
- **Edit** skill content directly in the browser
- **Model override** — Set a specific LLM model per skill
- **Requirements** status with checkmark/cross indicators for each binary and environment variable

Disabled skills are stored in `config.json` under `disabled_skills` and are excluded from matching even if their triggers hit.

## Skill Discovery Directories

| Directory | Priority | Description |
|---|---|---|
| `<project>/skills/` | Bundled | Ships with Ghost, updated with the codebase |
| `~/.ghost/skills/` | User | Your custom skills + installed registry skills, persisted across updates |

Both directories are scanned for `SKILL.md` files in subdirectories:

```
skills/
  my-skill/SKILL.md        ✓ Found (subdirectory)
  standalone/SKILL.md       ✓ Found (subdirectory)
```

The loader reloads skills every 30 seconds, so changes take effect without restarting Ghost.
