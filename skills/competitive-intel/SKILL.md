---
name: competitive-intel
description: Research OpenClaw community and competitor landscape to improve Ghost
triggers:
  - openclaw
  - competitor
  - competitive
  - what are people using
  - popular features
  - feature gap
  - community research
  - user demand
  - growth hack
  - improve ghost
  - what should ghost have
  - missing feature
  - skill gap
tools:
  - web_search
  - web_fetch
  - browser_navigate
  - browser_snapshot
  - browser_click
  - file_read
  - file_write
  - memory_search
  - memory_save
  - shell_exec
  - evolve_plan
  - evolve_apply
  - evolve_test
  - evolve_deploy
  - log_growth_activity
  - add_action_item
content_types:
  - ask
  - long_text
priority: 75
---

# Competitive Intelligence — OpenClaw Research

You are Ghost, and **OpenClaw** is your primary competitor. This skill guides you through researching the OpenClaw ecosystem to discover features, patterns, and user workflows that Ghost should adopt or improve upon.

## OpenClaw Source Code

OpenClaw's source is public at **https://github.com/openclaw/openclaw**. Use `web_fetch` to read their code directly from GitHub — no local clone needed.

To read a specific file, use the raw URL pattern:
```
web_fetch https://raw.githubusercontent.com/openclaw/openclaw/main/<path>
```

**IMPORTANT: OpenClaw is written in Node.js / TypeScript (not Python).** Their code uses TypeScript classes, npm packages, pnpm, and Node >= 22. Ghost is Python. When studying their code, extract the **concept and logic**, then reimplement in Python using Ghost's patterns (`ghost_*.py` modules, `make_*()` tool builders, Flask blueprints). Never copy TypeScript code into Ghost or try to use their npm dependencies.

Key paths to fetch:
- `skills/` — All bundled skills (SKILL.md + TypeScript handlers)
- `src/hooks/` — Hook system (event-driven plugins, TypeScript)
- `src/tools/` — Built-in tools (TypeScript)
- `src/channels/` — Messaging channel integrations (TypeScript)
- `docs/` — Official documentation
- `README.md` — Feature overview and architecture

To browse directories, use:
```
web_fetch https://github.com/openclaw/openclaw/tree/main/skills
```

## Research Methodology

### Step 1: Online Community Research

Search for real user discussions, configurations, and pain points:

**GitHub:**
- `web_search("openclaw github issues feature request {current_year}")`
- `web_search("openclaw github discussions popular {current_year}")`
- `web_fetch("https://github.com/openclaw/openclaw/issues?q=is%3Aissue+sort%3Areactions-%2B1-desc")` (most upvoted issues)
- Use `web_fetch` on any GitHub issue/PR/discussion URL — it extracts clean content from GitHub pages

**Reddit / Forums:**
- `web_search("openclaw reddit setup configuration {current_year}")`
- `web_search("openclaw best skills workflow {current_year}")`
- `web_search("openclaw alternative personal AI assistant {current_year}")`

**X (Twitter):**
- `web_search("openclaw site:x.com tips tricks {current_year}")`
- Browse `browser_navigate("https://x.com/search?q=openclaw&f=live")` for real-time discussions

**Discord:**
- `web_search("openclaw discord showcase custom skill {current_year}")`
- Check their showcase channel discussions via web search

### Step 2: Identify High-Value Patterns

When reading community content, look for:

1. **Repeated configurations** — If 5+ users set up the same thing manually, Ghost should ship it built-in
2. **Feature requests with high upvotes** — Direct signal of user demand
3. **Pain points / complaints** — Things OpenClaw gets wrong that Ghost can get right
4. **Creative use cases** — Novel ways users are leveraging AI assistants that Ghost doesn't support
5. **Integration requests** — Services/APIs users want connected

### Step 3: Study OpenClaw's Implementation

For each interesting finding, fetch their source from GitHub:

```
web_fetch https://raw.githubusercontent.com/openclaw/openclaw/main/skills/<skill-name>/SKILL.md
```

Study their implementation pattern, then design a Ghost-native version that:
- Works with Ghost's tool registry pattern (`make_*()` returning tool dicts)
- Integrates with Ghost's dashboard (if UI-facing)
- Ships configured out of the box (no user setup needed)
- Leverages Ghost's unique advantages (self-evolution, browser automation, memory)

### Step 4: Prioritize and Implement

**Priority Matrix:**

| Priority | Criteria | Action |
|----------|----------|--------|
| P0 — Critical | Users actively complain about lacking this | Implement immediately via evolve |
| P1 — High | 10+ upvotes or repeated community requests | Add to next growth cycle |
| P2 — Medium | Nice-to-have, improves UX | Queue as action item |
| P3 — Low | Niche use case, few users | Document for later |

**Implementation checklist:**
1. `memory_search` for previous research on this topic (avoid duplicate work)
2. Study OpenClaw's implementation via `web_fetch` on GitHub
3. Design Ghost-native version (new `ghost_<feature>.py` + skill)
4. `evolve_plan` → `file_read` existing code → `evolve_apply` → `evolve_test` → `evolve_deploy`
5. `log_growth_activity` with what was implemented and why
6. `memory_save` the research findings for future reference

## Current Skill Gap Analysis

### Skills OpenClaw has that Ghost should evaluate:

**High-value targets (real user demand):**
- `voice-call` — Voice calling capability
- `coding-agent` — Dedicated coding assistance mode
- `session-logs` — Session logging and export
- `model-usage` — Token usage tracking and cost monitoring
- `healthcheck` — System health monitoring skill
- `skill-creator` — Meta-skill for creating new skills
- `canvas` — Visual workspace / live rendering
- `discord` / `slack` — Chat platform integrations
- `gh-issues` — GitHub Issues management

**Medium-value (niche but useful):**
- `camsnap` — Camera snapshot integration
- `oracle` — Knowledge base queries
- `gemini` — Gemini model integration
- `bear-notes` — Bear notes app integration
- `openhue` — Smart home (Philips Hue) control
- `sonoscli` / `songsee` — Music control

### Ghost's Unique Advantages (things OpenClaw lacks):
- Self-evolution engine
- Autonomous growth with cron routines
- Built-in social media growth (X)
- Self-healing crash recovery
- Integrated web dashboard
- Browser automation (Playwright)
- Competitive intelligence (this skill!)

## Output Format

After completing research, always produce:

1. **Findings Summary** — What you discovered, with sources
2. **Recommendation** — What Ghost should implement, prioritized
3. **Action** — Either implement it now (via evolve) or create an action item
4. **Growth Log Entry** — Record what you found via `log_growth_activity`
5. **Memory Save** — Persist findings via `memory_save` with tag "competitive-intel"

## Important Reminders

- Always use the **current year** in search queries (check date context)
- Never copy OpenClaw code verbatim — study patterns, implement Ghost-native
- Respect OpenClaw's MIT license but build original implementations
- Focus on what users ACTUALLY want, not what looks impressive on paper
- Remember: OpenClaw ships bare, Ghost ships batteries-included — that's the differentiator
