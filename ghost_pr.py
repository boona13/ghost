"""
Ghost PR System — pull request management and adversarial code review.

Provides:
  - PRStore: CRUD for internal pull requests (stored in ~/.ghost/prs/)
  - ReviewEngine: multi-persona dialogue between Reviewer and Developer personas
  - build_pr_tools(): LLM-callable tools for the evolve pipeline

The review loop runs synchronously: Developer submits a PR, Reviewer examines
the diff, they discuss back and forth, and the Reviewer renders a verdict
(approve, request_changes, or block) — all within one session.
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_HOME = Path.home() / ".ghost"
PR_DIR = GHOST_HOME / "prs"
PR_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("ghost.pr")

# ── Review System Prompt ──────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
You are a strict, senior code reviewer protecting the codebase from regressions, \
bugs, and bad design. Ghost has shipped 42+ documented bugs. Your job is to \
stop the next one. Check EVERY section below.

### Code Quality
- Security: input validation, path sanitization, no hardcoded secrets
- Correctness: logic bugs, off-by-one, race conditions, error handling
- Simplicity: no over-engineering, no unnecessary abstractions
- No bare `except: pass` or `except Exception: pass` that swallows real errors

### UI/UX Quality
- Modals MUST default to hidden, be dismissable (X, overlay click, Escape)
- Forms MUST use proper input types, follow dashboard dark theme patterns
- SVG icons, not emojis; use stat-card, btn, form-input, badge classes

### Frontend-Backend Integration (MOST DAMAGING — caused M-14, M-15, M-23)
- Backend API added = frontend UI MUST call it
- Frontend UI added = backend MUST persist and return data
- Feature MUST be wired into runtime (not just dead CRUD + UI)
- JS payload shape MUST match Python route's request.get_json()
- API responses MUST return live data, not stale defaults

### Tool Registration and Wiring (caused M-15, M-29, M-30)
- New module = MUST be imported in ghost.py
- New build_*_tools() = MUST be called in GhostDaemon.__init__
- New tool defs = MUST be registered via tool_registry.register()
- If any of these are missing, the feature is dead code — BLOCK it

### Tool Execute Signatures (caused 6+ TypeError crashes)
- Every tool execute function MUST accept **kwargs or match the schema exactly
- Optional params MUST have defaults (e.g. `_=None`, `limit=50`)
- If schema says `"required": ["x"]`, execute MUST accept `x` as keyword arg

### Thread Safety and File I/O (caused PR rejections)
- Shared files (log.json, config.json, growth_log.json) need locking or atomic writes
- Write to new paths = `Path.mkdir(parents=True, exist_ok=True)` first
- Prefer atomic write pattern: write to temp file, then `os.replace()`
- Never read an entire unbounded file into memory — use limits or tail reads
- No read-modify-write without a lock when multiple threads can access the file

### Python Correctness (caused M-06, M-07)
- NEVER `from module import mutable_var` (dead copy) — use `import module; module.var`
- No double-escaped strings: `"\\n".join()` is WRONG, `"\n".join()` is RIGHT
- No blocking I/O at module level or in `__init__` (no pip install, no network calls)

### Duplicate Functionality (caused M-17)
- Does this PR add something that already exists in the codebase?
- Check: is there an existing tool, module, or route that does the same thing?
- If EXISTING CODE MATCHES are provided below, verify those files don't already implement this feature.
- If the feature is already working in the codebase: VERDICT: BLOCK — "already implemented"

### Scope
- PR should do ONE thing. Flag unrelated changes.
- Multi-scope changes = REQUEST_CHANGES to split them.

**Response format as REVIEWER:**
1. Brief summary (1-2 sentences)
2. Specific concerns with line references from the diff
3. End with EXACTLY ONE verdict:
   VERDICT: APPROVE — safe, correct, well-integrated
   VERDICT: REQUEST_CHANGES — specific issues to fix (list them)
   VERDICT: BLOCK — fundamentally wrong approach

"""

MAX_REVIEW_ROUNDS = 3


