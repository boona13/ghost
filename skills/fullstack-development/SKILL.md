---
name: fullstack-development
description: "End-to-end implementation standards: backend + frontend + CSS + verification. Never ship incomplete work."
triggers:
  - implement
  - feature
  - add
  - create
  - build
  - new endpoint
  - new page
  - new tool
  - integrate
  - wire up
  - connect
  - full stack
  - fullstack
  - end to end
tools:
  - file_read
  - file_write
  - file_search
  - shell_exec
  - browser
  - evolve_plan
  - evolve_apply
  - evolve_test
  - evolve_deploy
priority: 80
---

# Full-Stack Development Standards

Every feature you implement MUST be complete across all layers. Partial work is a bug.

## The Completeness Principle

Before calling `task_complete`, verify EVERY layer is done:

### Layer Checklist

| Layer | What to check |
|-------|--------------|
| **Backend** | New route/endpoint exists, returns correct JSON, handles errors |
| **Tool** | If new tool needed: `build_*_tools()` created, registered in `ghost.py` |
| **Frontend JS** | DOM elements created, event listeners bound, API calls wired, state managed |
| **CSS** | Every new element styled, hover/active states, transitions, responsive |
| **Integration** | Backend ↔ Frontend data flow working end-to-end |
| **Verification** | Browsed to page, elements visible, interactions tested |

### The 5-Step Implementation Process

```
STEP 1: PLAN — Read all files you'll modify. Understand current state.
   file_read every file listed in evolve_plan BEFORE writing any patches.

STEP 2: IMPLEMENT — Apply all changes across all layers.
   Backend route → Frontend JS → CSS → all in one evolution.

STEP 3: TEST — Run evolve_test to catch syntax/import errors.
   If test fails, fix immediately. Do not deploy broken code.

STEP 4: DEPLOY — evolve_deploy triggers restart.
   Wait for restart to complete.

STEP 5: VERIFY — Browse to the page and test.
   Navigate to http://localhost:3333/#<page>
   Snapshot to check elements exist.
   Click/interact to test functionality.
   If ANYTHING is wrong → fix with new evolution, DO NOT call task_complete.
```

## Implementation Depth Requirements

### For a New API Endpoint

1. Add the route function in the correct `routes/<page>.py`
2. Handle `GET` and `POST` as needed
3. Validate request data (don't trust input)
4. Return consistent JSON: `{"ok": true, ...}` or `{"ok": false, "error": "..."}`
5. Add to the frontend JS that will call it
6. Test with the browser tool: navigate, interact, verify response shows in UI

### For a New Dashboard Feature

1. **Backend**: Route with API endpoint(s)
2. **Frontend**: JS module additions (or new page module)
3. **HTML**: DOM elements created via JS (template literals in `render()`)
4. **CSS**: All classes referenced in HTML must exist in `dashboard.css`
5. **Events**: Every button/input has event listeners
6. **State**: Variables declared, updated correctly, cleared on reset
7. **Error handling**: Try/catch on API calls, error messages shown to user
8. **Verification**: Browse and test after deploy

### For Modifying Existing Features

1. `file_read` the target file(s) FIRST
2. Understand the existing code structure before patching
3. Patches must be precise — include enough context for unique matching
4. Don't break adjacent functionality
5. Test the ENTIRE page, not just your change

## Common Failure Modes (AVOID THESE)

### The "Reference Error" Trap
**Problem**: You add code that uses a variable/function that doesn't exist yet.
**Fix**: When adding code that references `attachments`, `renderAttachments()`, etc. — define them FIRST, use them SECOND. Read the scope carefully.

### The "Half-Wired" Trap
**Problem**: Backend endpoint exists but frontend never calls it, or frontend calls it but UI doesn't display the result.
**Fix**: Trace the FULL data flow: User action → JS event → API call → Backend handler → Response → JS handler → DOM update. Every link in this chain must exist.

### The "Invisible Element" Trap
**Problem**: JS creates DOM elements but CSS classes are missing, so elements are unstyled or invisible.
**Fix**: For every `className` you assign in JS, verify the corresponding CSS rule exists.

### The "Orphaned Function" Trap
**Problem**: You define `renderAttachments()` but nobody calls it, or you add an event listener for a button that isn't in the DOM.
**Fix**: After writing code, mentally trace: who calls this function? Is the DOM element this listener targets actually created?

## Code Quality Standards

### Python
- Type hints for function parameters (at minimum for public APIs)
- Docstrings for classes and public methods
- Error handling: try/except with specific exceptions, not bare `except:`
- Use pathlib for file paths
- Return strings from tool execute functions
- **Dependencies**: When you `pip install` a package via `shell_exec`, `requirements.txt` is automatically updated with the pinned version. **Do NOT manually edit `requirements.txt` after pip install** — the auto-sync handles it and manual edits will create duplicates.

### JavaScript
- Use `const` by default, `let` only when mutation needed
- Event delegation for dynamically created elements
- Clean up: remove event listeners and timers when navigating away
- Handle API errors: show user-visible error messages
- Escape user content with `GhostUtils.escapeHtml()` before inserting into HTML

### CSS
- Follow existing naming convention: `.pagename-element`
- Include transitions for interactive elements
- Use the established color palette (no random hex codes)
- Test both with and without content (empty states)
- Ensure new elements don't break existing layout

## Testing with the Browser Tool

After any UI change, verify with the browser tool:

```
1. browser(action='navigate', url='http://localhost:3333/#<page>')
   → Wait for page to load

2. browser(action='snapshot')
   → Verify all expected elements appear in the accessibility tree
   → Check element names, roles, and states

3. browser(action='click', ref='<button_ref>')
   → Test interactive elements

4. browser(action='snapshot')
   → Verify the interaction produced the expected result

5. browser(action='console')
   → Check for JavaScript errors

6. If errors found → fix with new evolution → test again
```

**If the browser tool shows ANY issue — missing elements, JS errors, broken layout — you MUST fix it before calling `task_complete`.** A task is only done when the user can see and use the feature.
