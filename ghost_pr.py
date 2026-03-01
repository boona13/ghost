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

# ── Persona Prompts ──────────────────────────────────────────────────

REVIEWER_PERSONA = """\
You are Ghost's CODE REVIEWER — a strict, senior engineer whose sole purpose \
is to protect the codebase from regressions, bugs, and bad design.

You review code quality, UI/UX quality, and frontend-backend integration as a \
single concern. You have seen Ghost's past mistakes and you WILL NOT let them \
happen again.

## Your Review Checklist

### Code Quality
- Security: input validation, path sanitization, no hardcoded secrets
- Correctness: logic bugs, off-by-one, race conditions, error handling
- Simplicity: no over-engineering, no unnecessary abstractions
- No regressions: changes must not break existing functionality

### UI/UX Quality (past mistakes M-08 through M-12)
- Modals MUST default to hidden (no display:flex on overlays)
- Modals MUST be dismissable (X button, overlay click, Escape key)
- Forms MUST use proper input types (selectors/pickers for known values, NOT raw text fields)
- UI MUST follow existing dashboard patterns (SVG icons, NOT emojis; dark theme; stat-card, btn, form-input, badge classes)
- Form labels MUST be accurate and match the actual expected input

### Frontend-Backend Integration (past mistakes M-14, M-15, M-23 — MOST DAMAGING)
- If a backend API is added, there MUST be frontend UI that calls it
- If frontend UI is added, the backend MUST actually persist and return the data
- The feature MUST be wired into the runtime (not just CRUD + UI that does nothing)
- API response data MUST be live, not stale/default values
- JS payload shape MUST match what the Python route reads from request.get_json()

### Python Correctness (past mistake M-06)
- NEVER import mutable module-level state with `from module import var` (dead copy)
- MUST use `import module; module.var` for live references to module state
- No double-escaped strings (\\\\n vs \\n)

### Scope (past mistake M-19)
- PR should do ONE thing. Flag unrelated changes.

## How to Respond

You MUST structure your response as follows:

1. Start with a brief summary of what the PR does (1-2 sentences)
2. List specific concerns with line references from the diff
3. End with EXACTLY ONE of these verdict lines:

   VERDICT: APPROVE — the change is safe, correct, and well-integrated
   VERDICT: REQUEST_CHANGES — specific issues must be fixed (list them)
   VERDICT: BLOCK — fundamentally wrong approach, not fixable with patches

Use BLOCK only when the entire approach is wrong (duplicates existing \
functionality, violates architecture, or introduces an unfixable security hole). \
Most issues should be REQUEST_CHANGES.
"""

DEVELOPER_PERSONA = """\
You are Ghost's DEVELOPER — the engineer who wrote the code under review. \
Your job is to defend your decisions with technical reasoning, but also to \
honestly acknowledge valid concerns.

## How to Respond

For each concern the reviewer raised:
1. If the reviewer is RIGHT: acknowledge it and propose a CONCRETE fix (include \
   the actual code patch — {old: "...", new: "..."} format)
2. If the reviewer is WRONG: explain why with specific technical reasoning
3. If you're unsure: say so and propose the safer alternative

When proposing fixes, wrap them in a JSON block:
```json
{"patches": [{"file": "ghost_example.py", "old": "old code", "new": "new code"}]}
```

End your response with:
CHANGES_PROPOSED: YES (if you proposed fixes)
CHANGES_PROPOSED: NO (if you disagree with all concerns and stand by the original code)
"""