# ── PR Store ─────────────────────────────────────────────────────────

class PRStore:
    """CRUD for pull requests, stored as JSON files in ~/.ghost/prs/.

    All writes are serialized through _lock so dashboard force-actions
    and the review loop can't corrupt a PR file with concurrent writes.
    """

    _lock = threading.Lock()

    def _read_pr_unlocked(self, pr_id: str) -> Optional[Dict]:
        path = PR_DIR / f"{pr_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def _write_pr_unlocked(self, pr: Dict):
        path = PR_DIR / f"{pr['pr_id']}.json"
        path.write_text(json.dumps(pr, indent=2, default=str))

    def create_pr(self, evolution_id: str, feature_id: str, title: str,
                  description: str, branch: str, diff: str,
                  files_changed: list[str]) -> Dict[str, Any]:
        pr_id = f"pr-{uuid.uuid4().hex[:10]}"
        pr = {
            "pr_id": pr_id,
            "evolution_id": evolution_id,
            "feature_id": feature_id,
            "branch": branch,
            "title": title,
            "description": description,
            "status": "open",
            "diff": diff,
            "files_changed": files_changed,
            "discussions": [],
            "review_rounds": 0,
            "max_rounds": MAX_REVIEW_ROUNDS,
            "verdict": None,
            "blocked_reason": None,
            "created_at": datetime.now().isoformat(),
            "merged_at": None,
        }
        self._save_pr(pr)
        log.info("PR created: %s for evolution %s", pr_id, evolution_id)
        return pr

    def get_pr(self, pr_id: str) -> Optional[Dict]:
        with self._lock:
            return self._read_pr_unlocked(pr_id)

    def list_prs(self, status: Optional[str] = None,
                 feature_id: Optional[str] = None) -> List[Dict]:
        with self._lock:
            prs = []
            for f in sorted(PR_DIR.glob("pr-*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    pr = json.loads(f.read_text())
                    if status and pr.get("status") != status:
                        continue
                    if feature_id and pr.get("feature_id") != feature_id:
                        continue
                    prs.append(pr)
                except Exception:
                    continue
            return prs

    def update_status(self, pr_id: str, status: str) -> bool:
        with self._lock:
            pr = self._read_pr_unlocked(pr_id)
            if not pr:
                return False
            pr["status"] = status
            self._write_pr_unlocked(pr)
            return True

    def add_discussion(self, pr_id: str, role: str, message: str,
                       round_num: int) -> bool:
        with self._lock:
            pr = self._read_pr_unlocked(pr_id)
            if not pr:
                return False
            pr["discussions"].append({
                "role": role,
                "message": message,
                "round": round_num,
                "timestamp": datetime.now().isoformat(),
            })
            pr["review_rounds"] = round_num
            self._write_pr_unlocked(pr)
            return True

    def set_verdict(self, pr_id: str, verdict: str,
                    reason: Optional[str] = None) -> bool:
        with self._lock:
            pr = self._read_pr_unlocked(pr_id)
            if not pr:
                return False
            pr["verdict"] = verdict
            if verdict == "approved":
                pr["status"] = "approved"
            elif verdict == "blocked":
                pr["status"] = "blocked"
                pr["blocked_reason"] = reason
            elif verdict == "rejected":
                pr["status"] = "rejected"
            self._write_pr_unlocked(pr)
            return True

    def mark_merged(self, pr_id: str) -> bool:
        with self._lock:
            pr = self._read_pr_unlocked(pr_id)
            if not pr:
                return False
            pr["status"] = "merged"
            pr["merged_at"] = datetime.now().isoformat()
            self._write_pr_unlocked(pr)
            return True

    def update_diff(self, pr_id: str, diff: str,
                    files_changed: list[str]) -> bool:
        with self._lock:
            pr = self._read_pr_unlocked(pr_id)
            if not pr:
                return False
            pr["diff"] = diff
            pr["files_changed"] = files_changed
            self._write_pr_unlocked(pr)
            return True

    def _save_pr(self, pr: Dict):
        with self._lock:
            self._write_pr_unlocked(pr)


# ── Review Engine ────────────────────────────────────────────────────

class ReviewEngine:
    """Orchestrates code review as a real multi-turn conversation.

    Instead of isolated single_shot() calls that rebuild massive context
    each time, the review runs as one continuous chat thread. The diff is
    sent once, and the LLM role-plays reviewer/developer on alternating
    turns via short turn markers.
    """

    def __init__(self, store: PRStore, evolve_engine=None):
        self.store = store
        self.evolve_engine = evolve_engine

    # ── Direct LLM chat (bypasses ToolLoopEngine) ────────────────────

    @staticmethod
    def _chat(engine, messages, max_tokens=8192, temperature=0.3):
        """Send the conversation to the LLM and return the assistant text.

        Uses engine._call_llm() directly — no tool loop, no pushback,
        no loop detection. Just a plain chat completion.
        Returns None on any failure.
        """
        payload = {
            "model": engine.model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            data, error = engine._call_llm(payload)
        except Exception as exc:
            log.warning("LLM call raised: %s", exc)
            return None
        if error or not data:
            log.warning("LLM call failed: %s", error)
            return None
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            return None
        text = (choices[0].get("message", {}).get("content") or "").strip()
        return text or None

    # ── Diff preparation ─────────────────────────────────────────────

    @staticmethod
    def _prepare_diff(raw_diff: str, max_chars: int = 40000) -> str:
        """Prepare diff for reviewer, prioritizing new files over patches.

        New files are shown in full (reviewer needs complete code to verify
        tool signatures, imports, etc.). Patches to existing files are
        truncated if the total exceeds max_chars.
        """
        if len(raw_diff) <= max_chars:
            return raw_diff

        new_file_parts = []
        patch_parts = []
        current_part = []
        is_new_file = False

        for line in raw_diff.split("\n"):
            if line.startswith("diff --git"):
                if current_part:
                    target = new_file_parts if is_new_file else patch_parts
                    target.append("\n".join(current_part))
                current_part = [line]
                is_new_file = False
            elif line.startswith("new file mode"):
                is_new_file = True
                current_part.append(line)
            else:
                current_part.append(line)

        if current_part:
            target = new_file_parts if is_new_file else patch_parts
            target.append("\n".join(current_part))

        new_text = "\n".join(new_file_parts)
        remaining = max_chars - len(new_text)

        if remaining > 2000:
            patch_text = "\n".join(patch_parts)
            if len(patch_text) > remaining:
                patch_text = patch_text[:remaining] + "\n\n[... patches truncated for length, new files shown in full above ...]"
            return new_text + "\n" + patch_text if new_text else patch_text
        else:
            return new_text[:max_chars] + "\n\n[... truncated ...]"

    # ── Main review loop ─────────────────────────────────────────────

    def run_review(self, pr_id: str, engine) -> str:
        """Run a single-round code review. Returns: approved/rejected/blocked.

        The reviewer examines the diff once and renders a final verdict.
        If the verdict is not APPROVE, the PR is rejected immediately so
        the feature can be re-queued with the feedback incorporated into
        the next evolution attempt.
        """
        pr = self.store.get_pr(pr_id)
        if not pr:
            return "rejected"

        self.store.update_status(pr_id, "reviewing")
        log.info("Starting review for PR %s: %s", pr_id, pr["title"])

        diff_text = self._prepare_diff(pr["diff"])
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"## Pull Request: {pr['title']}\n"
                f"**Description:** {pr['description']}\n"
                f"**Files changed:** {', '.join(pr['files_changed'])}\n\n"
                f"```diff\n{diff_text}\n```"
            )},
            {"role": "user", "content": (
                "**REVIEWER:** Review the diff above. Check code quality, "
                "correctness, UI/UX, frontend-backend integration, and scope. "
                "End with your VERDICT."
            )},
        ]

        # Inject rejection history so the reviewer can verify past issues were fixed
        if pr.get("feature_id"):
            try:
                from ghost_future_features import FutureFeaturesStore
                feat = FutureFeaturesStore().get_by_id(pr["feature_id"])
                rejections = feat.get("pr_rejections", []) if feat else []
                if rejections:
                    history_text = "\n".join(
                        f"- Attempt {r.get('attempt', i+1)}: {r.get('feedback', 'unknown')[:300]}"
                        for i, r in enumerate(rejections[-3:])
                    )
                    messages.insert(2, {"role": "user", "content": (
                        f"**REJECTION HISTORY** — This feature has been rejected "
                        f"{len(rejections)} time(s) before. Previous feedback:\n"
                        f"{history_text}\n\n"
                        "Pay SPECIAL attention to whether these specific issues were fixed."
                    )})
            except Exception:
                pass

        # Codebase context: help reviewer detect duplicate/already-implemented features
        try:
            import subprocess
            _stopwords = {
                "the", "and", "for", "with", "from", "that", "this", "into",
                "add", "fix", "bug", "feature", "ghost", "update", "implement",
                "new", "support", "enable", "create", "make", "use", "set",
            }
            title_words = [
                w.lower() for w in pr["title"].split()
                if len(w) > 3 and w.lower() not in _stopwords
            ]
            pr_files_abs = set()
            for pf in pr.get("files_changed", []):
                pr_files_abs.add(str(PROJECT_DIR / pf))
                pr_files_abs.add(str(pf))
            hits = []
            for term in title_words[:3]:
                result = subprocess.run(
                    ["grep", "-ril", term, "--include=*.py", str(PROJECT_DIR)],
                    capture_output=True, text=True, timeout=5,
                )
                for fpath in result.stdout.strip().split("\n"):
                    fpath = fpath.strip()
                    if fpath and fpath not in pr_files_abs and ".venv" not in fpath:
                        hits.append(f"'{term}' found in {fpath}")
            if hits:
                existing_context = (
                    "**EXISTING CODE MATCHES** — files NOT in this PR that already "
                    "reference feature keywords:\n"
                    + "\n".join(f"- {h}" for h in hits[:10])
                    + "\n\nIf these files already implement what this PR adds, "
                    "the feature is a duplicate. VERDICT: BLOCK — 'already implemented'."
                )
                messages.insert(-1, {"role": "user", "content": existing_context})
        except Exception:
            pass

        log.info("Review round 1/1 for PR %s", pr_id)
        reviewer_text = self._chat(engine, messages)
        if not reviewer_text:
            log.warning("Reviewer produced no response — rejecting")
            self.store.set_verdict(pr_id, "rejected",
                "LLM failed to produce reviewer response")
            return "rejected"

        self.store.add_discussion(pr_id, "reviewer", reviewer_text, 1)
        verdict = self._parse_verdict(reviewer_text)
        log.info("Reviewer verdict: %s", verdict)

        if verdict == "approve":
            self.store.set_verdict(pr_id, "approved")
            return "approved"

        if verdict == "block":
            reason = self._extract_block_reason(reviewer_text)
            self.store.set_verdict(pr_id, "blocked", reason)
            return "blocked"

        reason = self._extract_change_requests(reviewer_text)
        self.store.set_verdict(pr_id, "rejected", reason)
        log.info("PR %s rejected: reviewer requested changes", pr_id)
        return "rejected"

    def _parse_verdict(self, response: str) -> str:
        response_upper = response.upper()
        if "VERDICT: APPROVE" in response_upper:
            return "approve"
        if "VERDICT: BLOCK" in response_upper:
            return "block"
        if "VERDICT: REQUEST_CHANGES" in response_upper:
            return "request_changes"
        if "VERDICT:" in response_upper:
            after = response_upper.split("VERDICT:")[-1].strip()[:20]
            if "APPROVE" in after:
                return "approve"
            if "BLOCK" in after:
                return "block"
        return "request_changes"

    def _extract_block_reason(self, response: str) -> str:
        lines = response.split("\n")
        for i, line in enumerate(lines):
            if "VERDICT: BLOCK" in line.upper():
                rest = line.split("BLOCK")[-1].strip(" —-:")
                if rest:
                    return rest
                if i + 1 < len(lines):
                    return lines[i + 1].strip()
        return "Blocked by reviewer"

    def _extract_change_requests(self, response: str) -> str:
        """Extract the reviewer's concerns as a concise rejection reason."""
        lines = response.split("\n")
        concerns = []
        for line in lines:
            stripped = line.strip()
            if stripped and stripped[0:1].isdigit() and "." in stripped[:4]:
                concerns.append(stripped)
            elif stripped.startswith("- **") or stripped.startswith("* **"):
                concerns.append(stripped)
        if concerns:
            return "\n".join(concerns[:10])
        summary_line = lines[0].strip() if lines else ""
        return summary_line[:500] or "Reviewer requested changes"


