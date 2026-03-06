"""
Ghost Autonomy Engine — makes Ghost a self-improving, self-healing system.

Provides:
  - Growth routines (scheduled via cron) for proactive self-improvement
  - Action Items system for things only the user can do
  - Growth Log for tracking autonomous improvements
  - Self-repair on crash (reads crash_report.json, diagnoses, fixes)
  - Bootstrap function to register growth cron jobs
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from ghost_implementation_auditor_filters import build_implementation_auditor_candidate_report

GHOST_HOME = Path.home() / ".ghost"
ACTION_ITEMS_FILE = GHOST_HOME / "action_items.json"
GROWTH_LOG_FILE = GHOST_HOME / "growth_log.json"
CRASH_REPORT_FILE = GHOST_HOME / "crash_report.json"

PROJECT_DIR = Path(__file__).resolve().parent

DEFAULT_GROWTH_SCHEDULES = {
    "tech_scout":          "0 */12 * * *",
    "health_check":        "0 */2 * * *",
    "user_context":        "0 */4 * * *",
    "skill_improver":      "0 3 * * *",
    "soul_evolver":        "0 4 * * 0",
    "bug_hunter":          "0 */6 * * *",
    "competitive_intel":   "0 6 * * 1,4",
    "content_health":      "0 4 * * 0",
    "security_patrol":     "0 5 * * *",
    "visual_monitor":      "0 */8 * * *",
}

GROWTH_JOB_PREFIX = "_ghost_growth_"


# ═══════════════════════════════════════════════════════════════
#  ACTION ITEMS
# ═══════════════════════════════════════════════════════════════

class ActionItemStore:
    """CRUD for user-required action items."""

    def __init__(self):
        GHOST_HOME.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if ACTION_ITEMS_FILE.exists():
            try:
                return json.loads(ACTION_ITEMS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, items: List[Dict]):
        ACTION_ITEMS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def add(self, title: str, description: str, category: str = "general",
            priority: str = "info") -> Dict:
        items = self._load()
        for item in items:
            if item.get("title") == title and item.get("status") == "pending":
                item["_duplicate"] = True
                return item
        item = {
            "id": uuid.uuid4().hex[:10],
            "title": title,
            "description": description,
            "category": category,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        items.insert(0, item)
        self._save(items)
        return item

    def resolve(self, item_id: str) -> bool:
        items = self._load()
        for item in items:
            if item["id"] == item_id:
                item["status"] = "resolved"
                item["resolved_at"] = datetime.now().isoformat()
                self._save(items)
                return True
        return False

    def dismiss(self, item_id: str) -> bool:
        items = self._load()
        for item in items:
            if item["id"] == item_id:
                item["status"] = "dismissed"
                item["dismissed_at"] = datetime.now().isoformat()
                self._save(items)
                return True
        return False

    def get_pending(self) -> List[Dict]:
        return [i for i in self._load() if i.get("status") == "pending"]

    def get_all(self) -> List[Dict]:
        return self._load()

    def count_pending(self) -> int:
        return len(self.get_pending())


# ═══════════════════════════════════════════════════════════════
#  GROWTH LOG
# ═══════════════════════════════════════════════════════════════

class GrowthLogger:
    """Logs autonomous improvements for transparency."""

    def __init__(self):
        GHOST_HOME.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict]:
        if GROWTH_LOG_FILE.exists():
            try:
                return json.loads(GROWTH_LOG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, entries: List[Dict]):
        entries = entries[:200]
        GROWTH_LOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def log(self, routine: str, summary: str, details: str = "",
            category: str = "growth") -> Dict:
        entries = self._load()
        
        # Deduplication: Check for identical entries in the last 10 minutes
        from datetime import timedelta
        now = datetime.now()
        for existing in entries[:20]:  # Check recent entries only
            existing_time = datetime.fromisoformat(existing["timestamp"])
            if (existing["routine"] == routine and 
                existing["summary"] == summary and
                (now - existing_time) < timedelta(minutes=10)):
                existing["_warning"] = (
                    "DUPLICATE — this was already logged. Do NOT call log_growth_activity again. "
                    "Continue with your ACTUAL task (evolve_plan, evolve_apply, file_read, etc.). "
                    "Calling this tool repeatedly is a waste of steps."
                )
                return existing
        
        # Also warn if the same summary appears many times recently
        recent_same_summary = sum(
            1 for e in entries[:50] 
            if e["summary"] == summary and e["routine"] == routine
        )
        warning = ""
        if recent_same_summary >= 5:
            warning = f"WARNING: log_growth_activity called {recent_same_summary} times with identical arguments. The repeated calls may not be productive. Try a different approach."
        
        entry = {
            "id": uuid.uuid4().hex[:10],
            "routine": routine,
            "summary": summary,
            "details": details,
            "category": category,
            "timestamp": now.isoformat(),
            "_warning": warning if warning else None,
        }
        entries.insert(0, entry)
        self._save(entries)
        return entry

    def get_recent(self, limit: int = 50) -> List[Dict]:
        return self._load()[:limit]


# ═══════════════════════════════════════════════════════════════
#  GROWTH ROUTINE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

_CAPABILITIES = (
    "\n\n## YOUR CAPABILITIES (use them — no excuses)\n"
    "You are a fully autonomous AI agent with access to 120+ tools. "
    "You have EVERYTHING a senior developer has. Use it all.\n\n"
    "### Tools you have RIGHT NOW:\n"
    "- **shell_exec**: Run ANY command — curl, python, grep, find, pip, git, ls, cat, etc.\n"
    "  The allowed commands list is huge: filesystem, text processing, search,\n"
    "  networking (curl, wget, ping), process management, python, node, and more.\n"
    "- **web_search**: Search the internet for solutions, docs, error messages.\n"
    "- **web_fetch**: Fetch any URL — read docs, test YOUR OWN endpoints, check APIs.\n"
    "  TEST YOUR OWN DASHBOARD: web_fetch('http://localhost:3333/api/...') to verify endpoints work.\n"
    "- **file_read / file_write / grep / glob**: Full filesystem access to Ghost's codebase.\n"
    "- **memory_search / memory_save**: Learn from past mistakes, remember what you tried.\n"
    "- **add_future_feature**: Queue code changes for the Evolution Runner to implement.\n"
    "- **add_action_item**: Ask the user for things ONLY they can do (API keys, accounts).\n\n"
    "### How to act like a senior developer:\n"
    "- **Hit a confusing error?** web_search the error message. Read the docs.\n"
    "- **Not sure how something works?** file_read the source code. grep for patterns.\n"
    "- **Need to verify a fix?** curl/web_fetch the endpoint. Run a test command.\n"
    "- **Need a package?** shell_exec('pip install <pkg>') — you have pip access.\n"
    "- **Dashboard endpoint broken?** web_fetch it, read the traceback, read the route code, "
    "diagnose and queue a fix. Don't just report 'endpoint returned 500'.\n"
    "- **NEVER give up** because something is hard. You have the internet, an LLM brain, "
    "and full system access. Figure it out.\n"
)

_DEV_STANDARDS = (
    "\n\n## DEVELOPMENT STANDARDS (MANDATORY for all code changes)\n"
    "### Modular Architecture\n"
    "- New feature = new file. Create `ghost_<feature>.py`. NEVER add unrelated code to existing files.\n"
    "- One module, one responsibility. Each `ghost_*.py` owns a single domain.\n"
    "- New dashboard page = new blueprint in `routes/` + new JS module in `static/js/pages/`. "
    "MUST follow the dashboard design system (see SOUL.md): use `stat-card`, `page-header`, "
    "`page-desc`, `btn btn-primary`, `form-input`, `badge`, `evo-tab` classes. "
    "NEVER use Tailwind light/dark mode (`dark:`, `bg-white`) — the dashboard is always dark.\n"
    "- After adding a new feature, UPDATE SOUL.md codebase map and document the feature.\n"
    "- Function-level tools: `make_*()` returns {name, description, parameters, execute}.\n"
    "- Config-driven: every feature has an `enable_<feature>` toggle. Degrade gracefully when disabled.\n"
    "- Minimal coupling: communicate through function calls, config dicts, and tool registry.\n"
    "### Security Best Practices\n"
    "- NEVER hardcode secrets. Keys/tokens go in `~/.ghost/` config or env vars.\n"
    "- Validate ALL inputs. Never trust LLM-provided values blindly.\n"
    "- Sanitize file paths — resolve and check against `allowed_roots`. Block path traversal.\n"
    "- Whitelist shell commands. Never bypass `allowed_commands`.\n"
    "- Scope API tokens to minimum required permissions.\n"
    "- NEVER log secrets — strip tokens, keys, passwords from logs and memory.\n"
    "- Protect user data: store summaries only, never verbatim email/file contents.\n"
    "- Rate limit external calls. Use backoff for retries.\n"
    "- Fail closed: deny on security check failure.\n"
    "- Pin dependency versions.\n"
    "### Evolution Success Logging\n"
    "- NEVER call memory_save or log_growth_activity to claim success until evolve_submit_pr or evolve_deploy confirms.\n"
    "- If evolve_test fails or you call evolve_rollback, the evolution FAILED — do not log it as successful.\n"
    "- If a new feature needs a pip package, install it yourself: shell_exec(command='pip install <pkg>'). requirements.txt is auto-updated — do NOT manually edit it.\n"
    "- Only use add_action_item for things that truly need human action (API keys, hardware, accounts).\n"
    "### SKILL.md Format (MANDATORY)\n"
    "When creating or editing skills, SKILL.md MUST use this exact frontmatter format:\n"
    "```\n"
    "---\n"
    "name: my-skill-name\n"
    "description: One-line description\n"
    "triggers:\n"
    "  - keyword1\n"
    "  - keyword2\n"
    "  - phrase with spaces\n"
    "tools:\n"
    "  - tool_name1\n"
    "  - tool_name2\n"
    "priority: 50\n"
    "---\n"
    "```\n"
    "CRITICAL rules for `triggers:`:\n"
    "- Each trigger MUST be a plain string (a word or phrase).\n"
    "- NEVER nest triggers as dicts/objects like `- keywords: [...]` or `- pattern: ...`.\n"
    "- NEVER use YAML mappings inside the triggers list.\n"
    "- WRONG: `- keywords: [\"a\", \"b\"]`  WRONG: `- {match: \"x\"}`\n"
    "- RIGHT: `- a`  `- b`  `- x`\n"
    "- File extensions go as plain strings too: `- .mp3`  `- .wav`\n"
)

_CODE_PATTERNS = (
    "\n\n## BATTLE-TESTED CODE PATTERNS (copy these — do NOT improvise)\n"
    "These patterns come from 14 rejected PRs. Use them EXACTLY.\n\n"
    "### Pattern 1: Thread-safe atomic file write\n"
    "```python\n"
    "import tempfile, os, json, threading\n"
    "from pathlib import Path\n\n"
    "_file_lock = threading.Lock()\n\n"
    "def atomic_write_json(path: Path, data):\n"
    "    path.parent.mkdir(parents=True, exist_ok=True)\n"
    "    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')\n"
    "    try:\n"
    "        with os.fdopen(fd, 'w') as f:\n"
    "            json.dump(data, f, indent=2, default=str)\n"
    "        os.replace(tmp, str(path))  # atomic on POSIX\n"
    "    except BaseException:\n"
    "        os.close(fd) if not os.fdopen else None  # fd already closed by fdopen\n"
    "        if Path(tmp).exists():\n"
    "            os.unlink(tmp)\n"
    "        raise\n"
    "```\n"
    "KEY RULES: (1) mkdir BEFORE write. (2) os.fdopen takes ownership of fd — never "
    "close fd separately after fdopen. (3) os.replace for atomicity. (4) Clean up tmp on failure.\n\n"
    "### Pattern 2: Read-modify-write with lock\n"
    "```python\n"
    "def append_entry(path: Path, entry: dict, max_entries: int = 500):\n"
    "    with _file_lock:\n"
    "        entries = []\n"
    "        if path.exists():\n"
    "            try:\n"
    "                raw = path.read_text(encoding='utf-8')\n"
    "                loaded = json.loads(raw) if raw.strip() else []\n"
    "                if isinstance(loaded, list):\n"
    "                    entries = loaded[-max_entries:]  # bounded read\n"
    "            except (json.JSONDecodeError, ValueError):\n"
    "                entries = []  # corrupted — start fresh, don't crash\n"
    "        entries.append(entry)\n"
    "        entries = entries[-max_entries:]  # cap size\n"
    "        atomic_write_json(path, entries)\n"
    "```\n"
    "KEY RULES: (1) Lock wraps the ENTIRE read-modify-write. (2) Validate loaded type "
    "is list. (3) Bound the read AND the write. (4) Specific exceptions, never bare except.\n\n"
    "### Pattern 3: Exception handling — NEVER do this\n"
    "```python\n"
    "# WRONG — will be instantly rejected:\n"
    "except: pass\n"
    "except Exception: pass\n"
    "except Exception as e: pass\n"
    "except (OSError, ValueError): pass  # silent swallow\n\n"
    "# RIGHT — specific exceptions + logging:\n"
    "except (json.JSONDecodeError, ValueError) as exc:\n"
    "    logger.warning('Failed to parse %s: %s', path, exc)\n"
    "    return default_value\n"
    "except OSError as exc:\n"
    "    logger.error('I/O error writing %s: %s', path, exc)\n"
    "    raise  # or return a safe fallback, NEVER silently ignore\n"
    "```\n"
    "RULE: Every except block MUST either (a) log + return a safe default, or (b) log + re-raise. "
    "NEVER silently swallow. Use the MOST SPECIFIC exception type.\n\n"
    "### Pattern 4: Python imports for mutable module state\n"
    "```python\n"
    "# WRONG — copies the value at import time, stays stale forever:\n"
    "from ghost_foo import _some_var\n\n"
    "# RIGHT — live reference through the module:\n"
    "import ghost_foo\n"
    "# usage: ghost_foo._some_var  (always reads current value)\n"
    "```\n\n"
    "### Pattern 5: Tool definition template\n"
    "```python\n"
    "def build_my_tools(cfg):\n"
    "    def _my_action(arg1, limit=50, **kwargs):\n"
    "        # kwargs absorbs unexpected params — prevents TypeError crashes\n"
    "        return 'result string'\n\n"
    "    return [{\n"
    "        'name': 'my_tool',\n"
    "        'description': 'What this tool does (one clear sentence)',\n"
    "        'parameters': {\n"
    "            'type': 'object',\n"
    "            'properties': {\n"
    "                'arg1': {'type': 'string', 'description': '...'},\n"
    "                'limit': {'type': 'integer', 'description': '...', 'default': 50},\n"
    "            },\n"
    "            'required': ['arg1']\n"
    "        },\n"
    "        'execute': _my_action\n"
    "    }]\n"
    "```\n"
    "KEY RULES: (1) execute function MUST accept **kwargs. (2) Optional params MUST have defaults. "
    "(3) 'required' list matches the non-defaulted params.\n"
)

_GHOST_SYSTEM_MAP = (
    "\n\n## GHOST SYSTEM MAP (know your codebase before you build)\n"
    "### Backend Modules (ghost_*.py in project root)\n"
    "ghost.py          — Main daemon, GhostDaemon class, tool registration\n"
    "ghost_loop.py     — ToolLoopEngine, ToolRegistry, LoopDetector\n"
    "ghost_tools.py    — Core tools: shell_exec, file_read/write, web_fetch, notify\n"
    "ghost_browser.py  — Playwright browser automation\n"
    "ghost_memory.py   — SQLite FTS5 memory (save/search/prune)\n"
    "ghost_cron.py     — CronService, build_cron_tools()\n"
    "ghost_skills.py   — SkillLoader, trigger matching, prompt injection\n"
    "ghost_plugins.py  — PluginLoader, HookRunner\n"
    "ghost_evolve.py   — EvolutionEngine, build_evolve_tools()\n"
    "ghost_autonomy.py — Growth routines, action items, self-repair\n"
    "ghost_mcp.py      — MCP client, build_mcp_tools()\n"
    "ghost_integrations.py — Google APIs + Grok/X\n"
    "ghost_credentials.py  — Encrypted credential storage\n"
    "ghost_web_search.py   — Multi-provider web search\n"
    "ghost_code_intel.py   — AST-based code analysis\n"
    "ghost_extension_manager.py — Extension system: ExtensionAPI, ExtensionManager, ExtensionEventBus\n"
    "ghost_community_hub.py     — Community Hub: discover, install, publish extensions/nodes\n"
    "ghost_supervisor.py   — Process supervisor (PROTECTED — cannot modify)\n\n"
    "### Extensions (ghost_extensions/<name>/ — NEW FEATURES GO HERE)\n"
    "Each extension has: EXTENSION.yaml (manifest) + extension.py (register(api) entry point)\n"
    "Extensions register tools, hooks, cron jobs, dashboard pages via ExtensionAPI.\n"
    "They auto-load on startup. Users can enable/disable/uninstall via dashboard.\n"
    "⚠️ New features MUST be extensions. NEVER add new ghost_*.py modules.\n\n"
    "### Dashboard Routes (ghost_dashboard/routes/)\n"
    "chat.py, status.py, config.py, models.py, identity.py, skills.py,\n"
    "cron.py, memory.py, feed.py, daemon.py, evolve.py, integrations.py,\n"
    "autonomy.py, mcp.py, webhooks.py, setup.py, accounts.py\n"
    "Register new blueprints in routes/__init__.py\n\n"
    "### Frontend Pages (ghost_dashboard/static/js/pages/)\n"
    "chat.js (#chat), overview.js (#overview), models.js (#models),\n"
    "config.js (#config), soul.js (#soul), skills.js (#skills),\n"
    "cron.js (#cron), memory.js (#memory), feed.js (#feed),\n"
    "evolve.js (#evolve), integrations.js (#integrations),\n"
    "autonomy.js (#autonomy), mcp.js (#mcp), webhooks.js (#webhooks)\n"
    "Each page exports render(container). Router is in app.js.\n\n"
    "### Core JS (ghost_dashboard/static/js/)\n"
    "app.js  — SPA router, sidebar, navigate(), updateSidebarStatus()\n"
    "api.js  — window.GhostAPI: get/post/put/patch/del wrappers\n"
    "utils.js — window.GhostUtils: escapeHtml, formatDate, toast\n\n"
    "### CSS Classes (ghost_dashboard/static/css/dashboard.css)\n"
    "Layout: page-header, page-desc, stat-card, stat-value, stat-label\n"
    "Buttons: btn, btn-primary, btn-ghost, btn-danger, btn-sm\n"
    "Forms: form-input, form-group, toggle-switch\n"
    "Cards: model-card, skill-card, cron-card\n"
    "Status: badge, badge-success, badge-warning, badge-danger\n"
    "Nav: nav-link, nav-link active\n"
    "Colors: bg #0a0a14 (darkest), #10101c (cards), #161625 (inputs)\n"
    "        ghost-purple #8b5cf6 (primary), #a78bfa (hover)\n"
    "        text #ffffff (headings), #d4d4d8 (body), #a1a1aa (muted)\n"
    "ALWAYS dark theme. NEVER use Tailwind light/dark classes.\n\n"
    "### Adding a Dashboard Page (2 paths)\n"
    "A) VIA EXTENSION (preferred for new features):\n"
    "   1. In extension.py: api.register_page({id, label, icon, section, js_path})\n"
    "   2. Create ghost_extensions/<name>/static/<page>.js — export render(container)\n"
    "   3. api.register_route(blueprint) for API endpoints — MANDATORY when the page\n"
    "      needs to load/save data. The JS calls /api/<ext_name>/... endpoints served\n"
    "      by the blueprint. Without this, all API calls from the page return 404.\n"
    "      IMPORTANT: Extension tools (register_tool) are NOT HTTP endpoints.\n"
    "      The JS frontend CANNOT call tools via /tool/... URLs. You MUST create\n"
    "      Flask Blueprint routes for any data the page needs.\n"
    "   The extension system auto-registers routes, nav links, and static serving.\n"
    "   NO changes to core files needed.\n\n"
    "   ⚠ DASHBOARD PAGE UX RULES (MANDATORY):\n"
    "   - Decide the page's PURPOSE first: Is it a VIEWER (showing data the AI or\n"
    "     system produces) or an INPUT FORM (collecting data from the human user)?\n"
    "   - AUTOMATION extensions (tools Ghost uses during tasks): The dashboard page\n"
    "     must be a READ-ONLY VIEWER/MANAGER. Show history, status, results, exports.\n"
    "     Do NOT expose raw tool parameters as a manual form. Users don't fill in\n"
    "     session IDs, step lists, or artifact dicts — Ghost generates those.\n"
    "   - USER-FACING extensions (tools the human triggers): Forms are OK, but keep\n"
    "     them simple. One or two inputs max. No internal IDs. No multi-line fields\n"
    "     for structured data (like 'one step per line').\n"
    "   - The EXAMPLE EXTENSION in ghost_extensions/example_extension/ shows a correct\n"
    "     viewer page with a simple input form. READ IT before building yours.\n"
    "   - Empty states must have helpful text explaining what the page shows and how\n"
    "     data appears (e.g., 'Checkpoints appear here when Ghost runs long tasks').\n\n"
    "B) CORE PAGES ONLY (for bug fixes to existing pages):\n"
    "   1. ghost_dashboard/routes/<page>.py — Flask blueprint\n"
    "   2. Register in routes/__init__.py\n"
    "   3. ghost_dashboard/static/js/pages/<page>.js — export render(container)\n"
    "   4. Add route in app.js + sidebar link in index.html\n\n"
    "### CORE API REFERENCE (do NOT hallucinate methods — use ONLY these)\n"
    "These are the EXACT public methods on the most-imported classes. If a method\n"
    "is not listed here, it does NOT exist. Always file_read the source to confirm.\n\n"
    "ToolLoopEngine (ghost_loop.py):\n"
    "  __init__(api_key, model, base_url=..., fallback_models=None, auth_store=None, provider_chain=None, usage_tracker=None)\n"
    "  .run(system_prompt, user_message, tool_registry=None, max_steps=20, temperature=0.3, max_tokens=..., ...)\n"
    "  .single_shot(system_prompt, user_message, temperature=0.2, max_tokens=1024, image_b64=None, images=None)\n"
    "  .api_key (property, getter+setter)    .model (property, getter+setter)\n"
    "  .fallback_chain (property -> ModelFallbackChain)\n"
    "  NOTE: There is NO .run_once(), NO .step(), NO .execute(). Use .run() for the full loop.\n\n"
    "ToolRegistry (ghost_loop.py):\n"
    "  __init__(strict_mode=False)\n"
    "  .register(tool_def)    .unregister(name)    .get(name)    .get_all() -> dict\n"
    "  .names() -> list    .execute(name, args) -> str    .to_openai_schema() -> list\n"
    "  .subset(names) -> ToolRegistry    .is_reserved(name) -> bool    .get_audit_log() -> list\n"
    "  NOTE: There is NO .list_tools(), NO .list(), NO .find(). Use .get_all() or .names().\n\n"
    "SkillLoader (ghost_skills.py):\n"
    "  __init__(extra_dirs=None)\n"
    "  .skills -> Dict[str, Skill]    .reload()    .check_reload(interval=30)\n"
    "  .match(text, content_type=None, disabled=None) -> list[Skill]\n"
    "  .get(name) -> Skill|None    .list_all() -> list[Skill]\n"
    "  .build_skills_prompt(matched_skills) -> str\n"
    "  .get_tools_for_skills(matched_skills) -> set[str]\n"
    "  NOTE: There is NO .get_skill(), NO .load(). Use .get(name) or .skills dict.\n\n"
    "Skill (ghost_skills.py):\n"
    "  Slots: .name .description .triggers .tools .body .path .priority .os_filter .requires .model\n"
    "  .matches(text, content_type=None) -> bool    .to_prompt_section() -> str\n"
)

_PRE_PR_CHECKLIST = (
    "\n\n## PRE-PR SELF-REVIEW (MANDATORY — complete EVERY item before evolve_submit_pr)\n"
    "Run through this checklist mentally. If ANY item fails, fix it FIRST.\n\n"
    "[ ] ARCHITECTURE CHECK: Is this a new feature? Files must be under ghost_extensions/<name>/.\n"
    "    If you modified ghost.py or routes/__init__.py for a new feature, STOP and redo as extension.\n"
    "    Bug fixes may patch core files. New features NEVER touch core files.\n"
    "[ ] EXCEPTION HANDLING: grep your new code for 'except'. Every handler must\n"
    "    (a) catch a specific type, AND (b) log or re-raise. Zero bare except/silent pass.\n"
    "[ ] THREAD SAFETY: Does your code read+write any file that another thread could touch?\n"
    "    If yes → threading.Lock + atomic write. See Pattern 2 above.\n"
    "[ ] DIRECTORY CREATION: Every file path you write to — does the parent dir exist?\n"
    "    Add Path.mkdir(parents=True, exist_ok=True) BEFORE the first write.\n"
    "[ ] ATOMIC WRITES: Any JSON/config file write must use tempfile+os.replace.\n"
    "    NEVER open(path,'w') directly on a shared file. See Pattern 1 above.\n"
    "[ ] BOUNDED READS: Never json.load() an unbounded file. Cap reads with slicing.\n"
    "[ ] IMPORT STYLE: If you import a mutable module-level variable, use\n"
    "    'import module' not 'from module import var'. See Pattern 4 above.\n"
    "[ ] TOOL SIGNATURES: Every execute function accepts **kwargs.\n"
    "    Optional params have defaults. Required params match schema.\n"
    "[ ] FRONTEND-BACKEND: JS payload shape == Python route's request.get_json() shape.\n"
    "    GET responses match what JS renders. Save→reload shows same data.\n"
    "[ ] EXTENSION ROUTES: If extension has a dashboard page, it MUST have a Flask Blueprint\n"
    "    registered via api.register_route(). JS files must call /api/<ext_name>/... NOT /tool/...\n"
    "    Tools (register_tool) are NOT HTTP endpoints — the frontend cannot call them.\n"
    "    Blueprint routes must return jsonify({...}), NOT json.dumps() strings.\n"
    "[ ] EXTENSION JS LAYOUT: Form inputs/textareas inside modals must use\n"
    "    style=\"width:100%;box-sizing:border-box\". The form-input class alone does NOT set width.\n"
    "[ ] EXTENSION YAML: EXTENSION.yaml provides.routes must list the Blueprint name.\n"
    "    provides.pages must list page definitions. Mismatched YAML causes silent load failures.\n"
    "[ ] HOOK EVENTS: Every register_hook() call must use a valid event name from:\n"
    "    on_boot, on_shutdown, on_chat_message, on_tool_call, on_tool_loop_complete,\n"
    "    on_tool_loop_error, on_media_generated, on_evolve_complete.\n"
    "    Unknown events are REJECTED at load time. Hook handler kwargs must match the\n"
    "    event's documented signature (see Events table above).\n"
    "[ ] TOOL REGISTRATION: Extensions use api.register_tool() in register(api).\n"
    "    Bug-fix modules: imported in ghost.py + build_*_tools() + tool_registry.register().\n"
    "[ ] NO DUPLICATE FEATURES: Did you check if a similar tool/module already exists?\n"
    "    grep for the capability before building a new one.\n"
    "[ ] INTERFACE COMPATIBILITY: For every 'from ghost_X import ClassName' in your new code,\n"
    "    file_read ghost_X.py and verify that EVERY method you call on that class actually\n"
    "    exists. Do NOT assume — CHECK. Common mistake: hallucinating method names like\n"
    "    run_once (real: run), list_tools (real: get_all/names), get_skill (real: .get).\n"
    "[ ] TOOL NAME CONFLICTS: grep for each tool name you registered across ghost_tools.py,\n"
    "    ghost.py, ghost_extension_manager.py. If ANY existing tool has the same name, rename yours.\n"
    "[ ] NO STUBS: Every tool execute function does real work. No 'not implemented',\n"
    "    'coming soon', 'skipped' responses. If a parameter is accepted, it must function.\n"
    "[ ] LLM FOR INTELLIGENCE: If this extension does summarization, extraction, or classification,\n"
    "    verify it uses api.llm_summarize() — NOT regex/string splitting.\n"
    "[ ] DASHBOARD UX: If the extension has a dashboard page, ask: WHO uses this page?\n"
    "    - If Ghost uses the tools autonomously → page must be a VIEWER (browse, inspect, export).\n"
    "      Do NOT create manual forms that duplicate tool parameters. Users don't type session IDs,\n"
    "      completed steps, or artifacts by hand.\n"
    "    - If the user triggers the action → keep forms minimal (1-2 fields). No internal IDs.\n"
    "    - Empty states must explain what the page shows and how data appears.\n"
    "[ ] WORKFLOW TEST: Trace the complete user workflow end-to-end. Does the extension actually\n"
    "    solve the problem in the feature request? Or does it just provide passive building blocks?\n"
    "If ALL boxes pass, proceed to evolve_submit_pr. Otherwise, fix and re-verify.\n"
)

GROWTH_ROUTINES = [
    {
        "id": "tech_scout",
        "name": "Tech Scout",
        "description": "Browse AI/tech news and identify improvements for Ghost",
        "prompt": (
            "You are Ghost running an autonomous TECH SCOUT routine. Your goal:\n"
            "1. Use memory_search to check what you scouted recently — avoid duplicate work.\n"
            "2. Use web_search (preferred) or web_fetch to browse AI/tech news sources. Look for:\n"
            "   - New AI models or APIs Ghost could integrate with\n"
            "   - New developer tools that could become Ghost extensions or skills\n"
            "   - Security patches or best practices relevant to Ghost\n"
            "3. BEFORE calling add_future_feature, you MUST verify Ghost doesn't already have this.\n"
            "   Do NOT rely on memory alone — search the actual codebase:\n"
            "   - grep(key_term, include='*.py') for each key technology/package/feature name\n"
            "   - Also check ghost_extensions/ and ghost_nodes/ for existing extensions/nodes\n"
            "   - file_read requirements.txt to check if packages are already installed\n"
            "   - If grep finds matches, file_read the matching files to confirm the functionality\n"
            "     is already working code (not just a comment or TODO).\n"
            "   - If the feature/package/tool already exists and is working in Ghost, do NOT add it.\n"
            "     Log via memory_save that you confirmed it was already present and move on.\n\n"
            "## EXTENSION-FIRST ARCHITECTURE\n"
            "Ghost uses an EXTENSION system for new features. New capabilities should be\n"
            "designed as self-contained extensions in ghost_extensions/<name>/, NOT as\n"
            "modifications to core Ghost files (ghost.py, ghost_loop.py, etc.).\n"
            "Only bug fixes and security patches modify core files.\n\n"
            "When you discover a new capability Ghost should have, think:\n"
            "- What TOOLS would this extension register? (e.g. 'translate_text', 'analyze_sentiment')\n"
            "- What HOOKS would it subscribe to? (on_chat_message, on_media_generated, etc.)\n"
            "- Does it need a DASHBOARD PAGE? (for config, monitoring, visualization)\n"
            "- Does it need CRON JOBS? (periodic sync, cleanup, polling)\n"
            "- What pip DEPENDENCIES does it need?\n\n"
            "4. If you find something actionable AND confirmed it is NOT already in Ghost,\n"
            "   use this decision tree:\n"
            "   a. NEW FEATURES / IMPROVEMENTS / INTEGRATIONS:\n"
            "      - You MUST call add_future_feature() — do NOT just write a summary.\n"
            "        Provide an IMPLEMENTATION-READY BRIEF:\n"
            "        * description: What you found and why it matters.\n"
            "        * affected_files: 'ghost_extensions/<name>/EXTENSION.yaml, "
            "ghost_extensions/<name>/extension.py' (add static/<page>.js if it needs UI).\n"
            "        * proposed_approach: Extension design — what tools/hooks/pages/cron it\n"
            "          registers via ExtensionAPI. What the register(api) function does.\n"
            "          What pip packages it needs. Reference existing extensions as examples.\n"
            "      - Set priority: P1 (high), P2 (medium), or P3 (low) based on value/effort.\n"
            "      - Set source='tech_scout', source_detail=news source URL.\n"
            "      - Set category: 'feature' or 'improvement' (NOT 'bugfix').\n"
            "   b. BUG FIXES / SECURITY:\n"
            "      - These DO modify core files. Set category='bugfix' or 'security'.\n"
            "      - List the actual core file paths in affected_files.\n"
            "   c. MISSING DEPENDENCIES (needs pip package):\n"
            "      - Install yourself with shell_exec: pip install <package> (requirements.txt auto-updates — do NOT edit it manually)\n"
            "   d. USER INPUT REQUIRED (API keys, hardware, accounts):\n"
            "      - Use add_action_item for human-required actions\n"
            "5. You do NOT have access to evolve tools. All code changes go through the\n"
            "   Future Features queue. The Evolution Runner implements them automatically.\n"
            "   Do NOT skip add_future_feature because you think the finding 'needs more research'\n"
            "   or 'is too complex'. The feature brief IS the design document.\n"
            "6. Be selective — only act on things that genuinely improve Ghost.\n"
            "   Max 2-3 discoveries per run, but EACH one MUST be queued via add_future_feature.\n"
            "7. Use memory_save to record findings. Use log_growth_activity to summarize.\n"
            + _CAPABILITIES
            + _DEV_STANDARDS
        ),
    },
    {
        "id": "health_check",
        "name": "Health Check",
        "description": "Test system health — APIs, tools, disk, connectivity, dashboard endpoints",
        "prompt": (
            "You are Ghost running an autonomous HEALTH CHECK routine. Your goal:\n"
            "1. Test OpenRouter connectivity: use web_fetch to hit https://openrouter.ai/api/v1/models "
            "(just check it responds).\n"
            "2. Check Google integration: use google_gmail with action='list_labels' to verify "
            "connectivity. If it fails, use add_action_item to tell the user.\n"
            "3. Check disk usage: use shell_exec with 'df -h .' to check available space.\n"
            "4. Check memory database: use memory_search with a simple query to verify it works.\n"
            "5. Check recent error logs: use file_read on ~/.ghost/log.json (last 20 entries), "
            "look for repeated errors.\n"
            "6. **DASHBOARD SELF-TEST** (CRITICAL — this catches silent API bugs):\n"
            "   Use web_fetch to hit each of these dashboard endpoints and verify they return valid JSON:\n"
            "   - http://localhost:3333/api/setup/status\n"
            "   - http://localhost:3333/api/setup/providers\n"
            "   - http://localhost:3333/api/setup/doctor/status\n"
            "   - http://localhost:3333/api/ghost/status\n"
            "   If ANY endpoint returns an HTTP error (4xx/5xx), that is a BUG in Ghost's own code.\n"
            "   Read the route file that serves that endpoint, diagnose the root cause, and queue\n"
            "   a fix via add_future_feature with priority='P1', source='health_check', category='bugfix'.\n"
            "   Dashboard bugs are silent — they don't crash Ghost or appear in log.json.\n"
            "   This self-test is the ONLY way Ghost discovers them.\n"
            "7. Use log_growth_activity to log the health check results.\n"
            "8. If anything is broken:\n"
            "   - Code issues: queue a fix via add_future_feature with an IMPLEMENTATION-READY BRIEF.\n"
            "   - Missing pip packages: install them yourself with shell_exec(command='pip install <pkg>'). requirements.txt is auto-updated — do NOT edit it manually.\n"
            "   - Things truly requiring user action (API keys, account setup): use add_action_item.\n"
            "Be concise. Report status, don't over-explain."
            + _CAPABILITIES
        ),
    },
    {
        "id": "user_context",
        "name": "User Context Sync",
        "description": "Learn user patterns from email/calendar to anticipate needs",
        "prompt": (
            "You are Ghost running an autonomous USER CONTEXT routine. Your goal:\n"
            "1. Check if Google services are connected. If not, skip gracefully.\n"
            "2. Use google_gmail with action='list_messages' (max_results=5) to see recent emails.\n"
            "3. Use google_calendar with action='list_events' to see upcoming events.\n"
            "4. Use memory_save to store useful context about the user's current situation "
            "(upcoming meetings, important emails, patterns you notice).\n"
            "5. Do NOT read full email bodies unless the subject seems important.\n"
            "6. Use log_growth_activity to summarize what you learned.\n"
            "7. RESPECT PRIVACY: never store email contents verbatim. Only save high-level "
            "patterns like 'user has a meeting at 3pm' or 'user received emails about project X'.\n"
            "If Google is not connected, use add_action_item to suggest connecting it."
        ),
    },
    {
        "id": "skill_improver",
        "name": "Skill Improver",
        "description": "Review, improve, and add new skills",
        "prompt": (
            "You are Ghost running an autonomous SKILL IMPROVER routine. Your goal:\n"
            "1. Use memory_search to check what skill work you did recently.\n"
            f"2. Use file_search to list current skills in {PROJECT_DIR}/skills/ directory.\n"
            "3. Pick ONE of these tasks (rotate each run):\n"
            "   a. Review an existing skill's SKILL.md for quality — improve triggers, "
            "      instructions, or tool usage.\n"
            "   b. Create a new skill for a popular tool the user might need "
            "      (check memory for user context clues).\n"
            "   c. Check if any skill references outdated APIs or patterns and update them.\n"
            "4. Queue the change via add_future_feature with an IMPLEMENTATION-READY BRIEF:\n"
            "   - title: 'Skill improvement: <skill name> — <what to improve>'\n"
            "   - description: What's wrong with the current skill and why it needs changing.\n"
            "   - affected_files: The exact skill file path(s).\n"
            "   - proposed_approach: The exact content changes — new triggers, updated instructions,\n"
            "     fixed YAML frontmatter. Include the actual new content.\n"
            "   - priority='P2', source='other', category='improvement'\n"
            "5. You do NOT have access to evolve tools. All code changes go through the queue.\n"
            "6. Use memory_save to record what you found. Use log_growth_activity to log.\n"
            "Be conservative — small targeted improvements, not rewrites.\n"
            f"IMPORTANT: All skills MUST be created inside {PROJECT_DIR}/skills/<skill-name>/SKILL.md — "
            "this is the project skills directory. NEVER create skills in ~/.ghost/skills/ — "
            "that path is for user-installed community skills only.\n"
            "When reviewing skills, verify that `triggers:` is a flat list of plain strings. "
            "Fix any triggers that use nested dicts/objects — they break skill matching."
            + _DEV_STANDARDS
        ),
    },
    {
        "id": "soul_evolver",
        "name": "Soul Evolver",
        "description": "Reflect and refine SOUL.md based on experience",
        "prompt": (
            "You are Ghost running an autonomous SOUL EVOLUTION routine. Your goal:\n"
            "1. Read SOUL.md using file_read.\n"
            "2. Read recent growth log entries using memory_search or file_read on "
            "~/.ghost/growth_log.json.\n"
            "3. Read recent user interactions from memory_search.\n"
            "4. Reflect: Has Ghost learned new capabilities? Changed how it works? "
            "Found better approaches?\n"
            "5. If SOUL.md should be updated, queue the change via add_future_feature with:\n"
            "   - title: 'Soul update: <brief description>'\n"
            "   - description: What to change and why (with reasoning).\n"
            "   - affected_files: 'SOUL.md' (and any other files if applicable).\n"
            "   - proposed_approach: The EXACT text changes — which sections to update, what to add/remove.\n"
            "     Include the actual new content so the Evolution Runner can apply it as patches.\n"
            "   - priority='P2', source='other', category='soul_update'\n"
            "6. You do NOT have access to evolve tools. All code changes go through the queue.\n"
            "7. Use log_growth_activity to log what you recommended and why.\n"
            "IMPORTANT: Only propose meaningful updates. Don't change for the sake of changing. "
            "SOUL.md is your identity — treat it seriously.\n"
            "IMPORTANT: Never propose removing or weakening the Development Standards or Security sections."
            + _DEV_STANDARDS
        ),
    },
    {
        "id": "feature_implementer",
        "name": "Feature Implementer",
        "description": "Serial Evolution Runner — the ONLY routine with evolve tools",
        "event_driven": True,
        "prompt": (
            "You are the EVOLUTION RUNNER — Ghost's autonomous developer.\n\n"
            f"GHOST CODEBASE: {PROJECT_DIR}\n"
            "Use absolute paths or simple relative names (e.g. 'ghost.py'). NEVER '~/' or partial paths.\n\n"
            "## CRITICAL: YOUR TRAINING DATA IS WRONG ABOUT GHOST'S APIs\n"
            "Ghost's internal classes (ToolLoopEngine, ToolRegistry, SkillLoader, etc.) are NOT\n"
            "in your training data. If you guess method names, you WILL get them wrong.\n"
            "ALWAYS file_read the source file or grep('def method_name', include='ghost_*.py')\n"
            "to verify a method exists BEFORE calling it. Past failures from hallucinated methods:\n"
            "  ToolLoopEngine.run_once (does NOT exist — real method: .run)\n"
            "  ToolRegistry.list_tools (does NOT exist — real method: .get_all or .names)\n"
            "  SkillLoader.get_skill  (does NOT exist — real method: .get or .skills dict)\n\n"
            "## RULES\n"
            "- You MUST call evolve_apply at least once. No excuses.\n"
            "- You MUST NOT call task_complete without first calling evolve_submit_pr.\n"
            "- You MUST NOT call evolve_rollback unless evolve_test FAILED.\n"
            "- You MUST NOT defer work. There is no next run.\n"
            "- MAXIMUM 1 feature per run. After deploy, Ghost restarts.\n"
            "- NEVER call pause/shutdown/restart endpoints — those are USER-ONLY.\n\n"
            "## EXTENSION-FIRST ARCHITECTURE (MANDATORY)\n"
            "Check the feature's `implementation_type` field (shown by get_future_feature):\n"
            "- `extension` → Build as ghost_extensions/<name>/ (see structure below)\n"
            "- `core` → Modify core Ghost files directly (bug/security fixes ONLY)\n\n"
            "For EXTENSIONS, you create files ONLY under ghost_extensions/<name>/:\n"
            "```\n"
            "ghost_extensions/<name>/\n"
            "  EXTENSION.yaml    # manifest: name, version, description, category\n"
            "                    # requires: {ghost_version, deps: [pip packages]}\n"
            "                    # provides: {tools: [...], hooks: [...], pages: [...]}\n"
            "  extension.py      # def register(api): — entry point\n"
            "  static/           # optional JS/CSS if extension adds dashboard pages\n"
            "```\n\n"
            "⚠️ NAMING: Extension directory names MUST use underscores, NOT hyphens.\n"
            "  GOOD: ghost_extensions/stabilization_mode/\n"
            "  BAD:  ghost_extensions/stabilization-mode/  ← BREAKS Python import\n\n"
            "The register(api) function receives an ExtensionAPI instance with these methods:\n"
            "  Registration:\n"
            "    api.register_tool({name, description, parameters, execute})  # add a tool\n"
            "    api.register_hook(event, callback)     # subscribe to events\n"
            "    api.register_cron(name, callback, schedule, description)  # add cron job\n"
            "    api.register_page({id, label, icon, section, js_path})    # add dashboard page\n"
            "    api.register_route(blueprint)           # add Flask API routes\n"
            "    api.register_setting({key, type, default, label, description})  # declare setting\n"
            "  Intelligence (USE THESE — do NOT reimplement with regex):\n"
            "    api.llm_summarize(text, instruction, max_tokens=512)  # one-shot LLM call\n"
            "  Memory (USE THESE — do NOT register your own memory_save tool):\n"
            "    api.memory_save(content, tags='', memory_type='note')  # save to Ghost memory\n"
            "    api.memory_search(query, limit=5)      # search Ghost memory\n"
            "  Channels:\n"
            "    api.channel_send(message, channel_id=None)  # send via Telegram/Slack/etc.\n"
            "    api.get_channels()                     # list configured channel IDs\n"
            "  Settings & Data:\n"
            "    api.get_setting(key, default) / api.set_setting(key, value)\n"
            "    api.read_data(filename) / api.write_data(filename, content)\n"
            "  Utilities:\n"
            "    api.log(message)                        # extension-scoped logging\n"
            "    api.save_media(data, filename, ...)     # save generated media\n"
            "    api.id, api.manifest, api.extension_dir, api.data_dir\n\n"
            "Events (ONLY these are valid — any other event name will be rejected at load time):\n"
            "  on_boot()                                    — Ghost started, no kwargs\n"
            "  on_shutdown()                                — Ghost stopping, no kwargs\n"
            "  on_chat_message(role, content, session_id)   — user message received\n"
            "  on_tool_call(tool_name, args, result, session_id, step) — after each tool execution\n"
            "  on_tool_loop_complete(session_id, tool_count, steps, exit_reason) — tool loop finished\n"
            "  on_tool_loop_error(session_id, error, step)  — tool loop failed (LLM error, overflow)\n"
            "  on_media_generated(path, type, metadata)     — image/audio/video saved\n"
            "  on_evolve_complete(evolution_id, status)      — evolution deployed\n\n"
            "⚠️ CRITICAL: Do NOT modify ghost.py, ghost_dashboard/routes/__init__.py, app.js,\n"
            "   index.html, or ANY core file for new features. Extensions auto-register.\n"
            "   If you touch core files for a feature, the PR WILL be rejected.\n\n"
            "## EXTENSION QUALITY RULES (MANDATORY)\n"
            "Every extension you build MUST satisfy these rules. Violations = PR rejection.\n\n"
            "1. **Use the LLM, not regex.** If the feature involves summarization, extraction,\n"
            "   analysis, classification, or ANY text-understanding task — use api.llm_summarize().\n"
            "   Pure regex/string-splitting is NOT acceptable for intelligent features.\n"
            "   The user has LLM tokens available; use them.\n\n"
            "2. **Never shadow core tools.** Do NOT register tools with names that match existing\n"
            "   Ghost tools: memory_save, memory_search, web_fetch, web_search, file_read,\n"
            "   file_write, shell_exec, notify, channel_send, grep, glob, etc.\n"
            "   Always use a descriptive, extension-specific prefix for your tool names\n"
            "   (e.g. digest_thread, NOT semantic_memory_save).\n\n"
            "3. **No stubs.** Every registered tool MUST have a complete, working implementation.\n"
            "   If a parameter is accepted (like postback), it MUST actually work.\n"
            "   A tool that returns 'not configured' or 'coming soon' will be rejected.\n\n"
            "4. **Test the actual workflow.** Before evolve_submit_pr, mentally trace:\n"
            "   - What triggers this extension? What input does it need?\n"
            "   - What output does the user see? Does the tool do intelligent work,\n"
            "     or just shuffle data? If it just shuffles data, it is NOT done.\n\n"
            "5. **Hook into the system.** Extensions should NOT be passive tools waiting to be\n"
            "   called. Consider: should it hook on_chat_message to auto-detect inputs?\n"
            "   Should it register a cron job for periodic work? Should it notify the user?\n"
            "   A good extension integrates into Ghost's lifecycle.\n\n"
            "6. **Use convenience methods.** Prefer api.llm_summarize(), api.memory_save(),\n"
            "   api.memory_search(), api.channel_send() over reaching into daemon internals.\n"
            "   These methods handle errors, logging, and edge cases automatically.\n\n"
            "## TOOLS\n"
            "grep('pattern', include='*.py') — search file contents.\n"
            "glob('ghost_*.py') — find files by name.\n"
            "file_read('path') — read a file. Use these instead of file_search.\n\n"
            "## EXACT SEQUENCE — follow EVERY step, skip NOTHING\n\n"
            "1. list_future_features(status='in_progress'). If found, use that feature.\n"
            "   Otherwise list_future_features(status='pending'). If empty: task_complete.\n\n"
            "2. get_future_feature(id) — read the full brief.\n"
            "   ⚠️ PAST PR REJECTIONS: If present, these are reviewer feedback from failed attempts.\n"
            "   Your code MUST fix ALL listed issues. Missing even ONE = rejected again.\n\n"
            "   🔴 CRITICAL DECISION POINT — READ THE FEATURE OUTPUT CAREFULLY:\n"
            "   Look for a section titled 'RESUME CONTEXT (fix-and-resubmit)'.\n"
            "   If you see 'Branch:', 'Evolution ID:', and 'PR ID:' fields:\n"
            "   → You MUST follow step 2b (RESUME PATH). Do NOT skip to step 3.\n"
            "   → Starting fresh when resume context exists WASTES all prior work.\n"
            "   If there is NO resume context → skip 2b, go to step 3.\n\n"
            "2b. 🔴 MANDATORY RESUME PATH — ONLY skip this if there is NO resume context above.\n"
            "    The feature has an existing branch with code from a previous attempt.\n"
            "    You MUST resume it — do NOT start fresh, do NOT call evolve_plan.\n"
            "    a) Call start_future_feature(feature_id) FIRST to lock it as in_progress.\n"
            "    b) Call evolve_resume(evolution_id=<the Evolution ID from resume context>).\n"
            "    c) If evolve_resume FAILS (branch gone, evolution not found):\n"
            "       - The branch was lost. Proceed to step 3 for a fresh start.\n"
            "    d) If evolve_resume SUCCEEDS:\n"
            "       - Read the FULL reviewer feedback from the response.\n"
            "       - Read any inline comments and suggested changes from the PR.\n"
            "       - For EACH reviewer concern:\n"
            "         * file_read the relevant code section\n"
            "         * Apply a TARGETED fix via evolve_apply patches\n"
            "         * If the reviewer provided a suggest_change: apply exactly that fix\n"
            "       - Do NOT rewrite entire files. Patch only what the reviewer asked for.\n"
            "       - evolve_test(evolution_id)\n"
            "       - If test passes: do verification (step 9), then evolve_submit_pr\n"
            "         (same evolution_id — it reuses the same PR automatically)\n"
            "       - Skip steps 3, 5, 6, 7 (no already-implemented check, no explore,\n"
            "         no new plan, no fresh apply — just targeted patches)\n"
            "       - This saves ~40 steps compared to starting from scratch.\n\n"
            "3. ⚠️ ALREADY-IMPLEMENTED CHECK — BEFORE calling start_future_feature:\n"
            "   Do NOT rely on memory alone — search the actual codebase.\n"
            "   a) Extract 2-3 key technical terms from the feature title/description\n"
            "      (e.g. 'moonshine', 'slash_command', 'playwright')\n"
            "   b) grep(pattern, include='*.py') for EACH term — search the actual codebase\n"
            "   c) file_read requirements.txt — check if any packages mentioned are already installed\n"
            "   d) If grep finds matches: file_read the matching files to confirm whether the\n"
            "      functionality described in the feature is already working code (not just a\n"
            "      comment or TODO). Read enough to understand if it's truly implemented.\n"
            "   e) If the feature IS already implemented in code:\n"
            "      - call reject_future_feature(id, 'Already implemented in <file>: <evidence>')\n"
            "      - move on to the next pending feature. Do NOT start_future_feature.\n"
            "   f) Only proceed to start_future_feature if grep + file_read confirm the feature\n"
            "      is genuinely missing from the codebase.\n\n"
            "4. start_future_feature(id) — mark in_progress.\n\n"
            "5. EXPLORE — you MUST do ALL of these before writing any code:\n"
            "   a) memory_search(query='<feature keywords>', type_filter='mistake')\n"
            "      — MANDATORY CALL. Check for known pitfalls. Read and apply lessons.\n"
            "   b) For EXTENSIONS: file_read ghost_extensions/example_extension/extension.py\n"
            "      and ghost_extensions/example_extension/EXTENSION.yaml to see the patterns.\n"
            "      Also file_read an existing similar extension if one exists (grep ghost_extensions/).\n"
            "      For BUG FIXES: file_read the files you plan to patch.\n"
            "   c) file_read every file you will IMPORT FROM — verify exact class methods\n"
            "      and function signatures. NEVER assume you know a class's API.\n"
            "   d) grep for related code patterns across the codebase.\n"
            "   e) Check ghost_extensions/ for existing extensions that do something similar.\n\n"
            "6. evolve_plan(description, files)\n"
            "   For EXTENSIONS: files=['ghost_extensions/<name>/EXTENSION.yaml', "
            "'ghost_extensions/<name>/extension.py'] (add static/*.js if it needs UI).\n"
            "   For BUG FIXES: list the core files to patch.\n"
            "   ⚠️ NEVER include ghost.py, routes/__init__.py, or app.js for extensions.\n\n"
            "6b. 🔴 MANDATORY STOP — RE-READ DEPENDENCIES BEFORE ANY evolve_apply:\n"
            "    ⚠️ DO NOT call evolve_apply until you complete this step. ⚠️\n"
            "    Your file_read results from step 5 have been COMPACTED from context.\n"
            "    For EXTENSIONS: file_read ghost_extensions/example_extension/extension.py\n"
            "      to see the register(api) pattern. Also file_read ghost_extension_manager.py\n"
            "      class ExtensionAPI to see the available methods.\n"
            "    For BUG FIXES: re-read EVERY file you will patch RIGHT NOW.\n"
            "    This ensures real content is in your RECENT context (never trimmed).\n"
            "    Skipping this is the #1 cause of hallucinated method calls.\n\n"
            "7. evolve_apply — apply changes to EVERY file:\n"
            "   🔴 OUTPUT TOKEN LIMIT: Your max output is ~8K tokens (~150 lines of code).\n"
            "   Any evolve_apply(content=...) over 100 lines WILL truncate and fail with\n"
            "   'malformed JSON / Unterminated string'. This is NOT a bug — it's a hard limit.\n"
            "   SOLUTION: Split new files into chunks using append=True:\n"
            "     Call 1: evolve_apply(evo_id, 'file.py', content='imports + first class...')\n"
            "     Call 2: evolve_apply(evo_id, 'file.py', content='next functions...', append=True)\n"
            "     Call 3: evolve_apply(evo_id, 'file.py', content='remaining code...', append=True)\n"
            "   Keep each chunk ≤100 lines / ≤3000 chars. Complete functions in each chunk.\n"
            "   After ALL chunks are written: call file_read on the new file to see its\n"
            "   exact content BEFORE using patches on it. The actual whitespace may differ.\n"
            "   - NEVER use shell_exec to read, debug, or inspect file content. Use file_read.\n"
            "   - NEVER use shell_exec/file_write to write code — not tracked, causes PR rejection.\n\n"
            "   FOR EXTENSIONS (implementation_type=extension):\n"
            "   - Create EXTENSION.yaml with manifest metadata\n"
            "   - Create extension.py with def register(api): that calls api.register_tool(), etc.\n"
            "   - Create static/<page>.js if the extension needs a dashboard page\n"
            "   - Extensions auto-register on load. Do NOT touch ghost.py or routes/__init__.py.\n\n"
            "   FOR BUG FIXES (implementation_type=core):\n"
            "   - Patch the specific core files listed in affected_files.\n"
            "   - Use patches, not full rewrites.\n\n"
            "7b. CROSS-REFERENCE (mandatory after every evolve_apply):\n"
            "    Use delegate_task to verify your code with a fresh context window:\n"
            "    delegate_task(task='Read <new_file>. For every from ghost_X import Y,\n"
            "      grep def in ghost_X.py and verify every method called on Y exists.\n"
            "      List any methods that do NOT exist in the source.')\n"
            "    The delegate has fresh context — it will read files accurately without\n"
            "    context truncation from your long session.\n"
            "    If delegate_task reports missing methods: fix with evolve_apply immediately.\n"
            "    Do NOT proceed to evolve_test until every method call is verified.\n\n"
            "8. evolve_test(evolution_id) — if FAIL:\n"
            "   a) Read the EXACT error from the test output.\n"
            "   b) Call file_read on the failing file to get EXACT current content.\n"
            "   c) Fix with evolve_apply using patches that match the file_read output EXACTLY.\n"
            "   d) Re-run evolve_test. Up to 5 fix cycles.\n"
            "   After 5 failures: fail_future_feature → task_complete.\n\n"
            "9. ⚠️ MANDATORY VERIFICATION — DO NOT SKIP THIS STEP ⚠️\n"
            "   After evolve_test passes, you MUST run these checks BEFORE submitting the PR.\n"
            "   If you skip this step, your PR WILL be rejected.\n\n"
            "   a) For EACH file you modified, run:\n"
            "      file_read('<file>', offset=1, max_lines=30)\n"
            "      Check: are ALL imports present? If you used log.warning(), does the file\n"
            "      have 'import logging' and 'log = logging.getLogger(...)' at the top?\n"
            "      If you used json, threading, Path — are they imported? FIX if missing.\n\n"
            "   b) grep('except', include='<each_modified_file>')\n"
            "      Check: does EVERY except block either (1) catch a specific exception type\n"
            "      AND (2) log a warning or re-raise? Zero bare except. Zero silent pass.\n"
            "      FIX any that fail.\n\n"
            "   c) If you added routes/<x>.py, verify pages/<x>.js also exists.\n"
            "      If you added a new module, verify ghost.py imports it.\n\n"
            "   d) If you modified a function: what happens if input is None, empty, or wrong type?\n"
            "      Add input validation if needed.\n\n"
            "   e) For shared files (log.json, config.json, etc): is there a threading.Lock?\n"
            "      Is the write atomic (tempfile + os.replace)? Is there mkdir before write?\n\n"
            "   f) INTERFACE CROSS-CHECK (catches the #1 cause of deployed bugs):\n"
            "      Use delegate_task to verify interface compatibility with fresh context:\n"
            "      delegate_task(task='For each from ghost_X import Y in <files>,\n"
            "        verify every method called on Y exists in ghost_X.py.\n"
            "        List exact issues with line numbers.')\n"
            "      If delegate reports issues, fix them before proceeding.\n\n"
            "   Only after ALL checks pass, proceed to step 10.\n\n"
            "10. evolve_submit_pr(evolution_id, title, description, feature_id)\n"
            "    ⚠️ IF REJECTED: call task_complete IMMEDIATELY. Do NOT retry in this session.\n"
            "    The system auto-accumulates feedback and re-fires after 15min cooldown.\n\n"
            "11. ONLY if PR was APPROVED: complete_future_feature(id, summary).\n"
            "    NEVER call complete_future_feature before PR is approved.\n\n"
            "## CODING RULES (violating ANY = instant PR rejection)\n"
            "- OUTPUT LIMIT: You can only produce ~150 lines per tool call. NEVER write >100\n"
            "  lines in a single evolve_apply. Use append=True to build files in chunks.\n"
            "- New feature = NEW EXTENSION (ghost_extensions/<name>/). NEVER a new ghost_*.py module.\n"
            "  Bug fixes = patch existing core files. This is the ONLY distinction.\n"
            "- Extensions are self-contained: EXTENSION.yaml + extension.py + optional static/.\n"
            "  They register tools/hooks/cron/pages via ExtensionAPI. They do NOT import ghost.py.\n"
            "- Dashboard: dark theme only. Classes: stat-card, btn, form-input, badge.\n"
            "- Never hardcode secrets. Validate inputs. Sanitize paths.\n"
            "- Tool execute functions MUST accept **kwargs. Optional params need defaults.\n"
            "- NEVER bare except. NEVER except Exception: pass. Catch specific types + log.\n"
            "- Keep code SIMPLE. No unnecessary abstractions or over-engineering. One function, one job.\n"
            "- Dashboard modals MUST default to hidden. Dismiss via X button, overlay click, AND Escape key.\n"
            "- Use SVG icons in dashboard UI. NEVER use emojis as icons.\n"
            "- API responses MUST return LIVE data from the actual store. NEVER return hardcoded defaults or stale values.\n"
            "- NEVER perform blocking I/O (pip install, network calls, large file reads) at module level or in __init__.\n"
            "- Before building anything new, grep ghost_extensions/ and ghost_nodes/ to check if a similar one already exists.\n"
            + _CODE_PATTERNS
            + _PRE_PR_CHECKLIST
            + _GHOST_SYSTEM_MAP
            + _DEV_STANDARDS
            + _CAPABILITIES
        ),
    },
    {
        "id": "implementation_auditor",
        "name": "Implementation Auditor",
        "description": "Audit recently implemented features for completeness",
        "event_driven": True,
        "prompt": (
            "You are the IMPLEMENTATION AUDITOR. Your job: verify that recently\n"
            "implemented features are PROPERLY WIRED and ACTUALLY WORK.\n\n"
            f"GHOST CODEBASE: {PROJECT_DIR}\n\n"
            "## ANTI-LAZINESS RULES (ABSOLUTE)\n"
            "- You MUST audit at least 1 feature per run. No excuses.\n"
            "- You MUST NOT call task_complete without having run grep/file_read on actual code.\n"
            "- You MUST NOT say 'I cannot determine the filter', 'blocked by metadata', or\n"
            "  'timestamps not available'. If you cannot filter to 24h, audit the MOST RECENT\n"
            "  3 features instead. There is ALWAYS something to audit.\n"
            "- You MUST NOT simply list features and quit. That is NOT an audit.\n"
            "- An audit means: reading code, running grep, checking contracts, verifying rendering.\n\n"
            "## PROCESS\n"
            "1. Call list_future_features(status='implemented') to find features.\n"
            "2. FILTER FROM THE LIST OUTPUT — do NOT call get_future_feature on every feature:\n"
            "   - Skip any feature marked [AUDITED] in the list output.\n"
            "   - Skip any feature whose title starts with 'Wiring fix:'.\n"
            "   - Skip any feature whose title starts with 'Soul update:'.\n"
            "3. From the remaining (non-skipped) features, pick the TOP 3.\n"
            "   ONLY NOW call get_future_feature(id) on those 3 to get the full brief.\n"
            "   If NO candidates remain after filtering, task_complete('No auditable features found.').\n"
            "4. AUDIT each of those features through ALL FOUR layers below.\n"
            "5. After auditing each feature, IMMEDIATELY call mark_feature_audited(feature_id, result):\n"
            "   - result='pass' if all layers passed.\n"
            "   - result='fail_fix_queued' if you found a bug and queued a wiring fix.\n"
            "   - result='fail_no_fix' if you found an issue but couldn't queue a fix.\n"
            "   This stamps the feature so it is NEVER re-examined. You MUST call this.\n\n"
            "## LAYER A: Structural Wiring\n"
            "a) Does the new module file exist? (file_read ghost_<feature>.py)\n"
            "b) Is it IMPORTED in ghost.py? (grep('from ghost_<feature>', include='ghost.py'))\n"
            "c) Are its tools REGISTERED? (grep('build_<feature>_tools', include='ghost.py'))\n"
            "d) If it has API endpoints: does a route file exist in ghost_dashboard/routes/?\n"
            "e) If it has UI: is there JS in ghost_dashboard/static/js/pages/?\n\n"
            "## LAYER B: Functional Correctness\n"
            "For every API endpoint that accepts PUT/POST data:\n"
            "f) Read the JS code that SENDS data to the endpoint. Note the payload shape.\n"
            "g) Read the Python route that RECEIVES the data. Check what keys it reads.\n"
            "h) VERIFY the JS payload keys match what Python expects.\n"
            "   Common bug: JS sends { wrapper: { key: val } } but Python reads\n"
            "   request.get_json() and looks for 'key' at top level.\n"
            "i) For save/update endpoints: verify saved data can be read back.\n\n"
            "## LAYER C: Frontend-Backend Contract\n"
            "j) For toggle/form UIs: does the initial render read from the same source\n"
            "   that the save endpoint writes to?\n"
            "k) Does the GET endpoint return data in the shape the JS expects?\n\n"
            "## LAYER D: Rendering Completeness (THE #1 MISSED BUG)\n"
            "This layer catches the most common autonomous implementation failure:\n"
            "data exists in both backend and frontend metadata, but NEVER RENDERS\n"
            "because a hardcoded list/array controls what gets displayed.\n\n"
            "l) If the feature ADDS a new entity (provider, page, tool, option) to any\n"
            "   JS metadata object or config dict:\n"
            "   - Find the code that RENDERS/ITERATES over that object.\n"
            "   - Check: does it use Object.keys(obj), obj.forEach, or a HARDCODED array?\n"
            "   - If HARDCODED ARRAY: verify the new entity is in the array.\n"
            "   - Example bug: xAI added to PROVIDER_META = { xai: {...} } but the render\n"
            "     loop uses ['openrouter', 'openai', ...] (no 'xai') → never renders.\n"
            "   - grep for hardcoded arrays: grep(\"\\['openrouter\", include='*.js')\n"
            "m) If the feature adds a new backend entity returned by an API:\n"
            "   - Hit the API endpoint with web_fetch: http://localhost:3333/api/...\n"
            "   - Verify the new entity appears in the response.\n"
            "   - Then check the JS that consumes that API — does it render all items,\n"
            "     or filter to a hardcoded whitelist?\n"
            "n) General rule: search for ALL hardcoded lists/arrays in the same JS file\n"
            "   as the feature's changes. Any array that enumerates entities is suspect.\n"
            "   grep('const.*=.*\\[', include='<file>.js') to find them.\n\n"
            "## QUEUEING FIXES\n"
            "For each GAP found, queue a fix via add_future_feature:\n"
            "- title: 'Wiring fix: <specific issue>'\n"
            "- description: Exactly what's wrong with code evidence.\n"
            "- affected_files: The exact files that need patching.\n"
            "- proposed_approach: The EXACT code change needed.\n"
            "  For hardcoded array bugs: propose replacing the array with Object.keys(META)\n"
            "  so the bug class is eliminated permanently.\n"
            "- priority='P1', source='implementation_auditor', category='bugfix'\n\n"
            "## WHAT COUNTS AS PROPERLY IMPLEMENTED\n"
            "A feature is complete ONLY if ALL of these are true:\n"
            "- ghost.py imports and registers the module's tools\n"
            "- If it has API: endpoints respond correctly (verify with web_fetch)\n"
            "- If it has UI: the new entity actually RENDERS in the dashboard\n"
            "- If it has save/update: the JS payload format matches Python\n"
            "- If it has toggles: initial render reads from the same place save writes to\n"
            "- NO hardcoded arrays/lists bypass the new entity\n\n"
            "## IMPORTANT\n"
            "- You do NOT have evolve tools. Queue fixes via add_future_feature.\n"
            "- Be specific in your briefs — the Evolution Runner will implement them.\n"
            "- Do NOT re-audit features that already have a wiring fix queued.\n"
            "- Do NOT audit features that YOU created (title starts with 'Wiring fix:' or\n"
            "  source='implementation_auditor'). Auditing your own fixes creates infinite loops.\n"
            "- A feature that passes structural checks but FAILS rendering checks is BROKEN.\n"
            "- Use log_growth_activity to summarize: features audited, gaps found, fixes queued.\n"
            + _CODE_PATTERNS
            + _PRE_PR_CHECKLIST
            + _CAPABILITIES
        ),
    },
    {
        "id": "bug_hunter",
        "name": "Bug Hunter",
        "description": "Scan logs for errors and fix them",
        "prompt": (
            "You are Ghost running an autonomous BUG HUNTER routine. Your goal:\n"
            f"GHOST CODEBASE: {PROJECT_DIR}\n"
            "Use file_read on files in this directory to inspect source code.\n\n"
            "1. Use file_read to read ~/.ghost/log.json (recent entries).\n"
            "2. Look for error patterns: repeated failures, tool errors, crash traces.\n"
            "3. Use memory_search to check if you already fixed this issue.\n"
            "4. If you find a fixable bug:\n"
            "   a. Use file_read on the codebase to understand the relevant source code and the root cause.\n"
            "   b. Queue the fix via add_future_feature with an IMPLEMENTATION-READY BRIEF:\n"
            "      - title: 'Bug fix: <brief description>'\n"
            "      - description: Error message, traceback snippet, root cause analysis.\n"
            "      - affected_files: Exact file paths that need changes.\n"
            "      - proposed_approach: The exact fix — which function, what to change, what to guard.\n"
            "        Be specific enough that the Evolution Runner can implement WITHOUT re-investigating.\n"
            "      - priority='P1', source='bug_hunter', category='bugfix'\n"
            "5. If the issue needs user action (missing API key, expired token), "
            "use add_action_item.\n"
            "6. You do NOT have access to evolve tools. All code changes go through the queue.\n"
            "7. Use memory_save to record what you found.\n"
            "8. Use log_growth_activity to log the results.\n"
            "Focus on real bugs, not cosmetic issues."
            + _CAPABILITIES
            + _DEV_STANDARDS
        ),
    },
    {
        "id": "competitive_intel",
        "name": "AI Landscape Research",
        "description": "Research the AI agent ecosystem to find features that improve Ghost for users",
        "prompt": (
            "You are Ghost running an autonomous AI LANDSCAPE RESEARCH routine.\n"
            "Your goal is to make Ghost better for the human user by finding SPECIFIC,\n"
            "CONCRETE features that other products have and Ghost doesn't.\n\n"
            f"GHOST CODEBASE: {PROJECT_DIR}\n"
            "Use file_read on files in this directory to check Ghost's existing features. "
            "Key files: ghost.py, ghost_tools.py, ghost_providers.py, ghost_evolve.py, ghost_loop.py.\n"
            "Do NOT run 'find' commands to locate the codebase — use the path above.\n\n"
            "## RESEARCH STRATEGY — BE SPECIFIC, NOT GENERIC\n"
            "Do NOT search for broad categories like 'AI agent features' — those return\n"
            "trend articles that Ghost already covers at a high level. Instead:\n\n"
            "1. **Pick 2-3 specific products** and study their CONCRETE features:\n"
            "   Examples (rotate each run — check memory for what you researched last time):\n"
            "   - Productivity: n8n, Zapier AI, Make.com, Notion AI, Obsidian plugins\n"
            "   - Dev tools: Cursor, Windsurf, Cline, Aider, Continue.dev\n"
            "   - AI agents: CrewAI, AutoGen, LangGraph, OpenHands, Devin\n"
            "   - Personal AI: Rewind.ai, Limitless, Granola, Otter.ai\n"
            "   - Media/creative: ComfyUI workflows, Runway, ElevenLabs features\n"
            "   Search: '<product> features {current_year}' or '<product> changelog {current_year}'\n"
            "   Read their docs, GitHub READMEs, or changelogs with web_fetch.\n\n"
            "2. **Find user wishlists and pain points** with SPECIFIC searches:\n"
            "   - 'I wish my AI assistant could site:reddit.com {current_year}'\n"
            "   - 'AI agent missing feature site:news.ycombinator.com'\n"
            "   - 'personal AI assistant frustrations {current_year}'\n"
            "   - GitHub Issues on popular agent repos (sort by reactions/thumbs-up)\n\n"
            "3. **Extract SPECIFIC features, not categories.** Good vs bad examples:\n"
            "   BAD: 'Ghost needs better memory' (too vague, Ghost already has memory)\n"
            "   GOOD: 'Auto-summarize Slack threads and save key decisions to memory'\n"
            "   BAD: 'Ghost needs workflow automation' (too vague)\n"
            "   GOOD: 'Scheduled PDF report generator that emails weekly summaries'\n"
            "   BAD: 'Ghost needs coding assistance' (Ghost already has code tools)\n"
            "   GOOD: 'Git PR review tool that comments on diffs with suggestions'\n\n"
            "4. Use memory_search('landscape-research') to check previous research and\n"
            "   ROTATE to different products/sources each run. Don't repeat the same searches.\n\n"
            "5. For each specific feature found:\n"
            "   a. Describe the CONCRETE workflow: what the user does, what happens, what output.\n"
            "   b. Check if Ghost ALREADY HAS this SPECIFIC workflow:\n"
            "      - grep(key_term, include='*.py') for each key technology/package name\n"
            "      - Also check ghost_extensions/ and ghost_nodes/ for existing extensions/nodes\n"
            "      - file_read requirements.txt to check if packages are already installed\n"
            "      - If grep finds matches, file_read the matching files to confirm it's working code\n"
            "      - Ghost having a GENERAL capability (e.g. 'memory') does NOT mean it has\n"
            "        the SPECIFIC workflow (e.g. 'auto-summarize meetings and save to memory').\n"
            "   c. If it's genuinely missing, design it as an extension and queue it.\n"
            "   d. Assess priority: P1 (high user impact), P2 (nice-to-have), P3 (low).\n\n"
            "## EXTENSION-FIRST ARCHITECTURE\n"
            "Ghost uses an EXTENSION system for new features. New capabilities are built as\n"
            "self-contained extensions in ghost_extensions/<name>/, NOT as modifications to\n"
            "core Ghost files. Only bug fixes and security patches modify core files.\n\n"
            "When you find a feature Ghost should have, design it as an extension:\n"
            "- What TOOLS would it register? (the main capability)\n"
            "- What HOOKS does it need? (on_chat_message, on_media_generated, etc.)\n"
            "- Does it need a DASHBOARD PAGE?\n"
            "- Does it need CRON JOBS?\n\n"
            "5. **MANDATORY: Call add_future_feature() for EVERY actionable finding.**\n"
            "   DO NOT just write a report. DO NOT just summarize findings in task_complete.\n"
            "   If you found a feature Ghost should have, you MUST call add_future_feature().\n"
            "   For each call, provide an IMPLEMENTATION-READY BRIEF:\n"
            "   - description: What the feature does and why it benefits Ghost users.\n"
            "   - affected_files: 'ghost_extensions/<name>/EXTENSION.yaml, "
            "ghost_extensions/<name>/extension.py' (add static/<page>.js if it needs UI).\n"
            "     Use UNDERSCORES in names (e.g. my_feature), NEVER hyphens.\n"
            "   - proposed_approach: Extension design — what tools/hooks/pages/cron the\n"
            "     extension registers via ExtensionAPI. What pip packages it needs.\n"
            "   - source='competitive_intel', category='feature'\n"
            "   - source_detail: Source URL (article, repo, discussion)\n"
            "   - estimated_effort: small/medium/large based on complexity\n"
            "   - tags: relevant domain tags (e.g. 'productivity,automation')\n"
            "   The queue system handles everything else. P1/P2 features auto-implement.\n"
            "6. You do NOT have access to evolve tools. All code changes go through the queue.\n"
            "7. Use memory_save to record findings (tag: landscape-research).\n"
            "8. Use log_growth_activity to log what you discovered and actions taken.\n\n"
            "## MINIMUM OUTPUT EXPECTATIONS\n"
            "Every run MUST queue at least 1-2 concrete features via add_future_feature().\n"
            "If you can't find gaps, you're searching too broadly. Dig deeper:\n"
            "- Read a specific product's feature page and compare feature-by-feature\n"
            "- Read GitHub Issues sorted by most-upvoted on an agent repo\n"
            "- Read a 'what I built with AI' Reddit thread for workflow inspiration\n"
            "A run that queues ZERO features means the research was too shallow.\n\n"
            "Ghost is a batteries-included AI agent. Think about SPECIFIC workflows the user\n"
            "would love to have. Study CONCEPTS from any source, then design a Ghost EXTENSION.\n"
            + _CAPABILITIES
            + _DEV_STANDARDS
        ),
    },
    {
        "id": "visual_monitor",
        "name": "Visual Monitor",
        "description": "Take and analyze screenshots to monitor Ghost's visual environment",
        "prompt": (
            "You are Ghost running an autonomous VISUAL MONITOR routine. Your goal:\n"
            "1. Use screenshot_analyze to check the most recent screenshot (if any).\n"
            "2. Look for anomalies: error dialogs, crash screens, unusual UI states.\n"
            "3. If no screenshots are available, skip gracefully.\n"
            "4. Check if the dashboard is accessible by using web_fetch on "
            "http://localhost:3333 (or configured port).\n"
            "5. If you find visual anomalies:\n"
            "   - For error dialogs: log the error and attempt to diagnose.\n"
            "   - For dashboard issues: check if the server is running.\n"
            "6. Use log_growth_activity to summarize findings.\n"
            "7. Use memory_save to store any visual context that might be useful.\n"
            "Be brief. Only report meaningful findings."
        ),
    },
    {
        "id": "security_patrol",
        "name": "Security Patrol",
        "description": "AI-driven security audit — investigate, fix, and harden autonomously",
        "prompt": (
            "You are Ghost running an autonomous SECURITY PATROL routine.\n"
            "You are the auditor. Investigate, diagnose, and queue fixes.\n\n"
            "## Step 1: Scan (READ-ONLY)\n"
            "Call security_audit for baseline. Investigate with config_get, "
            "shell_exec (read-only: ls -la ~/.ghost/, ps aux, lsof), file_read.\n\n"
            "## Step 1.5: Capability-Impact Checklist (MANDATORY)\n"
            "Before proposing shell allowlist hardening, assess impact on autonomy, self-repair, evolution, setup-doctor.\n"
            "Do not propose blanket removals of autonomy-critical commands without guarded alternatives.\n"
            "Prefer policy gates, elevated confirmation, and audit logs over broad capability removal.\n"
            "Include evidence + mitigations in each feature brief.\n\n"
            "## FORBIDDEN — Shell Allowlist\n"
            "The allowed_commands list is USER-MANAGED via the Config page.\n"
            "You MUST NOT propose removing commands from DEFAULT_ALLOWED_COMMANDS or CORE_COMMANDS.\n"
            "You MUST NOT propose modifying ghost_tools.py to change the command lists.\n"
            "You MUST NOT queue features that reduce the allowed_commands in config.\n"
            "If a command is dangerous, propose adding it to blocked_commands or using\n"
            "the dangerous_command_policy gate instead of removing it from the allowlist.\n\n"
            "## Step 2: Queue Fixes\n"
            "For each issue found, queue a fix via add_future_feature with an IMPLEMENTATION-READY BRIEF:\n"
            "- title: 'Security fix: <brief description>'\n"
            "- description: The vulnerability, risk level, and root cause.\n"
            "- affected_files: Exact file paths that need hardening.\n"
            "- proposed_approach: The exact fix — which functions to change, what validation to add,\n"
            "  what config keys to set. Be specific enough that the Evolution Runner can implement\n"
            "  WITHOUT re-investigating.\n"
            "  If shell policy is touched, include capability-impact evidence + mitigations\n"
            "  (policy gate, elevated confirmation, audit logging, regression checks).\n"
            "- priority='P1', source='other', category='security'\n"
            "P1 features trigger the Evolution Runner immediately.\n\n"
            "## Step 3: Report\n"
            "- Permission issues or things needing user action: use add_action_item.\n"
            "- Use memory_save to log findings (tag: security-patrol).\n"
            "- Use log_growth_activity to summarize what you found.\n\n"
            "You do NOT have access to evolve tools. All code changes go through the\n"
            "Future Features queue. The Evolution Runner implements them serially.\n"
            "FORBIDDEN: shell_exec for writes, file_write. Read-only investigation only."
            + _CAPABILITIES
        ),
    },
    {
        "id": "content_health",
        "name": "Content Health Check",
        "description": "Test web_fetch extraction quality on sample URLs",
        "prompt": (
            "You are Ghost running a CONTENT EXTRACTION HEALTH CHECK routine. Your goal:\n"
            "1. Use web_fetch_status to check which extraction tiers are available.\n"
            "2. Test web_fetch on 3-5 diverse URLs to verify extraction quality:\n"
            "   - A news article (e.g. https://www.bbc.com/news)\n"
            "   - Technical documentation (e.g. https://docs.python.org/3/tutorial/index.html)\n"
            "   - A GitHub README (e.g. https://github.com/python/cpython)\n"
            "   - A blog post from a popular tech blog\n"
            "3. For each URL, verify:\n"
            "   - Output is clean markdown with actual article content\n"
            "   - Navigation bars, ads, and boilerplate are stripped\n"
            "   - Title is correctly extracted\n"
            "   - Extractor used (readability, firecrawl, basic) — basic is a red flag\n"
            "4. If extraction quality is poor (mostly 'basic' extractor, missing content):\n"
            "   - Check if readability-lxml is installed: shell_exec(command='pip list | grep readability')\n"
            "   - If not installed: shell_exec(command='pip install readability-lxml html2text lxml')\n"
            "5. If Firecrawl is not configured, note it as a recommendation via add_action_item.\n"
            "6. Use memory_save to log results with tag 'content_health'.\n"
            "7. Use log_growth_activity to summarize the health check.\n"
            "Be concise. Focus on whether extraction is working, not on the content itself."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════
#  BOOTSTRAP — Register growth cron jobs
# ═══════════════════════════════════════════════════════════════

def bootstrap_growth_cron(cron_service, cfg):
    """Register growth routines as cron jobs. Idempotent — skips already registered."""
    if not cron_service or not cfg.get("enable_growth", True):
        return

    schedules = cfg.get("growth_schedules", {})
    store = cron_service.store

    from ghost_cron import make_job
    existing_jobs = {j["name"]: j for j in store.get_all()}

    for routine in GROWTH_ROUTINES:
        job_name = f"{GROWTH_JOB_PREFIX}{routine['id']}"

        if routine.get("event_driven"):
            target_schedule = {"kind": "manual"}
        else:
            cron_expr = schedules.get(routine["id"],
                                      DEFAULT_GROWTH_SCHEDULES.get(routine["id"], "0 */6 * * *"))
            target_schedule = {"kind": "cron", "expr": cron_expr}

        existing = existing_jobs.get(job_name)
        if existing:
            updates = {}
            # Migrate schedule if kind changed (e.g. cron → manual for event_driven)
            if existing.get("schedule", {}).get("kind") != target_schedule.get("kind"):
                updates["schedule"] = target_schedule
            # Always refresh the payload so prompt changes take effect immediately
            current_prompt = existing.get("payload", {}).get("prompt", "")
            if current_prompt != routine["prompt"]:
                updates["payload"] = {"type": "task", "prompt": routine["prompt"]}
            if updates:
                store.update(existing["id"], updates)
            continue

        job = make_job(
            name=job_name,
            schedule=target_schedule,
            payload={"type": "task", "prompt": routine["prompt"]},
            description=routine["description"],
            enabled=True,
        )
        store.add(job)

    cron_service._arm_timer()


def reschedule_growth_cron(cron_service, cfg):
    """Update growth cron schedules from config without restart."""
    if not cron_service:
        return

    schedules = cfg.get("growth_schedules", {})
    store = cron_service.store
    jobs = store.get_all()

    for routine in GROWTH_ROUTINES:
        if routine.get("event_driven"):
            continue
        job_name = f"{GROWTH_JOB_PREFIX}{routine['id']}"
        new_expr = schedules.get(routine["id"],
                                 DEFAULT_GROWTH_SCHEDULES.get(routine["id"]))
        if not new_expr:
            continue

        for job in jobs:
            if job["name"] == job_name:
                if job["schedule"].get("expr") != new_expr:
                    from ghost_cron import compute_next_run
                    new_schedule = dict(job["schedule"])
                    new_schedule["expr"] = new_expr
                    next_run = compute_next_run(new_schedule, job["id"])
                    store.update(job["id"], {
                        "schedule": new_schedule,
                        "state": {**job.get("state", {}), "nextRunAtMs": next_run},
                    })
                break

    cron_service._arm_timer()


# ═══════════════════════════════════════════════════════════════
#  LLM TOOLS — exposed to the AI agent
# ═══════════════════════════════════════════════════════════════

def _try_channel_notify(channel_router, text: str, priority: str = "normal"):
    """Best-effort push notification via the multi-channel messaging system."""
    if not channel_router:
        return
    try:
        channel_router.send(text, priority=priority, title="Ghost Autonomy")
    except Exception:
        pass


def build_autonomy_tools(action_store: ActionItemStore, growth_logger: GrowthLogger,
                         channel_router=None):
    """Build LLM-callable tools for the autonomy system."""

    def add_action_item_exec(title, description, category="general", priority="info"):
        item = action_store.add(title, description, category, priority)
        if item.get("_duplicate"):
            return f"Action item already exists: [{item['id']}] {title} (status: pending). No duplicate created."
        notify_prio = {"critical": "high", "warning": "normal"}.get(priority, "low")
        _try_channel_notify(
            channel_router,
            f"**Action Required: {title}**\n{description}",
            priority=notify_prio,
        )
        return f"Action item created: [{item['id']}] {title} (priority: {priority})"

    def log_growth_exec(routine, summary, details="", category="growth"):
        entry = growth_logger.log(routine, summary, details, category)
        warning = entry.get("_warning", "")
        if warning:
            return f"{warning}\nDuplicate not sent to notifications. Entry ID: [{entry['id']}]"
        _try_channel_notify(
            channel_router,
            f"**Growth [{routine}]**: {summary}",
            priority="low",
        )
        return f"Growth logged: [{entry['id']}] {summary}"

    return [
        {
            "name": "add_action_item",
            "description": (
                "Post an action item for the user — something only they can do "
                "(provide API keys, enable services, approve settings). "
                "The user sees these in the dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the action"},
                    "description": {"type": "string", "description": "What the user needs to do and why"},
                    "category": {
                        "type": "string",
                        "description": "Category: api_key, integration, config, security, other",
                        "default": "general",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Priority: critical, warning, info",
                        "default": "info",
                    },
                },
                "required": ["title", "description"],
            },
            "execute": add_action_item_exec,
        },
        {
            "name": "log_growth_activity",
            "description": (
                "Log an autonomous growth activity — what you improved, fixed, or discovered. "
                "This appears in the Growth Log on the dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "routine": {"type": "string", "description": "Which routine: tech_scout, health_check, user_context, skill_improver, soul_evolver, bug_hunter, competitive_intel (landscape research), self_repair"},
                    "summary": {"type": "string", "description": "One-line summary of what was done"},
                    "details": {"type": "string", "description": "Detailed description (optional)", "default": ""},
                    "category": {"type": "string", "description": "Category: growth, fix, skill, health, context", "default": "growth"},
                },
                "required": ["routine", "summary"],
            },
            "execute": log_growth_exec,
        },
    ]


# ═══════════════════════════════════════════════════════════════
#  SELF-REPAIR — runs on startup if crash report exists
# ═══════════════════════════════════════════════════════════════

def run_self_repair(daemon):
    """If a crash report exists, feed it to the LLM for diagnosis and fix."""
    if not CRASH_REPORT_FILE.exists():
        return False

    try:
        report = json.loads(CRASH_REPORT_FILE.read_text(encoding="utf-8"))
    except Exception:
        CRASH_REPORT_FILE.unlink(missing_ok=True)
        return False

    stderr_text = "\n".join(report.get("stderr_tail", []))
    exit_code = report.get("exit_code", "unknown")
    crash_count = report.get("crash_count", 1)

    if crash_count >= report.get("max_crashes_before_rollback", 5) - 1:
        print("  [AUTONOMY] Too many crashes — skipping self-repair, supervisor will rollback")
        CRASH_REPORT_FILE.unlink(missing_ok=True)
        return False

    print(f"  [AUTONOMY] Crash report found (exit code {exit_code}, crash #{crash_count})")
    print("  [AUTONOMY] Running self-repair...")

    deleted_files_context = ""
    deleted_log_path = GHOST_HOME / "evolve" / "deleted_files.json"
    if deleted_log_path.exists():
        try:
            deleted_log = json.loads(deleted_log_path.read_text(encoding="utf-8"))
            if deleted_log:
                recently_deleted = [
                    e for e in deleted_log
                    if time.time() - e.get("timestamp", 0) < 86400 * 7
                ]
                if recently_deleted:
                    files_list = ", ".join(e["file"] for e in recently_deleted)
                    deleted_files_context = (
                        f"\n## INTENTIONALLY DELETED FILES (do NOT restore these):\n"
                        f"The following files were intentionally deleted by the user or a previous evolution: "
                        f"{files_list}\n"
                        f"If the crash is caused by another file trying to import a deleted module, "
                        f"the fix is to REMOVE the import from the importing file — NOT to recreate "
                        f"the deleted file.\n"
                    )
        except Exception:
            pass

    repair_prompt = (
        f"Ghost crashed with exit code {exit_code}. This is crash #{crash_count}.\n\n"
        f"## STDERR OUTPUT (last {len(report.get('stderr_tail', []))} lines):\n"
        f"```\n{stderr_text}\n```\n"
        f"{deleted_files_context}\n"
        "## YOUR TASK:\n"
        "1. Analyze the traceback to identify the root cause.\n"
        "2. If the crash is caused by an import of a deleted module (see INTENTIONALLY DELETED FILES above):\n"
        "   - The fix is to REMOVE or GUARD the import in the file that's crashing.\n"
        "   - NEVER recreate or restore a file that was intentionally deleted.\n"
        "3. If it's a code bug in Ghost's source files:\n"
        "   - Use file_read to inspect the failing file and line.\n"
        "   - Use evolve_plan to plan the fix (you have evolve access in self-repair mode).\n"
        "   - Use evolve_apply with patches to fix the bug.\n"
        "   - Use evolve_test to verify.\n"
        "   - Use evolve_deploy to restart with the fix.\n"
        "   NOTE: Self-repair is the ONLY routine with direct evolve access besides the\n"
        "   Feature Implementer. This is because crash recovery must happen immediately.\n"
        "4. If it's a missing Python dependency: install it yourself with "
        "shell_exec(command='pip install <package>'). Ghost runs in a venv. requirements.txt is auto-updated — do NOT edit it manually.\n"
        "5. If it's a configuration or environment issue that truly requires user action "
        "(missing API key, hardware setup):\n"
        "   - Use add_action_item to tell the user what needs to be fixed.\n"
        "6. Use log_growth_activity with routine='self_repair' to log what you did.\n"
        "7. Be precise and minimal — fix only the crash cause, nothing else.\n"
        "8. Follow modular architecture: if a fix needs new code, create a new file — "
        "don't dump into existing modules beyond their responsibility.\n"
        "9. Follow security best practices: validate inputs, sanitize paths, never hardcode secrets.\n\n"
        f"Ghost project root: {PROJECT_DIR}\n"
        + _CAPABILITIES
    )

    SELF_REPAIR_TIMEOUT_S = 120  # 2 minutes max — if it takes longer, something is wrong

    try:
        identity = daemon._build_identity_context()
        system_prompt = (
            identity +
            "You are Ghost in SELF-REPAIR mode. You just crashed and the supervisor restarted you. "
            "Your job is to diagnose and fix the crash so it doesn't happen again. "
            "Be surgical — fix only the crash cause.\n"
        )

        old_auto = daemon.cfg.get("evolve_auto_approve", False)
        daemon.cfg["evolve_auto_approve"] = True

        import threading

        repair_result = [None]
        repair_error = [None]

        def _run_repair():
            try:
                repair_result[0] = daemon.engine.run(
                    system_prompt=system_prompt,
                    user_message=repair_prompt,
                    tool_registry=daemon.tool_registry,
                    max_steps=50,
                    max_tokens=4096,
                    force_tool=False,
                    extension_event_bus=getattr(daemon, "extension_event_bus", None),
                )
            except Exception as e:
                repair_error[0] = e

        repair_thread = threading.Thread(target=_run_repair, daemon=True)
        repair_thread.start()
        repair_thread.join(timeout=SELF_REPAIR_TIMEOUT_S)

        daemon.cfg["evolve_auto_approve"] = old_auto

        if repair_thread.is_alive():
            print(f"  [AUTONOMY] Self-repair timed out after {SELF_REPAIR_TIMEOUT_S}s — "
                  "skipping (Ghost stays alive)")
            CRASH_REPORT_FILE.unlink(missing_ok=True)
            return False

        if repair_error[0]:
            raise repair_error[0]

        result = repair_result[0]
        print(f"  [AUTONOMY] Self-repair complete: {(result.text or '')[:200]}")

        CRASH_REPORT_FILE.unlink(missing_ok=True)
        return True

    except Exception as e:
        print(f"  [AUTONOMY] Self-repair failed: {e}")
        CRASH_REPORT_FILE.unlink(missing_ok=True)
        return False