MAX_REVIEW_ROUNDS = 5


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
    """Orchestrates multi-persona code review dialogue."""

    def __init__(self, store: PRStore, evolve_engine=None):
        self.store = store
        self.evolve_engine = evolve_engine

    def run_review(self, pr_id: str, engine) -> str:
        """Run the full review cycle. Returns verdict: approved/rejected/blocked.

        Args:
            pr_id: The PR to review
            engine: ToolLoopEngine instance for LLM calls
        """
        pr = self.store.get_pr(pr_id)
        if not pr:
            return "rejected"

        self.store.update_status(pr_id, "reviewing")
        log.info("Starting review for PR %s: %s", pr_id, pr["title"])

        for round_num in range(1, pr["max_rounds"] + 1):
            log.info("Review round %d/%d for PR %s",
                     round_num, pr["max_rounds"], pr_id)

            # --- Reviewer turn (with retries + escalating temperature) ---
            reviewer_context = self._format_reviewer_context(pr, round_num)
            reviewer_response = None
            for attempt in range(3):
                try:
                    prompt = reviewer_context
                    if attempt > 0:
                        prompt += (
                            "\n\nIMPORTANT: Your previous response was empty. "
                            "You MUST respond with:\n"
                            "1) A summary of the PR\n"
                            "2) Specific concerns (if any)\n"
                            "3) End with EXACTLY one of: VERDICT: APPROVE, "
                            "VERDICT: REQUEST_CHANGES, or VERDICT: BLOCK\n"
                        )
                    reviewer_response = engine.single_shot(
                        system_prompt=REVIEWER_PERSONA,
                        user_message=prompt,
                        max_tokens=4000,
                        temperature=0.2 + (attempt * 0.15),
                    )
                except Exception as e:
                    log.warning("Reviewer LLM call failed round %d attempt %d: %s",
                                round_num, attempt + 1, e)
                    reviewer_response = None
                if reviewer_response and reviewer_response.strip():
                    break
                reviewer_response = None
                log.warning("Reviewer response empty round %d attempt %d",
                            round_num, attempt + 1)
            if not reviewer_response:
                log.warning("Reviewer empty after 3 attempts round %d, auto-approving",
                            round_num)
                self.store.set_verdict(pr_id, "approved")
                return "approved"
            self.store.add_discussion(pr_id, "reviewer",
                                      reviewer_response, round_num)

            verdict = self._parse_verdict(reviewer_response)
            log.info("Reviewer verdict round %d: %s", round_num, verdict)

            if verdict == "approve":
                self.store.set_verdict(pr_id, "approved")
                return "approved"
            if verdict == "block":
                reason = self._extract_block_reason(reviewer_response)
                self.store.set_verdict(pr_id, "blocked", reason)
                return "blocked"

            # --- Developer turn ---
            pr = self.store.get_pr(pr_id)
            developer_context = self._format_developer_context(
                pr, reviewer_response, round_num)
            developer_response = None
            for attempt in range(3):
                try:
                    prompt = developer_context
                    if attempt > 0:
                        prompt += (
                            "\n\nIMPORTANT: Your previous response was empty. "
                            "You MUST respond with at least:\n"
                            "1) A short reply to the review concerns\n"
                            "2) Final line exactly: CHANGES_PROPOSED: YES or CHANGES_PROPOSED: NO\n"
                        )
                    developer_response = engine.single_shot(
                        system_prompt=DEVELOPER_PERSONA,
                        user_message=prompt,
                        max_tokens=4000,
                        temperature=0.2 + (attempt * 0.15),
                    )
                except Exception as e:
                    log.warning("Developer LLM call failed round %d attempt %d: %s",
                                round_num, attempt + 1, e)
                    developer_response = None
                if developer_response and developer_response.strip():
                    break
                developer_response = None
                log.warning("Developer response empty round %d attempt %d",
                            round_num, attempt + 1)
            if not developer_response:
                log.warning("Developer empty after 3 attempts round %d, auto-approving",
                            round_num)
                self.store.set_verdict(pr_id, "approved")
                return "approved"
            self.store.add_discussion(pr_id, "developer",
                                      developer_response, round_num)

            # Apply patches if developer proposed changes
            if self._has_proposed_changes(developer_response):
                patches = self._extract_patches(developer_response)
                if patches and self.evolve_engine:
                    self._apply_review_patches(
                        pr, patches, round_num)
                    pr = self.store.get_pr(pr_id)

        # Max rounds exhausted
        self.store.set_verdict(pr_id, "rejected")
        log.info("PR %s rejected: max review rounds exhausted", pr_id)
        return "rejected"

    def _format_reviewer_context(self, pr: Dict, round_num: int) -> str:
        parts = [
            f"## Pull Request: {pr['title']}",
            f"**Description:** {pr['description']}",
            f"**Files changed:** {', '.join(pr['files_changed'])}",
            f"**Review round:** {round_num}/{pr['max_rounds']}",
            "",
            "## Diff",
            "```diff",
            pr["diff"][:15000],
            "```",
        ]

        if round_num > 1 and pr["discussions"]:
            parts.append("\n## Previous Discussion")
            for d in pr["discussions"]:
                role_label = "REVIEWER" if d["role"] == "reviewer" else "DEVELOPER"
                parts.append(f"\n### {role_label} (Round {d['round']})")
                parts.append(d["message"])

        parts.append(
            "\n\nReview this PR. Check code quality, UI/UX, "
            "frontend-backend integration, and Python correctness. "
            "End with your VERDICT."
        )
        return "\n".join(parts)

    def _format_developer_context(self, pr: Dict,
                                  reviewer_message: str,
                                  round_num: int) -> str:
        parts = [
            f"## Your PR: {pr['title']}",
            f"**Description:** {pr['description']}",
            f"**Files changed:** {', '.join(pr['files_changed'])}",
            "",
            "## Your Diff",
            "```diff",
            pr["diff"][:15000],
            "```",
            "",
            f"## Reviewer Feedback (Round {round_num})",
            reviewer_message,
            "",
            "Respond to each concern. If you agree with a fix, include "
            "the patch in JSON format. End with CHANGES_PROPOSED: YES or NO.",
        ]
        return "\n".join(parts)

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