# ── Singleton ────────────────────────────────────────────────────────

_pr_store: Optional[PRStore] = None
_review_engine: Optional[ReviewEngine] = None


def get_pr_store() -> PRStore:
    global _pr_store
    if _pr_store is None:
        _pr_store = PRStore()
    return _pr_store


def get_review_engine(evolve_engine=None) -> ReviewEngine:
    global _review_engine
    if _review_engine is None:
        _review_engine = ReviewEngine(get_pr_store(), evolve_engine)
    elif evolve_engine and _review_engine.evolve_engine is None:
        _review_engine.evolve_engine = evolve_engine
    return _review_engine


# ── LLM Tools ────────────────────────────────────────────────────────

def build_pr_tools(cfg: dict = None) -> list[dict]:
    """Build LLM-callable tools for PR management."""
    store = get_pr_store()

    def list_prs_exec(status=None, feature_id=None):
        prs = store.list_prs(status=status, feature_id=feature_id)
        if not prs:
            return "No pull requests found."
        lines = [f"Found {len(prs)} PR(s):"]
        for pr in prs[:20]:
            verdict_str = f" [{pr['verdict']}]" if pr.get("verdict") else ""
            lines.append(
                f"  {pr['pr_id']}: {pr['title']} "
                f"(status={pr['status']}{verdict_str}, "
                f"rounds={pr['review_rounds']}, "
                f"branch={pr['branch']})"
            )
        return "\n".join(lines)

    def get_pr_exec(pr_id):
        pr = store.get_pr(pr_id)
        if not pr:
            return f"PR not found: {pr_id}"
        lines = [
            f"PR: {pr['pr_id']}",
            f"Title: {pr['title']}",
            f"Status: {pr['status']}",
            f"Verdict: {pr.get('verdict', 'pending')}",
            f"Branch: {pr['branch']}",
            f"Files: {', '.join(pr['files_changed'])}",
            f"Review rounds: {pr['review_rounds']}/{pr['max_rounds']}",
            f"Created: {pr['created_at']}",
        ]
        if pr.get("blocked_reason"):
            lines.append(f"Block reason: {pr['blocked_reason']}")
        if pr.get("discussions"):
            lines.append(f"\nDiscussion ({len(pr['discussions'])} messages):")
            for d in pr["discussions"][-6:]:
                role = d["role"].upper()
                msg_preview = d["message"][:300]
                lines.append(f"  [{role} R{d['round']}] {msg_preview}")
        return "\n".join(lines)

    return [
        {
            "name": "list_prs",
            "description": (
                "List pull requests. Optionally filter by status "
                "(open, reviewing, approved, merged, blocked, rejected) "
                "or feature_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by PR status",
                    },
                    "feature_id": {
                        "type": "string",
                        "description": "Filter by feature ID",
                    },
                },
            },
            "execute": list_prs_exec,
        },
        {
            "name": "get_pr",
            "description": (
                "Get details of a specific pull request including "
                "diff, discussion history, and verdict."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_id": {
                        "type": "string",
                        "description": "The PR ID (e.g. pr-abc1234567)",
                    },
                },
                "required": ["pr_id"],
            },
            "execute": get_pr_exec,
        },
    ]
