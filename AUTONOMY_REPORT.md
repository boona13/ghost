# Ghost Autonomy & Self-Correction Report

**Date:** March 9, 2026
**Tested on:** OpenRouter / moonshotai/kimi-k2.5 (primary)

---

## What Was Done

Three layers of improvements to make Ghost more autonomous, persistent, and self-correcting.

### 1. LLM-based Self-Correction Loop

**Files:** `ghost.py`, `ghost_dashboard/routes/chat.py`

When Ghost responds to a user, the system runs a lightweight LLM classifier on the response to detect "give-up" language (e.g., "I can't", "not possible", asking the user to do it themselves). If detected, the system automatically injects a coaching message and forces Ghost to retry with the next escalation level — up to 2 retries.

- **Classifier** (`ghost.py`): Uses `single_shot()` with a binary YES/NO prompt. A separate LLM call (temperature 0, max 5 tokens) decides if Ghost gave up or delivered a real result.
- **Bug fix:** `single_shot()` returns a string, not a `ToolLoopResult`. Original code did `result.text` on a string — fixed to just `result`.
- **Self-correction loop** is in both `ghost.py` (inbound message handler + ask command) and `chat.py` (dashboard chat handler).

### 2. Mandatory Escalation Ladder (Prompt Engineering)

**Files:** `ghost.py`, `ghost_dashboard/routes/chat.py`

Restructured the system prompts to include a **MANDATORY ESCALATION LOOP** with 5 levels:

| Level | Strategy | When to use |
|-------|----------|-------------|
| 1 | Direct tools | web_fetch, web_search, shell_exec |
| 2 | Research | web_search for "how to do X programmatically" |
| 3 | Python sandbox | Install packages in `~/.ghost/sandbox/`, write and run scripts |
| 4 | Browser automation | ONLY for interactive/visual tasks (login, forms, clicking) |
| 5 | Combine | Chain approaches |

Also added:
- **PRE-REPLY SELF-CHECK** — count user's questions, verify all answered with data, strip upsell language
- **COMPLETION RULE** — forbids "if you want", "let me know", "I can also"
- Removed all test-specific "KNOWN SOLUTIONS" sections to prevent prompt cheating

### 3. Browser Guardrail

**Files:** `ghost_browser.py`, `ghost.py`, `ghost_dashboard/routes/chat.py`

The original prompts told Ghost to use the browser as a fallback for `web_fetch`. This caused Ghost to open a visible Chromium window on the user's screen when extracting data (e.g., YouTube transcripts). Fixed with a three-layer guardrail:

- **Tool description** (`ghost_browser.py`): Warning directly in the browser tool definition — *"NEVER use for silent data extraction. Use shell_exec with Python scripts in ~/.ghost/sandbox/ instead."*
- **System prompts**: Changed escalation instructions to "escalate to Python sandbox, NOT browser" when web_fetch returns limited content.
- **Coaching message** (`ghost.py`): Updated to "Do NOT open the browser — extract data programmatically."

### 4. Rate Limit Fast-Fallback

**File:** `ghost_loop.py`

Reduced `RATE_LIMIT_MAX_RETRIES` from 6 to 1 and `RATE_LIMIT_BASE_DELAY` from 5.0s to 3.0s. On a 429, Ghost now retries once then immediately switches to the next fallback model instead of waiting minutes.

---

## Test Methodology

**Script:** `test_ghost_blind.py`

- 10 blind autonomy tests
- Each test runs in its own isolated chat session (cleared between tests)
- No hints about libraries, APIs, or implementation approaches in any prompt
- 15-second delay between tests to reduce API pressure
- 300-second timeout per test

**Evaluation criteria:**
- Result length > 50 characters
- No give-up phrases ("I can't", "unable to", "please provide", etc.)
- No upsell phrases ("if you want", "let me know", "I can also")

### The 10 Tests

| # | Test | What it checks |
|---|------|---------------|
| 1 | YouTube transcript | Extract video transcript without being told how |
| 2 | Crypto prices | Find live data and do math (BTC→ETH conversion) |
| 3 | GitHub stars | Query an API and compare numbers |
| 4 | Bar chart image | Research data, generate visualization, save file |
| 5 | QR code + verify | Generate AND verify (round-trip) a QR code |
| 6 | PDF extract | Download and parse a PDF |
| 7 | HN top stories | Fetch and parse a live API |
| 8 | Multi-part repo comparison | Answer 3 sub-questions from 2 sources |
| 9 | Word frequency | Fetch text, process it, remove stop words |
| 10 | Weather data | Get live weather for 3 cities |

---

## Results: 9/10 Pass

| # | Test | Verdict | Steps | Time | Tools Used |
|---|------|---------|-------|------|------------|
| 1 | YouTube transcript | **PASS** | 15 | 228.8s | shell_exec, web_fetch, browser(2x), file_write, file_read |
| 2 | Crypto prices | **PASS** | 3 | 52.6s | web_search, web_fetch, shell_exec |
| 3 | GitHub stars | **PASS** | 5 | 26.4s | shell_exec(3x), web_fetch(2x) |
| 4 | Bar chart image | **PASS** | 5 | 71.4s | web_search(3x), shell_exec, file_write |
| 5 | QR code + verify | **FAIL** | 5 | 300.6s (timeout) | shell_exec, file_write, shell_exec(2x), file_write |
| 6 | PDF extract | **PASS** | 3 | 58.9s | — |
| 7 | HN top stories | **PASS** | 1 | 29.2s | — |
| 8 | Multi-part repo comparison | **PASS** | 7 | 157.6s | — |
| 9 | Word frequency | **PASS** | 5 | 202.4s | — |
| 10 | Weather data | **PASS** | 3 | 64.7s | shell_exec(3x) |

**Total: 9 PASS | 0 WARN | 1 FAIL**

---

## Current Problems

### 1. Browser guardrail is not airtight (Test 1)

The YouTube test still made 2 browser calls despite the guardrail. The tool description warning reduced it from 6 calls to 2, but kimi-k2.5 doesn't always follow tool description constraints. A harder fix would be code-level interception in the browser tool handler — rejecting navigate calls when the task is data extraction and returning an error directing Ghost to sandbox.

### 2. QR code test timed out (Test 5)

Ghost used the right tools (shell_exec + file_write) but took too long — 150 seconds with 0 steps before the first tool call, then only 5 steps before the 300s timeout. The QR task itself is simple; the bottleneck is LLM latency on the initial planning step.

### 3. Test pass criteria are shallow

The script checks `len(result) > 50` and absence of give-up phrases. It does not verify:
- Whether the bar chart image is actually valid
- Whether the word frequencies are correct
- Whether the YouTube transcript matches the actual video
- Whether the QR code actually encodes the right text

A stronger test suite would need content verification (checking specific keywords, validating files exist, etc.).

### 4. YouTube test is slow (228.8s)

15 steps for a task that should take 3-4 steps with `youtube-transcript-api`. Ghost researches, tries multiple approaches, and eventually succeeds but the path is inefficient. A permanent built-in `youtube_transcript` tool (via the evolve system) would make this instant.

### 5. Some tests are slow overall

Tests 8 (157.6s) and 9 (202.4s) take 2-3 minutes for relatively simple tasks. This is primarily LLM response latency from kimi-k2.5, not tool execution time.
