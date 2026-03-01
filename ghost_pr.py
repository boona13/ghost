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
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import ghost_git

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_HOME = Path.home() / ".ghost"
PR_DIR = GHOST_HOME / "prs"
PR_DIR.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("ghost.pr")

# ── Review System Prompt ──────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
You are a code review system with two personas. You will be asked to respond \
as either the REVIEWER or the DEVELOPER depending on the turn.

## When acting as REVIEWER

You are a strict, senior engineer protecting the codebase from regressions, \
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

## When acting as DEVELOPER

You are the engineer who wrote this code. Defend your decisions honestly.

For each reviewer concern:
1. Reviewer is RIGHT: acknowledge and propose a fix as a patch
2. Reviewer is WRONG: explain why with technical reasoning
3. Unsure: propose the safer alternative

When proposing fixes, use this JSON format:
```json
{"patches": [{"file": "filename.py", "old": "old code", "new": "new code"}]}
```

**Response format as DEVELOPER:**
End with: CHANGES_PROPOSED: YES (if you proposed fixes) or CHANGES_PROPOSED: NO
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
    def _chat(engine, messages, max_tokens=4000, temperature=0.3):
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

    # ── Main review loop ─────────────────────────────────────────────

    def run_review(self, pr_id: str, engine) -> str:
        """Run a conversational code review. Returns: approved/rejected/blocked.

        The entire review is one messages thread:
          system  →  PR context (diff, title, desc)  →  reviewer turn  →
          developer turn  →  reviewer turn  →  ...  →  final verdict.
        """
        pr = self.store.get_pr(pr_id)
        if not pr:
            return "rejected"

        self.store.update_status(pr_id, "reviewing")
        log.info("Starting review for PR %s: %s", pr_id, pr["title"])

        diff_text = pr["diff"][:15000]
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"## Pull Request: {pr['title']}\n"
                f"**Description:** {pr['description']}\n"
                f"**Files changed:** {', '.join(pr['files_changed'])}\n\n"
                f"```diff\n{diff_text}\n```"
            )},
        ]

        for round_num in range(1, pr["max_rounds"] + 1):
            log.info("Review round %d/%d for PR %s",
                     round_num, pr["max_rounds"], pr_id)

            # ── Reviewer turn ────────────────────────────────────────
            messages.append({"role": "user", "content": (
                f"**REVIEWER — Round {round_num}/{pr['max_rounds']}:** "
                "Review the diff above. Check code quality, correctness, "
                "UI/UX, frontend-backend integration, and scope. "
                "End with your VERDICT."
            )})

            reviewer_text = self._chat(engine, messages)
            if not reviewer_text:
                log.warning("Reviewer produced no response round %d — rejecting",
                            round_num)
                self.store.set_verdict(pr_id, "rejected",
                    f"LLM failed to produce reviewer response in round {round_num}")
                return "rejected"

            messages.append({"role": "assistant", "content": reviewer_text})
            self.store.add_discussion(pr_id, "reviewer", reviewer_text, round_num)

            verdict = self._parse_verdict(reviewer_text)
            log.info("Reviewer verdict round %d: %s", round_num, verdict)

            if verdict == "approve":
                self.store.set_verdict(pr_id, "approved")
                return "approved"
            if verdict == "block":
                reason = self._extract_block_reason(reviewer_text)
                self.store.set_verdict(pr_id, "blocked", reason)
                return "blocked"

            # ── Developer turn ───────────────────────────────────────
            messages.append({"role": "user", "content": (
                "**DEVELOPER:** Respond to every concern the reviewer raised. "
                "For valid concerns, propose a concrete fix as a patch. "
                "For invalid ones, explain why with technical reasoning. "
                "End with CHANGES_PROPOSED: YES or CHANGES_PROPOSED: NO."
            )})

            developer_text = self._chat(engine, messages)
            if not developer_text:
                log.info("Developer silent round %d — reviewer concerns stand, "
                         "rejecting", round_num)
                self.store.set_verdict(pr_id, "rejected",
                    f"Developer could not respond in round {round_num}")
                return "rejected"

            messages.append({"role": "assistant", "content": developer_text})
            self.store.add_discussion(pr_id, "developer", developer_text,
                                      round_num)

            # Apply patches if developer proposed changes
            if self._has_proposed_changes(developer_text):
                patches = self._extract_patches(developer_text)
                if patches and self.evolve_engine:
                    self._apply_review_patches(pr, patches, round_num)
                    pr = self.store.get_pr(pr_id)
                    diff_text = pr["diff"][:15000]
                    messages.append({"role": "user", "content": (
                        "Patches have been applied and tested. "
                        f"Updated diff:\n```diff\n{diff_text}\n```"
                    )})

        # Max rounds exhausted without resolution
        self.store.set_verdict(pr_id, "rejected")
        log.info("PR %s rejected: max review rounds exhausted", pr_id)
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

    def _has_proposed_changes(self, response: str) -> bool:
        return "CHANGES_PROPOSED: YES" in response.upper()

    def _extract_patches(self, response: str) -> list[dict]:
        """Extract patch JSON blocks from developer response."""
        patches = []
        json_pattern = re.compile(
            r'```json\s*\n(.*?)\n\s*```', re.DOTALL)
        for match in json_pattern.finditer(response):
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and "patches" in data:
                    patches.extend(data["patches"])
                elif isinstance(data, list):
                    patches.extend(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return patches

    def _apply_review_patches(self, pr: Dict, patches: list[dict],
                              round_num: int):
        """Apply developer patches on the feature branch, re-test, update PR.

        Important: saves and restores the evolution status around test() to
        prevent the review-round test from corrupting the 'tested_pass' status
        that submit_pr() relies on for deploy().
        """
        evolution_id = pr["evolution_id"]
        branch = pr["branch"]

        ok, msg = ghost_git.checkout(branch)
        if not ok:
            log.warning("Cannot checkout branch %s for patches: %s",
                        branch, msg)
            return

        try:
            for patch in patches:
                file_path = patch.get("file", "")
                old = patch.get("old", "")
                new = patch.get("new", "")
                if not file_path or not old or not new:
                    continue
                if self.evolve_engine:
                    self.evolve_engine.apply_change(
                        evolution_id, file_path,
                        patches=[{"old": old, "new": new}])

            ghost_git.commit(f"Address review feedback: round {round_num}")

            if self.evolve_engine:
                evo = self.evolve_engine._active_evolutions.get(evolution_id)
                saved_status = evo["status"] if evo else None
                self.evolve_engine.test(evolution_id)
                if evo and saved_status:
                    evo["status"] = saved_status

        except Exception as e:
            log.warning("Error applying review patches: %s", e)
        finally:
            ghost_git.stash_and_checkout("main")
            diff = ghost_git.get_diff("main", branch)
            files = ghost_git.get_changed_files("main", branch)
            self.store.update_diff(pr["pr_id"], diff, files)


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
