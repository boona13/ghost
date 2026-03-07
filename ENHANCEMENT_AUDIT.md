# Ghost Enhancement Audit Report

**Date:** March 7, 2026
**Scope:** Audit of 4 proposed enhancements vs actual implementation

---

## Overall Scorecard

| Pattern | Proposed Items | Fully Implemented | Partial | Missing | Grade |
|---------|:-:|:-:|:-:|:-:|:-:|
| 1. Aider Repo Map | 7 | 5 | 1 | 1 | **A-** |
| 2. jCodeMunch Symbols | 9 | 6 | 2 | 1 | **A-** |
| 3. Copilot JIT Memory | 8 | 5 | 2 | 1 | **B+** |
| 4. Ralph Multi-Phase | 14 | 13 | 0 | 1 | **A** |
| **TOTAL** | **38** | **29** | **5** | **4** | |

---

## 1. Aider's Repo Map Pattern — Grade: A-

**Goal:** Replace the static `_GHOST_SYSTEM_MAP` (85 lines of manually-written module descriptions that go stale) with a dynamic, AST-generated repo map that auto-regenerates after every evolution.

**Primary file:** `ghost_code_index.py`

| # | Proposed | Status | Location | Notes |
|---|----------|--------|----------|-------|
| 1 | Dynamic AST-based map replaces static `_GHOST_SYSTEM_MAP` | **IMPLEMENTED** | `ghost_code_index.py` full file, `ghost_autonomy.py:402-422` | `generate_repo_map()` builds map via `ast.parse()`; `get_ghost_system_map()` returns dynamic + static dashboard map |
| 2 | Covers ALL classes, never stale | **IMPLEMENTED** | `ghost_code_index.py:279-314` | Indexes 1964+ symbols across 120+ files at build time |
| 3 | Regenerates after `evolve_deploy` | **IMPLEMENTED** | `ghost_evolve.py:1721-1724` | `get_code_index().rebuild()` called after deploy |
| 4 | Injected into evolution prompts as `{repo_map}` | **IMPLEMENTED** | `ghost_autonomy.py:1859, 1958, 2055, 2155` | All 4 phases (SCOUT/IMPLEMENT/VERIFY/FIX) receive a fresh map |
| 5 | Token budget mechanism | **IMPLEMENTED** | `ghost_code_index.py:126-136` | Default 3000 tokens (`char_budget = token_budget * 4`), configurable via `repo_map_token_budget` |
| 6 | PageRank dependency ranking | **PARTIAL** | `ghost_code_index.py:539-575` | Uses import-based in-degree ranking, not full iterative PageRank |
| 7 | Dashboard/JS/CSS map dynamic | **NOT DONE** | `ghost_autonomy.py:356-398` | `_GHOST_SYSTEM_MAP_DASHBOARD` (~42 lines) is still manually maintained for non-Python routes |

### Gaps

- **PageRank:** Only in-degree ranking (count of imports), not the iterative PageRank algorithm proposed. The simpler approach works but doesn't capture transitive importance.
- **Dashboard static section:** Non-Python files (routes, CSS, JS pages) still have a manually maintained map. The AST index only covers Python.

---

## 2. jCodeMunch Symbol Indexing — Grade: A-

**Goal:** Index every symbol with qualified names and byte offsets so the LLM can look up a single class/method (~200 tokens) instead of reading an entire file (~15,000 tokens).

**Primary file:** `ghost_code_index.py`

