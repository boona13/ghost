# Ghost Browser Migration: Playwright to PinchTab

## Overview

Replace all Playwright-based browser automation in Ghost with PinchTab (`https://github.com/pinchtab/pinchtab`). PinchTab is a standalone Go binary that exposes browser control via HTTP API. Ghost will talk to it with plain `requests` calls -- no Playwright dependency, no thread-affinity hacks, no Chromium download.

**Why:**
- Current Playwright integration (`ghost_browser.py`) is broken and unstable
- Thread-affinity workaround (dedicated worker thread + queue) adds complexity
- Single browser instance, no profile isolation
- No stealth -- just a user-agent string
- Playwright + Chromium is a ~150MB dependency
- Snapshot truncation at 6000 chars loses critical UI elements on complex pages

**What PinchTab gives us:**
- Simple HTTP API -- `requests.get()`/`requests.post()` from any thread
- Multi-instance with persistent profiles (login once, stay logged in across restarts)
- Built-in stealth injection at CDP level
- Headless by default (no windows popping up during autonomous tasks)
- ~22MB standalone binary, zero Python dependencies
- Token-efficient snapshots (800 tokens/page vs thousands)
- Daemon model -- browser lifecycle managed externally
- Shorthand routes for simple single-instance workflows

---

## Files to Touch

### Primary (must change)

| File | What to do |
|------|------------|
| **`ghost_browser.py`** | **Full rewrite.** Replace all Playwright code with PinchTab HTTP API calls. This is the main work. |
| **`ghost.py`** | Update config defaults, add PinchTab health check at startup |
| **`ghost_browser_use.py`** | **Delete or gut.** browser-use depends on Playwright. Already disabled in ghost.py. |
| **`ghost_canvas.py`** | Replace the `screenshot()` method (lines 212-224) which uses `playwright.sync_api` directly |
| **`ghost_dashboard/routes/browser_use.py`** | Mark as unavailable (browser-use is gone) |
| **`requirements.txt`** | Remove `playwright` and `browser-use` comments/entries |
| **`install.sh`** | Replace Playwright install step with PinchTab install |
| **`install.ps1`** | Same -- replace Playwright install with PinchTab |

### Secondary (text/docs references only)

| File | What to do |
|------|------------|
| `ghost_autonomy.py` | Update docstring: "ghost_browser.py -- Playwright browser automation" -> "PinchTab browser automation" (line ~364) |
| `ghost_pr.py` | Same docstring reference (line ~131) |
| `ghost_evolve.py` | `ghost_browser.py` is in the high-risk file list (line ~186) -- keep it there |

---

## PinchTab API Reference (Verified)

Base: `http://localhost:9867`

### Hierarchy: Server → Instances → Tabs

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| **Profiles** | | |
| `/profiles` | GET | List profiles |
| `/profiles` | POST | Create profile `{name, description}` → `{id, name, status}` |
| `/profiles/{id}` | GET | Get profile info |
| `/profiles/{id}` | DELETE | Delete profile |
| **Instances** | | |
| `/instances` | GET | List all instances |
| `/instances/start` | POST | Start instance `{profileId?, mode}` → `{id, profileId, port, headless, status}` |
| `/instances/{id}/stop` | POST | Stop instance |
| `/instances/{id}/tabs/open` | POST | Open new tab `{url}` → `{tabId}` |
| **Tabs** | | |
| `/tabs` | GET | List tabs (`?instanceId=` filter) |
| `/tabs/{tabId}/navigate` | POST | Navigate tab `{url}` → `{tabId, title, url}` |
| `/tabs/{tabId}/snapshot` | GET | Accessibility tree `?filter=interactive` → `{nodes: [{ref, role, name}]}` |
| `/tabs/{tabId}/text` | GET | Extract page text |
| `/tabs/{tabId}/action` | POST | Single action `{kind, ref, ...}` → `{success, result}` |
| `/tabs/{tabId}/actions` | POST | Batch actions |
| `/tabs/{tabId}/screenshot` | GET | Screenshot as PNG |
| `/tabs/{tabId}/pdf` | GET | Save as PDF |
| `/tabs/{tabId}/evaluate` | POST | Run JavaScript `{expression}` |
| `/tabs/{tabId}/cookies` | GET/POST | Cookie access |
| `/tabs/{tabId}/lock` | POST | Lock tab for exclusive access |
| `/tabs/{tabId}/unlock` | POST | Unlock tab |
| `/tabs/{tabId}/close` | POST | Close tab |
| **Shorthand (auto-routes to current instance)** | | |
| `/navigate` | POST | Navigate current tab |
| `/snapshot` | GET | Snapshot current tab |
| `/action` | POST | Action on current tab |
| `/text` | GET | Text from current tab |

### Key response formats

**Instance start:**
```json
{"id": "inst_0a89a5bb", "profileId": "prof_278be873", "port": "9868", "headless": true, "status": "starting"}
```

**Snapshot:**
```json
{"nodes": [{"ref": "e0", "role": "link", "name": "Skip to content"}, {"ref": "e14", "role": "button", "name": "Search or jump to…"}]}
```

**Action (click):**
```json
{"success": true, "result": {"clicked": true}}
```

**Navigate:**
```json
{"tabId": "CDP_TARGET_ID", "title": "Page Title", "url": "https://example.com"}
```

---

## Migration Checklist

- [x] Verify PinchTab API against actual documentation
- [ ] Install PinchTab (`curl -fsSL https://pinchtab.com/install.sh | bash`)
- [ ] Rewrite `ghost_browser.py` -- remove Playwright, add PinchTab HTTP calls
- [ ] Keep `build_browser_tools()` and `browser_stop()` function signatures identical
- [ ] Keep `_validate_url()` and `_wrap_external()` security functions
- [ ] Add persistent profile support (login state survives restarts)
- [ ] Update `ghost_canvas.py` screenshot method
- [ ] Delete or disable `ghost_browser_use.py`
- [ ] Update `ghost_dashboard/routes/browser_use.py`
- [ ] Update `install.sh` / `install.ps1` -- replace Playwright with PinchTab
- [ ] Remove Playwright from `requirements.txt`
- [ ] Update docstrings in `ghost_autonomy.py`, `ghost_pr.py`
- [ ] Add `pinchtab_url` / `pinchtab_profile` to Ghost config defaults
- [ ] Add PinchTab health check to Ghost startup