| # | Proposed | Status | Location | Notes |
|---|----------|--------|----------|-------|
| 1 | Symbols stored with qualified names | **IMPLEMENTED** | `ghost_code_index.py:55, 327-329` | Format: `ghost_loop.py::ToolRegistry.run#method` |
| 2 | Byte offsets for direct file seeking | **IMPLEMENTED** | `ghost_code_index.py:55-56, 315-324` | `byte_offset` and `byte_length` computed from AST line numbers |
| 3 | `code_symbol_lookup` tool for LLM | **IMPLEMENTED** | `ghost_code_index.py:635, 686-709` | Returns ~200 tokens vs ~15,000 for `file_read` |
| 4 | `code_symbol_list` tool for module overview | **IMPLEMENTED** | `ghost_code_index.py:668, 711-727` | Lists all public symbols with signatures in a file |
| 5 | O(1) file read via byte seek | **IMPLEMENTED** | `ghost_code_index.py:206-208` | `raw[sym.byte_offset:sym.byte_offset + sym.byte_length]` |
| 6 | O(1) index lookup via hashmap | **PARTIAL** | `ghost_code_index.py:182-185, 491-520` | Symbol lookup SCANS `_all_symbols` list (O(n)), no `symbol_id` → `SymbolEntry` hashmap |
| 7 | Nested class qualified IDs correct | **PARTIAL** | `ghost_code_index.py:287-294, 499-506` | Stored correctly (`Outer.Inner.method#method`), but name-based lookup for `Outer.Inner.method` fails because `_find_symbol` only checks immediate `parent_class` |
| 8 | Rebuild after deploy | **IMPLEMENTED** | `ghost_evolve.py:1721-1725` | `get_code_index().rebuild()` in `EvolutionEngine.deploy()` |
| 9 | Token savings instrumentation | **NOT DONE** | — | No logging or metrics to measure actual token savings vs `file_read` |

### Gaps

- **O(n) lookup:** `_find_symbol()` iterates the entire symbol list. Should build a `dict` keyed by `symbol_id` for O(1) access.
- **Nested class bug:** Looking up `Outer.Inner.method` by name fails because the code checks `parent_class == "Outer"` but the stored `parent_class` is `"Inner"` (the immediate parent, not the full chain).
- **No metrics:** The proposal estimated 99% token reduction on exploration but there's no instrumentation to verify this in practice.

---

## 3. GitHub Copilot JIT Memory — Grade: B+

**Goal:** Store memories with code-location citations. When a memory is retrieved, verify the citations in real-time against the current codebase. If the code changed, flag the memory as stale or auto-correct it.

**Primary file:** `ghost_memory.py`

| # | Proposed | Status | Location | Notes |
|---|----------|--------|----------|-------|
| 1 | `citations` column in memory schema | **IMPLEMENTED** | `ghost_memory.py:85, 107` | JSON array: `[{"file": "ghost_loop.py", "line": 42, "snippet": "class Foo:"}]` |
| 2 | Citations attached when saving | **IMPLEMENTED** | `ghost_memory.py:94-119, 434-441` | `memory_save` tool accepts `citations` parameter |
| 3 | Citations verified on retrieval | **IMPLEMENTED** | `ghost_memory.py:139-182, 394-396` | `verify_citations()` reads file:line, checks if snippet still matches (±2 line window) |
| 4 | `[VERIFIED]` / `[STALE]` status in results | **IMPLEMENTED** | `ghost_memory.py:395-399, 181-182` | Appended to each memory result string |
| 5 | Auto-expiration (28 days default) | **IMPLEMENTED** | `ghost_memory.py:124-136`, `ghost.py:985-989` | `expire_old_memories()` runs on daemon startup, configurable via `memory_expiry_days` |
| 6 | Stale memories auto-discarded or corrected | **PARTIAL** | `ghost_memory.py:394-408` | Only FLAGGED with `[STALE]` tag, never auto-deleted or auto-corrected in the DB |
| 7 | Self-healing: agents store corrected versions | **PARTIAL** | `ghost_memory.py:402-408` | Prompt says "Consider saving a corrected version" but there's no enforced self-healing flow |
| 8 | Dashboard API shows verification status | **NOT DONE** | `ghost_dashboard/routes/memory.py` | `/api/memory/search` and `/api/memory/recent` don't call `verify_citations()` |

### Gaps

- **No auto-discard/correction:** The Copilot blog specifically says "agents found the contradictions and stored corrected versions." In Ghost, stale memories are only flagged with a text note — they persist in the DB indefinitely (until the 28-day expiry) and will be returned on every relevant search, each time flagged as stale but never removed.
- **Self-healing is passive:** The prompt suggests the LLM should save a corrected memory, but this isn't enforced. The LLM can ignore the suggestion. A stronger implementation would automatically queue a correction task or at minimum delete the stale memory after N retrievals without correction.
- **Dashboard blind spot:** Users browsing memories in the dashboard see no indication of citation validity.

---

## 4. Ralph Loop Pattern (Multi-Phase Evolution) — Grade: A

**Goal:** Replace the single continuous evolution loop (where context degrades via compaction) with multiple phases, each starting with a fresh context window. State between phases is persisted through scratch files on disk.

**Primary file:** `ghost_autonomy.py`

| # | Proposed | Status | Location | Notes |
|---|----------|--------|----------|-------|
| 1 | `run_phased_evolution()` orchestrator | **IMPLEMENTED** | `ghost_autonomy.py:1753` | Full multi-phase orchestrator with error handling |
| 2 | Fresh `ToolLoopEngine` per phase | **IMPLEMENTED** | `ghost_autonomy.py:1520-1539` | `_build_phase_engine(daemon)` creates new engine each time |
| 3 | Separate prompts: SCOUT, IMPLEMENT, VERIFY, FIX | **IMPLEMENTED** | `ghost_autonomy.py:1817, 1925, 2034, 2134` | 4 distinct prompt constants with phase-specific instructions |
| 4 | Scratch files for state persistence | **IMPLEMENTED** | `ghost_autonomy.py:1465-1467` | `~/.ghost/evolve/scratch/auto.md` with structured sections |
| 5 | SCOUT writes plan (files, signatures, patterns, mistakes) | **IMPLEMENTED** | `ghost_autonomy.py:1842-1854` | Prompt requires: Files to Modify, Key Signatures, Patterns to Follow, Mistakes to Avoid |
| 6 | IMPLEMENT reads scratch as context | **IMPLEMENTED** | `ghost_autonomy.py:1966-1986` | `{scratch_content}` injected into `_IMPLEMENT_PROMPT` |
| 7 | VERIFY reads scratch + reviews changes | **IMPLEMENTED** | `ghost_autonomy.py:2064-2079` | Reads scratch via `{scratch_content}`, told to file_read each changed file |
| 8 | FIX phase for rejected PRs | **IMPLEMENTED** | `ghost_autonomy.py:2132-2213` | `_run_fix_phase()` uses `evolve_resume`, applies targeted patches |
| 9 | Iteration tracking per feature (max retries) | **IMPLEMENTED** | `ghost_autonomy.py:1692-1722` | `attempt_counts.json`, default max 5 attempts |
| 10 | Cross-feature learnings (Ralph's progress.txt) | **IMPLEMENTED** | `ghost_autonomy.py:1467, 1722-1754` | `learnings.md` append-only file, injected into SCOUT and IMPLEMENT prompts |
| 11 | `skip_evolve_cleanup` between phases | **IMPLEMENTED** | `ghost_autonomy.py:2004, 2096, 2196` | Prevents `ToolLoopEngine` from rolling back evolution state between phases |
| 12 | `_guard_evolve_plan_once` | **IMPLEMENTED** | `ghost_autonomy.py:1579-1610` | Blocks duplicate `evolve_plan` calls in IMPLEMENT phase |
| 13 | Step budgets per phase | **IMPLEMENTED** | `ghost_autonomy.py:1888, 1990, 2082, 2182` | SCOUT: 30, IMPLEMENT: 20, VERIFY: 30, FIX: 25 |
| 14 | Orchestrator flow: SCOUT → IMPLEMENT/FIX → VERIFY | **IMPLEMENTED** | `ghost_autonomy.py:1771-1810` | Resume detection routes to FIX; fresh features go to IMPLEMENT |

### Gaps

- **Config/code mismatch:** `ghost_config_tool.py` describes `implement_max_steps` default as 80 but the actual code default is 20. Same mismatch for verify (40 vs 30) and fix (40 vs 25). This could confuse users changing config values.
- **VERIFY doesn't use explicit diff:** The proposal said VERIFY should read "scratch + diff." The implementation tells the LLM to `file_read` each changed file rather than providing a `git diff` output directly.

---

## Performance Observations (Live Runs)

### Phased Evolution Timing

| Run | Feature | Phases (steps) | Total Time | Outcome |
|-----|---------|----------------|:----------:|---------|
| Run 1 (old code) | Audit logging | S:25 + I:46 + V:9 = 80 | **17.1 min** | PR submitted, blocked |
| Run 3 (optimized v1) | Audit logging | S:28 + I:19 + V:24 = 71 | **15.5 min** | VERIFY hit step cap |
| Run 4 (optimized v2) | Audit logging | S:27 + F:19 = 46 | **8.8 min** | Graceful fail (lost branch) |
| Run 5 (optimized v2) | Benchmark Timer | S:28 + I:17 + V:14 = 59 | **16.0 min** | Full cycle, PR blocked |

### IMPLEMENT Phase Improvement

- **Before fix:** 46 steps, ~10 min (wasted 40 steps trying to submit PR)
- **After fix:** 17 steps, ~3 min (core work done in 4 steps)
- **Improvement:** 63% step reduction

### Code Quality (Phased Pipeline Only)

| PR | Feature | Verdict | Critical Issues | Root Causes |
|----|---------|---------|:---------------:|-------------|
| pr-03f5e13723 | Audit logging fix | rejected | 2 | Logic bug (check-after-mutate), false success audit |
| pr-d476f6f72b | Benchmark Timer | blocked | 3 | Fake `exec()` sandbox, broken thread timeout, inaccurate memory measurement |

**0 out of 2 PRs approved** from the phased pipeline.

### Systemic Code Quality Issues (All 24 Blocked PRs)

| Category | Count | Description |
|----------|:-----:|-------------|
| Missing imports/symbols/files | 11 | References functions, enum values, or modules that don't exist |
| Security vulnerabilities | 7 | `exec()` sandboxes, no path validation, SQL injection, path traversal |
| Dead code / unreachable | 7 | Creates modules never wired into Ghost |
| Duplicated logic | 6 | Reimplements what already exists |
| Bugs / syntax errors | 5 | Missing braces, broken conditional logic |
| API/interface mismatch | 5 | Frontend expects keys the backend doesn't return |

---

## Remaining Gaps Summary

### High Priority

1. **Memory self-healing is passive** — Stale memories are flagged but never auto-corrected. This was the core value proposition of the Copilot pattern (measured at +7% PR merge rate). The fix: auto-delete stale memories after N failed verifications, or queue a correction task.

2. **Symbol index lookup is O(n)** — `_find_symbol()` scans the full list. Add a `dict` keyed by `symbol_id` for O(1) access.

3. **Nested class lookup bug** — Looking up `Outer.Inner.method` by name fails because `parent_class` stores only the immediate parent (`Inner`), not the full chain.

4. **Config/code defaults mismatch** — `ghost_config_tool.py` describes different step budget defaults than the actual code uses (e.g., implement: 80 in config vs 20 in code).

### Medium Priority

5. **No PageRank** — Using simpler in-degree ranking instead of iterative PageRank. Works but doesn't capture transitive importance.

6. **Dashboard memory API doesn't verify citations** — `/api/memory/search` returns raw results without calling `verify_citations()`.

7. **No token savings instrumentation** — No metrics to measure actual benefit of `code_symbol_lookup` vs `file_read`.

### Low Priority

8. **Dashboard map static** — Non-Python file descriptions (`_GHOST_SYSTEM_MAP_DASHBOARD`) still manually maintained.

9. **VERIFY phase doesn't use git diff** — Tells LLM to `file_read` changed files instead of providing an explicit diff.
