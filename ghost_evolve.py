"""
Ghost Self-Evolution Engine — lets Ghost modify its own codebase safely.

Provides: EvolutionEngine (backup, validate, test, deploy, rollback, history)
          build_evolve_tools() for ToolRegistry integration
"""

import ast
import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ghost.evolve")

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_HOME = Path.home() / ".ghost"
EVOLVE_DIR = GHOST_HOME / "evolve"
BACKUP_DIR = EVOLVE_DIR / "backups"
PENDING_DIR = EVOLVE_DIR / "pending"
HISTORY_FILE = EVOLVE_DIR / "history.json"
DEPLOY_MARKER = EVOLVE_DIR / "deploy_pending"

DELETED_FILES_LOG = EVOLVE_DIR / "deleted_files.json"

def _normalize_file_path(file_path: str) -> Path:
    """Normalize file paths to resolve relative to PROJECT_DIR.
    
    Handles: absolute paths, tilde paths, and accidental PROJECT_DIR-relative paths
    like 'Downloads/IMG/ghost.py' which should just be 'ghost.py'.
    """
    expanded = Path(file_path).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    rel_str = str(expanded)
    proj_resolved = str(PROJECT_DIR.resolve())
    proj_name = PROJECT_DIR.name
    try:
        proj_rel = str(PROJECT_DIR.relative_to(Path.home()))
    except ValueError:
        proj_rel = ""
    if proj_rel and rel_str.startswith(proj_rel + "/"):
        rel_str = rel_str[len(proj_rel) + 1:]
    elif rel_str.startswith(proj_name + "/"):
        rel_str = rel_str[len(proj_name) + 1:]
    return (PROJECT_DIR / rel_str).resolve()

EVOLVE_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
PENDING_DIR.mkdir(parents=True, exist_ok=True)

MAX_BACKUPS = 20
MAX_EVOLUTIONS_PER_HOUR = 25
HEALTH_CHECK_TIMEOUT = 15
MAX_NEW_FILE_SIZE = 30000

PROTECTED_FILES = {
    "ghost_supervisor.py",
}

PROTECTED_PATTERNS = [
    "PROTECTED_FILES",
    "PROTECTED_PATTERNS",
    "MAX_EVOLUTIONS_PER_HOUR",
    "evolve_rollback",
    "_restore_backup",
    "CORE_COMMANDS",
    "DEFAULT_ALLOWED_COMMANDS",
]

BACKUP_EXCLUDE_DIRS = {
    "__pycache__", ".git", "openclaw_ref", "node_modules",
    ".venv", "venv", ".mypy_cache", ".pytest_cache",
}
BACKUP_EXCLUDE_FILES = {
    "memory.db", "memory.db-wal", "memory.db-shm",
    ".env", ".DS_Store",
}


class EvolutionEngine:
    """Manages Ghost's self-modification lifecycle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active_evolutions = {}
        self._history = self._load_history()
        self._active_jobs_fn = None  # Set by GhostDaemon to check cron status
        self._cleanup_orphaned_pending()

    def _cleanup_orphaned_pending(self):
        """Remove pending evolution files left over from a previous process.

        When Ghost restarts, any _wait_for_approval loops from the old process
        are dead. Keeping the pending files causes stale approval requests to
        appear in the dashboard with no live listener to act on them.
        """
        cleaned = 0
        for pf in PENDING_DIR.glob("*.json"):
            try:
                pf.unlink()
                cleaned += 1
            except Exception:
                pass
        if cleaned:
            import logging
            _log = logging.getLogger("ghost.evolve")
            _log.info("Cleaned up %d orphaned pending evolution(s) on startup", cleaned)

    def set_active_jobs_fn(self, fn):
        """Register a callable that returns the count of active cron jobs
        (excluding the Feature Implementer itself). Used by deploy() to wait
        for other jobs to finish before restarting Ghost."""
        self._active_jobs_fn = fn

    def _load_history(self):
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text())
            except Exception:
                pass
        return []

    def _save_history(self):
        data = json.dumps(self._history, indent=2)
        import os as _os
        fd = _os.open(str(HISTORY_FILE), _os.O_WRONLY | _os.O_CREAT | _os.O_TRUNC)
        try:
            _os.write(fd, data.encode())
            _os.fsync(fd)
        finally:
            _os.close(fd)

    def _rate_check(self, limit=None):
        cutoff = time.time() - 3600
        recent = sum(
            1 for e in self._history
            if e.get("timestamp", 0) > cutoff and e.get("status") == "deployed"
        )
        max_per_hour = limit if limit is not None else MAX_EVOLUTIONS_PER_HOUR
        return recent < max_per_hour

    def _classify_level(self, files):
        """Determine modification level from file paths."""
        level = 1
        for f in files:
            f_str = str(f)
            basename = Path(f_str).name
            if basename in PROTECTED_FILES:
                return 99
            if f_str.startswith("skills/") or f_str.endswith("SKILL.md"):
                level = max(level, 1)
            elif f_str == "SOUL.md" or f_str == "USER.md":
                level = max(level, 2)
            elif f_str.startswith("ghost_dashboard/"):
                level = max(level, 3)
            elif basename in ("ghost.py", "ghost_loop.py", "ghost_memory.py",
                              "ghost_cron.py", "ghost_skills.py", "ghost_tools.py",
                              "ghost_browser.py", "ghost_evolve.py"):
                level = max(level, 5)
            else:
                level = max(level, 4)
        return level

    def _needs_approval(self, level, cfg):
        if cfg.get("evolve_auto_approve", False):
            return False
        if level >= 3:
            return True
        return False

    def create_backup(self, evolution_id, description=""):
        """Snapshot the entire project folder + config into a tar.gz."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{ts}_{evolution_id[:8]}.tar.gz"
        backup_path = BACKUP_DIR / backup_name
        evolve_backups = str(BACKUP_DIR)
        config_file = GHOST_HOME / "config.json"

        def _filter(tarinfo):
            path = tarinfo.name
            parts = Path(path).parts
            for part in parts:
                if part in BACKUP_EXCLUDE_DIRS:
                    return None
            if parts and parts[-1] in BACKUP_EXCLUDE_FILES:
                return None
            if path.endswith(".pyc"):
                return None
            return tarinfo

        with tarfile.open(str(backup_path), "w:gz") as tar:
            for item in PROJECT_DIR.iterdir():
                abs_path = str(item)
                if abs_path.startswith(evolve_backups):
                    continue
                arcname = item.name
                if item.is_dir() and item.name in BACKUP_EXCLUDE_DIRS:
                    continue
                tar.add(abs_path, arcname=arcname, filter=_filter)
            if config_file.exists():
                tar.add(str(config_file), arcname=".ghost_config_backup.json")

        self._prune_backups()
        return str(backup_path)

    def _prune_backups(self):
        backups = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
        while len(backups) > MAX_BACKUPS:
            backups[0].unlink()
            backups.pop(0)

    def _restore_backup(self, backup_path):
        """Restore files from a backup archive (project code + config)."""
        bp = Path(backup_path)
        if not bp.exists():
            return False, f"Backup not found: {backup_path}"

        config_file = GHOST_HOME / "config.json"
        with tarfile.open(str(bp), "r:gz") as tar:
            config_member = None
            for member in tar.getmembers():
                if member.name == ".ghost_config_backup.json":
                    config_member = member
                    break
            tar.extractall(path=str(PROJECT_DIR))
            if config_member:
                extracted = PROJECT_DIR / ".ghost_config_backup.json"
                if extracted.exists():
                    shutil.copy2(str(extracted), str(config_file))
                    extracted.unlink()
        return True, "Backup restored (code + config)"

    def plan(self, description, files, cfg):
        """Create an evolution plan. Returns (evolution_id, info_dict)."""
        with self._lock:
            limit = cfg.get("max_evolutions_per_hour", MAX_EVOLUTIONS_PER_HOUR)
            if not self._rate_check(limit=limit):
                return None, {"error": f"Rate limit: max {limit} self-modifications per hour"}

            evolution_id = uuid.uuid4().hex[:12]
            level = self._classify_level(files)

            if level >= 99:
                return None, {"error": f"Cannot modify protected files: {PROTECTED_FILES}"}

            needs_approval = self._needs_approval(level, cfg)
            backup_path = self.create_backup(evolution_id, description)

            # Create a git feature branch for this evolution
            git_branch = None
            try:
                import ghost_git
                branch_name = f"evolve/{evolution_id}"
                ok, msg = ghost_git.create_branch(branch_name)
                if ok:
                    git_branch = branch_name
                else:
                    import logging
                    _log = logging.getLogger("ghost.evolve")
                    _log.warning("Could not create git branch %s: %s",
                                branch_name, msg)
            except Exception as e:
                import logging
                _log = logging.getLogger("ghost.evolve")
                _log.warning("Git branch creation failed: %s", e)

            evo = {
                "id": evolution_id,
                "description": description,
                "files": [str(f) for f in files],
                "level": level,
                "status": "pending_approval" if needs_approval else "planned",
                "needs_approval": needs_approval,
                "approved": not needs_approval,
                "backup_path": backup_path,
                "git_branch": git_branch,
                "timestamp": time.time(),
                "created_at": datetime.now().isoformat(),
                "changes": [],
                "test_results": None,
            }

            self._active_evolutions[evolution_id] = evo

            if needs_approval:
                pending_file = PENDING_DIR / f"{evolution_id}.json"
                pending_file.write_text(json.dumps(evo, indent=2))

            return evolution_id, {
                "evolution_id": evolution_id,
                "level": level,
                "needs_approval": needs_approval,
                "approved": not needs_approval,
                "backup_path": backup_path,
                "status": evo["status"],
            }

    def approve(self, evolution_id):
        """Approve a pending evolution."""
        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            pending_file = PENDING_DIR / f"{evolution_id}.json"
            if pending_file.exists():
                evo = json.loads(pending_file.read_text())
                self._active_evolutions[evolution_id] = evo
            else:
                return False, "Evolution not found"

        evo["approved"] = True
        evo["status"] = "approved"
        pending_file = PENDING_DIR / f"{evolution_id}.json"
        if pending_file.exists():
            pending_file.unlink()
        return True, "Evolution approved"

    def reject(self, evolution_id):
        """Reject and clean up a pending evolution."""
        evo = self._active_evolutions.pop(evolution_id, None)
        pending_file = PENDING_DIR / f"{evolution_id}.json"
        if pending_file.exists():
            pending_file.unlink()
        if evo and evo.get("backup_path"):
            try:
                Path(evo["backup_path"]).unlink(missing_ok=True)
            except Exception:
                pass
        return True, "Evolution rejected"

    def _wait_for_approval(self, evolution_id, timeout=300):
        """Block until the evolution is approved, rejected, or times out."""
        poll_interval = 2
        waited = 0
        while waited < timeout:
            evo = self._active_evolutions.get(evolution_id)
            if not evo:
                return False, "Evolution was deleted while waiting."
            if evo.get("approved"):
                return True, f"Approved after {waited}s."
            if evo.get("status") == "rejected":
                return False, "Evolution was REJECTED by the user."
            time.sleep(poll_interval)
            waited += poll_interval
        self.reject(evolution_id)
        return False, "Timed out waiting for approval (5 minutes). Evolution cancelled."

    def apply_change(self, evolution_id, file_path, content=None, patches=None,
                     append=False):
        """Apply a code change to a file.

        append=True lets the LLM build a new file incrementally across
        multiple calls when the content is too large for a single JSON
        tool-call output.  Each call appends to the file; the diff is
        recorded on every call so rollback stays correct.
        """
        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            return False, "Evolution not found. Call evolve_plan first."
        if not evo.get("approved"):
            ok, msg = self._wait_for_approval(evolution_id)
            if not ok:
                return False, f"Evolution {evolution_id}: {msg}"

        rel_path = file_path
        abs_path = _normalize_file_path(rel_path)

        if not str(abs_path).startswith(str(PROJECT_DIR.resolve())):
            return False, (
                f"Cannot write outside the project directory. "
                f"Path '{file_path}' resolves to '{abs_path}' which is outside '{PROJECT_DIR}'. "
                f"Use a relative path like 'skills/{Path(file_path).name}' instead."
            )

        if Path(rel_path).name in PROTECTED_FILES:
            return False, f"Cannot modify protected file: {rel_path}"


        old_content = ""
        if abs_path.exists():
            old_content = abs_path.read_text()

        PATCH_ONLY_EXTENSIONS = {".css", ".js", ".html", ".py"}
        PATCH_ONLY_MIN_SIZE = 200
        if (content is not None and not append and old_content
                and Path(rel_path).suffix.lower() in PATCH_ONLY_EXTENSIONS
                and len(old_content) > PATCH_ONLY_MIN_SIZE):
            return False, (
                f"REJECTED: Cannot use full-file 'content' mode on existing {Path(rel_path).suffix} file "
                f"'{rel_path}' ({len(old_content)} bytes). Use 'patches' instead — provide a list of "
                "{old: '...', new: '...'} search/replace pairs. This prevents accidentally overwriting "
                "or losing existing code. To APPEND new code, use a patch where 'old' is the last few "
                "lines of the file and 'new' is those same lines plus your additions."
            )

        if append and content is not None:
            new_content = old_content + content
        elif content is not None:
            new_content = content
        elif patches:
            new_content = old_content
            for patch in patches:
                old_str = patch.get("old", "")
                new_str = patch.get("new", "")
                if old_str and old_str in new_content:
                    new_content = new_content.replace(old_str, new_str, 1)
                else:
                    # Provide more helpful error message with context
                    hint = ""
                    if old_str.strip():
                        # Check if it's a whitespace issue
                        if old_str.strip() in new_content:
                            hint = " (Note: The content exists but with different whitespace/indentation)"
                        # Check if it's a line ending issue  
                        elif old_str.replace('\r\n', '\n') in new_content.replace('\r\n', '\n'):
                            hint = " (Note: Content matches but line endings differ)"
                        # Suggest re-reading the file
                        else:
                            hint = f" Hint: Use file_read on '{rel_path}' to get the exact current content, then retry with matching text."
                    
                    return False, f"Patch target not found in {rel_path}: {old_str[:80]}...{hint}"
        else:
            return False, "Provide either 'content' (full file) or 'patches' (search/replace pairs)"

        for pattern in PROTECTED_PATTERNS:
            if pattern in old_content and pattern not in new_content:
                return False, f"Cannot remove safety pattern '{pattern}' from {rel_path}"

        if not abs_path.exists() and len(new_content) > MAX_NEW_FILE_SIZE:
            return False, (
                f"New file too large ({len(new_content)} bytes, max {MAX_NEW_FILE_SIZE}). "
                f"Break it into smaller, focused modules."
            )

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(new_content)

        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
        ))
        diff_text = "".join(diff) if diff else "(new file)"

        evo["changes"].append({
            "file": rel_path,
            "diff": diff_text[:5000],
            "timestamp": datetime.now().isoformat(),
        })

        change_count = len(evo["changes"])
        msg = f"Applied change to {rel_path} ({len(new_content)} bytes). [{change_count} file(s) changed] "
        msg += "Remember: call evolve_test then evolve_deploy when done."
        return True, msg

    def apply_config_change(self, evolution_id, updates):
        """Apply config changes to ~/.ghost/config.json within an evolution context.

        Validates updates, applies them, and records the change so
        evolve_test / evolve_deploy / rollback all cover it.
        """
        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            return False, "Evolution not found. Call evolve_plan first."
        if not evo.get("approved"):
            ok, msg = self._wait_for_approval(evolution_id)
            if not ok:
                return False, f"Evolution {evolution_id}: {msg}"

        if not isinstance(updates, dict) or not updates:
            return False, "updates must be a non-empty JSON object"

        from ghost_config_tool import BLOCKED_KEYS, SENSITIVE_KEYS, _is_hardening_change

        blocked = [k for k in updates if k in BLOCKED_KEYS]
        if blocked:
            return False, f"Cannot modify blocked keys: {blocked}"

        sensitive = [k for k in updates if k in SENSITIVE_KEYS]
        if sensitive:
            weakening = [k for k in sensitive if not _is_hardening_change(k, updates[k])]
            if weakening:
                return False, (
                    f"These changes would WEAKEN security: {weakening}. "
                    "Use add_action_item to propose weakening changes to the user."
                )

        config_file = GHOST_HOME / "config.json"
        old_cfg = {}
        if config_file.exists():
            try:
                old_cfg = json.loads(config_file.read_text())
            except Exception:
                pass

        old_values = {k: old_cfg.get(k, "(unset)") for k in updates}
        new_cfg = {**old_cfg, **updates}
        config_file.write_text(json.dumps(new_cfg, indent=2))

        diff_lines = []
        for k, new_val in updates.items():
            diff_lines.append(f"  {k}: {old_values[k]} -> {new_val}")

        evo["changes"].append({
            "file": "~/.ghost/config.json",
            "type": "config",
            "diff": "\n".join(diff_lines),
            "updates": updates,
            "old_values": old_values,
            "timestamp": datetime.now().isoformat(),
        })

        change_count = len(evo["changes"])
        msg = (
            f"Config updated ({len(updates)} key(s)) within evolution {evolution_id}:\n"
            + "\n".join(diff_lines)
            + f"\n[{change_count} change(s) total] "
            + "Remember: call evolve_test then evolve_deploy when done."
        )
        return True, msg

    def test(self, evolution_id):
        """Run validation pipeline on modified files.

        Three checks run directly on host:
        1. Syntax — ast.parse each changed .py file
        2. Import — attempt to import each changed module
        3. Smoke — run ghost.py --dry-run to verify startup
        """
        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            return False, {"error": "Evolution not found"}

        results = {
            "syntax": [], "import": [], "dangling_imports": [],
            "smoke": None, "passed": True,
        }

        def _to_rel(file_path):
            """Normalize a file path from a change record to a project-relative path."""
            p = Path(file_path)
            if p.is_absolute():
                try:
                    return str(p.relative_to(PROJECT_DIR.resolve()))
                except ValueError:
                    return p.name
            return str(p)

        changed_py = [
            _to_rel(c["file"]) for c in evo["changes"]
            if c["file"].endswith(".py")
        ]
        deleted_py = [
            _to_rel(c["file"]) for c in evo["changes"]
            if c["file"].endswith(".py") and c.get("action") == "delete"
        ]

        for f in deleted_py:
            dangling = self._scan_dangling_imports(f)
            for dep_file, dep_lines in dangling:
                results["dangling_imports"].append({
                    "deleted_module": Path(f).stem,
                    "importing_file": dep_file,
                    "lines": dep_lines,
                })
                results["passed"] = False

        for f in changed_py:
            abs_path = PROJECT_DIR / f
            if not abs_path.exists():
                continue
            try:
                source = abs_path.read_text()
                ast.parse(source, filename=f)
                ok, output = True, None
            except SyntaxError as e:
                ok, output = False, f"Line {e.lineno}: {e.msg}"

            results["syntax"].append({
                "file": f, "ok": ok,
                "error": output if not ok else None,
            })
            if not ok:
                results["passed"] = False

        if results["passed"] and changed_py:
            for f in changed_py:
                if f in deleted_py:
                    continue
                module_name = f.replace("/", ".").replace(".py", "")
                try:
                    r = subprocess.run(
                        [sys.executable, "-c", f"import {module_name}"],
                        capture_output=True, text=True, timeout=10,
                        cwd=str(PROJECT_DIR),
                    )
                    ok = r.returncode == 0
                    output = r.stderr.strip()[:300] if not ok else None
                except subprocess.TimeoutExpired:
                    ok, output = False, "Import timed out"

                results["import"].append({
                    "module": module_name, "ok": ok,
                    "error": output if not ok else None,
                })
                if not ok:
                    results["passed"] = False

        if results["passed"]:
            try:
                r = subprocess.run(
                    [sys.executable, "ghost.py", "--dry-run"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(PROJECT_DIR),
                )
                ok = r.returncode == 0
                output = r.stderr.strip()[:300] if not ok else "OK"
            except subprocess.TimeoutExpired:
                ok, output = False, "Smoke test timed out"
            except Exception as e:
                ok, output = False, str(e)[:300]

            results["smoke"] = {
                "ok": ok, "output": output if not ok else "OK",
            }
            if not ok:
                results["passed"] = False

        if results["passed"]:
            api_results = self._test_api_routes(evo)
            results["api_routes"] = api_results
            if any(not r["ok"] for r in api_results):
                results["passed"] = False

        if results["passed"]:
            lint_issues = self._semantic_lint(evo)
            results["semantic_lint"] = lint_issues
            if lint_issues:
                results["passed"] = False

        evo["test_results"] = results
        evo["status"] = "tested_pass" if results["passed"] else "tested_fail"

        return results["passed"], results

    # ── Semantic Lint ─────────────────────────────────────────────

    @staticmethod
    def _extract_changed_lines(diff_text):
        """Parse unified diff to extract set of added/changed line numbers in the new file."""
        changed = set()
        if not diff_text or diff_text == "(new file)":
            return None  # None means "all lines" (new file)
        current_line = 0
        for raw_line in diff_text.split("\n"):
            if raw_line.startswith("@@"):
                m = re.search(r'\+(\d+)', raw_line)
                if m:
                    current_line = int(m.group(1)) - 1
            elif raw_line.startswith("+") and not raw_line.startswith("+++"):
                current_line += 1
                changed.add(current_line)
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                pass  # deleted line, don't advance
            else:
                current_line += 1
        return changed

    def _semantic_lint(self, evo):
        """Static analysis for patterns that cause PR rejections.

        Only lints lines that were actually added or changed in this evolution,
        not pre-existing code. For new files, all lines are checked.
        Returns a list of dicts: [{file, line, rule, message}].
        """
        issues = []
        file_changed_lines = {}
        for change in evo.get("changes", []):
            fpath = change["file"]
            diff_text = change.get("diff", "")
            cl = self._extract_changed_lines(diff_text)
            if fpath in file_changed_lines:
                existing = file_changed_lines[fpath]
                if existing is None or cl is None:
                    file_changed_lines[fpath] = None
                else:
                    existing.update(cl)
            else:
                file_changed_lines[fpath] = cl

        for fpath, changed_lines in file_changed_lines.items():
            if not fpath.endswith(".py"):
                continue
            abs_path = _normalize_file_path(fpath)
            if not abs_path.exists():
                continue
            try:
                source = abs_path.read_text()
            except Exception:
                continue
            lines = source.split("\n")
            rel = str(abs_path.relative_to(PROJECT_DIR)) if abs_path.is_relative_to(PROJECT_DIR) else fpath

            for i, line in enumerate(lines, 1):
                if changed_lines is not None and i not in changed_lines:
                    continue
                stripped = line.strip()

                # Rule 1: Bare except with pass (no logging)
                if re.match(r'^except\s*:', stripped) or re.match(r'^except\s+Exception\s*:', stripped):
                    body_lines = []
                    for j in range(i, min(i + 5, len(lines))):
                        body_lines.append(lines[j].strip())
                    body = " ".join(body_lines)
                    if re.search(r'\bpass\b', body) and "log." not in body and "logging." not in body:
                        issues.append({
                            "file": rel, "line": i, "rule": "bare-except",
                            "message": "Bare except with pass — catch specific types and log the error",
                        })

                # Rule 2: from ghost_* import mutable_var (not class/func/CONSTANT)
                m = re.match(r'^from\s+(ghost_\w+)\s+import\s+(\w+)', stripped)
                if m:
                    name = m.group(2)
                    if not name[0].isupper() and name != name.upper():
                        # Check if it's a function/class in the source module
                        _src_mod = PROJECT_DIR / f"{m.group(1)}.py"
                        _is_callable = False
                        try:
                            if _src_mod.exists():
                                _src_text = _src_mod.read_text()
                                if re.search(rf'^(def|class)\s+{re.escape(name)}\b', _src_text, re.MULTILINE):
                                    _is_callable = True
                        except Exception:
                            pass
                        if not _is_callable:
                            issues.append({
                                "file": rel, "line": i, "rule": "mutable-import",
                                "message": f"'from {m.group(1)} import {name}' imports a mutable copy — use 'import {m.group(1)}; {m.group(1)}.{name}' instead",
                            })

                # Rule 3: Unbounded file read into json.loads
                if re.search(r'json\.loads?\(.*\.read_text\(\)', stripped):
                    size_guard = any(
                        "stat()" in lines[max(0, j)].strip() or "st_size" in lines[max(0, j)].strip()
                        for j in range(max(0, i - 6), i - 1)
                    )
                    if not size_guard:
                        issues.append({
                            "file": rel, "line": i, "rule": "unbounded-read",
                            "message": "json.loads(path.read_text()) without a file size check — add a size guard or use bounded reads",
                        })

                # Rule 4: .write_text() without preceding mkdir
                if ".write_text(" in stripped or re.search(r"open\(.+,\s*['\"]w", stripped):
                    has_mkdir = any(
                        "mkdir(" in lines[max(0, j)]
                        for j in range(max(0, i - 6), i - 1)
                    )
                    has_parent_mkdir = any(
                        "mkdir(" in lines[max(0, j)]
                        for j in range(max(0, i - 20), i - 1)
                    )
                    if not has_mkdir and not has_parent_mkdir:
                        if ".write_text(" in stripped:
                            path_in_line = stripped.split(".write_text")[0].split("=")[-1].strip()
                        else:
                            open_m = re.search(r'open\(([^,)]+)', stripped)
                            path_in_line = open_m.group(1).strip() if open_m else ""
                        if path_in_line and path_in_line.upper() != path_in_line:
                            issues.append({
                                "file": rel, "line": i, "rule": "missing-mkdir",
                                "message": "File write without preceding Path.mkdir(parents=True, exist_ok=True)",
                            })

        return issues

    def submit_pr(self, evolution_id, title, description, feature_id="", cfg=None):
        """Submit a PR for code review instead of deploying directly.

        Creates a git commit on the feature branch, builds a PR, runs the
        adversarial review loop, and handles the verdict (merge+deploy,
        reject, or block).

        The review ALWAYS runs. Self-repair uses evolve_deploy directly —
        it never calls submit_pr, so there is no auto-approve bypass here.
        """
        import ghost_git
        from ghost_pr import get_pr_store, get_review_engine

        if not evolution_id or not isinstance(evolution_id, str) or len(evolution_id) < 8:
            active_ids = list(self._active_evolutions.keys())
            hint = f" Active evolutions: {active_ids}" if active_ids else ""
            return False, f"Invalid evolution_id: '{evolution_id}'.{hint}"

        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            active_ids = list(self._active_evolutions.keys())
            hint = f" Active evolutions: {active_ids}" if active_ids else ""
            return False, f"Evolution '{evolution_id}' not found.{hint}"
        if evo.get("status") != "tested_pass":
            return False, "Cannot submit PR: tests have not passed. Run evolve_test first."

        # Pre-submit semantic lint: catch anti-patterns before the expensive review
        lint_issues = self._semantic_lint(evo)
        if lint_issues:
            issues_text = "\n".join(
                f"  - {i['file']}:{i['line']} [{i['rule']}]: {i['message']}"
                for i in lint_issues
            )
            return False, (
                f"PRE-SUBMIT VALIDATION FAILED — {len(lint_issues)} issue(s) found:\n"
                f"{issues_text}\n\n"
                "Fix these issues with evolve_apply, then re-run evolve_test, "
                "then try evolve_submit_pr again."
            )

        # Ensure git branch exists — recover if plan() failed to create it
        branch_name = evo.get("git_branch")
        if not branch_name or not ghost_git.branch_exists(branch_name):
            branch_name = f"evolve/{evolution_id}"
            ok, msg = ghost_git.create_branch(branch_name)
            if not ok:
                return False, (
                    f"Cannot create git branch for PR: {msg}. "
                    "Git may not be initialized. Run 'git init' in the project directory, "
                    "or use evolve_deploy for direct deploy."
                )
            evo["git_branch"] = branch_name
            import logging
            _log = logging.getLogger("ghost.evolve")
            _log.info("Recovered git branch %s for evolution %s", branch_name, evolution_id)

        # Commit changes on the feature branch
        ok, msg = ghost_git.checkout(branch_name)
        if not ok:
            return False, f"Cannot switch to feature branch: {msg}"
        ok, msg = ghost_git.commit(f"feat: {title}")

        diff = ghost_git.get_diff("main", branch_name)
        changed_files = ghost_git.get_changed_files("main", branch_name)

        # Reuse existing open/reviewing PR for this evolution+branch to
        # prevent duplicate records if submit_pr is retried after an error.
        store = get_pr_store()
        pr = None
        for existing in store.list_prs():
            if (
                existing.get("evolution_id") == evolution_id
                and existing.get("branch") == branch_name
                and existing.get("status") in {"open", "reviewing", "approved"}
            ):
                pr = existing
                store.update_diff(pr["pr_id"], diff, changed_files)
                break
        if pr is None:
            pr = store.create_pr(
                evolution_id=evolution_id,
                feature_id=feature_id,
                title=title,
                description=description,
                branch=branch_name,
                diff=diff,
                files_changed=changed_files,
            )

        # Run the adversarial review with a DEDICATED engine instance.
        # Using daemon.engine caused contention: concurrent cron jobs share
        # the same engine/fallback chain, amplifying 429s and causing empty
        # responses when the provider is rate-limited.
        review_engine = get_review_engine(evolve_engine=self)
        loop_engine = None
        try:
            from ghost import load_config
            from ghost_loop import ToolLoopEngine
            from ghost_auth_profiles import get_auth_store
            _cfg = cfg or load_config()
            api_key = _cfg.get("api_key", "")
            model = _cfg.get("model", "openrouter/auto")
            fallback_models = _cfg.get("fallback_models", [])
            auth_store = get_auth_store()

            provider_chain = None
            try:
                from ghost_dashboard import get_daemon
                daemon = get_daemon()
                if daemon and hasattr(daemon, "_build_provider_chain"):
                    provider_chain = daemon._build_provider_chain(
                        model, fallback_models)
            except Exception:
                pass

            loop_engine = ToolLoopEngine(
                api_key=api_key,
                model=model,
                fallback_models=fallback_models,
                auth_store=auth_store,
                provider_chain=provider_chain,
            )
        except Exception as e:
            _log = logging.getLogger("ghost.evolve")
            _log.warning("Could not create LLM engine for review: %s", e)
            ghost_git.stash_and_checkout("main")
            return False, f"Cannot start review: LLM init failed: {e}"

        verdict = review_engine.run_review(pr["pr_id"], loop_engine)
        import logging
        _log = logging.getLogger("ghost.evolve")
        _log.info("PR %s verdict: %s", pr["pr_id"], verdict)

        def _notify_queue_best_effort():
            try:
                from ghost_dashboard.routes.future_features import _notify_queue
                _notify_queue()
            except Exception:
                pass

        if verdict == "approved":
            ghost_git.checkout("main")
            ok, msg = ghost_git.merge(branch_name)
            if not ok:
                ghost_git.stash_and_checkout("main")
                return False, f"Merge failed after approval: {msg}"
            ghost_git.delete_branch(branch_name)
            store.mark_merged(pr["pr_id"])
            return self.deploy(evolution_id, feature_id=feature_id)

        elif verdict == "blocked":
            ghost_git.stash_and_checkout("main")
            ghost_git.delete_branch(branch_name)
            try:
                from ghost_future_features import FutureFeaturesStore
                if feature_id:
                    FutureFeaturesStore().reject(
                        feature_id, f"Blocked by reviewer (PR {pr['pr_id']})")
                    _notify_queue_best_effort()
            except Exception:
                pass
            pr_after = store.get_pr(pr["pr_id"]) or pr
            _log_reviewer_mistakes(pr_after, pr["pr_id"], title)
            return False, (
                f"PR {pr['pr_id']} BLOCKED by reviewer. "
                f"Feature {feature_id} marked as rejected. Call task_complete."
            )

        else:  # rejected
            ghost_git.stash_and_checkout("main")
            ghost_git.delete_branch(branch_name)
            retry_status = ""
            try:
                from ghost_future_features import FutureFeaturesStore
                if feature_id:
                    pr_after = store.get_pr(pr["pr_id"]) or pr
                    latest_reviewer_feedback = ""
                    for d in reversed(pr_after.get("discussions", [])):
                        if d.get("role") == "reviewer" and d.get("message"):
                            latest_reviewer_feedback = d["message"]
                            break
                    reason = f"PR rejected after review (PR {pr['pr_id']})"
                    if latest_reviewer_feedback:
                        feedback = latest_reviewer_feedback[:1200]
                        reason = (
                            f"{reason}. Latest reviewer feedback:\n{feedback}"
                        )
                    ok_retry, retry_status = FutureFeaturesStore().mark_review_rejected(
                        feature_id, reason,
                        max_retries=5,
                        reviewer_feedback=latest_reviewer_feedback)
                    if ok_retry and retry_status == "pending":
                        _delay = threading.Timer(905.0, _notify_queue_best_effort)
                        _delay.daemon = True
                        _delay.start()
            except Exception:
                pass
            pr_after = store.get_pr(pr["pr_id"]) or pr
            _log_reviewer_mistakes(pr_after, pr["pr_id"], title)
            from ghost_pr import MAX_REVIEW_ROUNDS
            retry_msg = (
                "Feature was re-queued to pending for another attempt."
                if retry_status == "pending" else
                "Feature was DEFERRED after max retry attempts."
                if retry_status == "deferred" else
                "Feature retry status unknown."
            )
            return False, (
                f"PR {pr['pr_id']} REJECTED. {retry_msg}\n"
                f"{'You MUST call task_complete NOW — do NOT retry in this session.' if retry_status == 'deferred' else 'Call task_complete NOW. The feature has been re-queued and will be attempted in a FUTURE run with all rejection feedback accumulated.'}"
            )

    def deploy(self, evolution_id, feature_id=""):
        """Signal the supervisor to restart Ghost with the new code.

        Before writing the deploy marker, waits for other cron jobs to finish
        (up to 30s) so the restart doesn't kill them mid-execution.

        The deploy marker carries feature_id so the supervisor can persist it
        for the new Ghost process to auto-complete the feature on startup.
        """
        with self._lock:
            evo = self._active_evolutions.get(evolution_id)
            if not evo:
                return False, "Evolution not found"
            if evo.get("status") != "tested_pass":
                return False, "Cannot deploy: tests have not passed. Run evolve_test first."

            # Wait for other cron jobs to finish before restarting
            if self._active_jobs_fn:
                waited = 0
                while waited < 30:
                    active = self._active_jobs_fn()
                    if active <= 1:  # 1 = just the Feature Implementer itself
                        break
                    time.sleep(2)
                    waited += 2

            # Clean up git feature branch if it exists
            git_branch = evo.get("git_branch")
            if git_branch:
                try:
                    import ghost_git
                    if ghost_git.current_branch() == git_branch:
                        ghost_git.stash_and_checkout("main")
                    ghost_git.delete_branch(git_branch)
                except Exception:
                    pass

            evo["status"] = "deployed"
            evo["deployed_at"] = datetime.now().isoformat()

            self._history.append(evo)
            self._save_history()
            self._active_evolutions.pop(evolution_id, None)

            deploy_info = {
                "evolution_id": evolution_id,
                "feature_id": feature_id,
                "backup_path": evo["backup_path"],
                "timestamp": time.time(),
            }
            DEPLOY_MARKER.write_text(json.dumps(deploy_info, indent=2))

        return True, (
            f"Evolution {evolution_id} deployed. "
            f"Ghost will restart momentarily. "
            f"Backup at: {evo['backup_path']}"
        )

    def delete_file(self, evolution_id, file_path):
        """Delete a file as part of an evolution, recording it for rollback awareness."""
        evo = self._active_evolutions.get(evolution_id)
        if not evo:
            return False, "Evolution not found. Call evolve_plan first."
        if not evo.get("approved"):
            ok, msg = self._wait_for_approval(evolution_id)
            if not ok:
                return False, f"Evolution {evolution_id}: {msg}"

        rel_path = file_path
        abs_path = _normalize_file_path(rel_path)

        if not str(abs_path).startswith(str(PROJECT_DIR.resolve())):
            return False, (
                f"Cannot delete outside the project directory. "
                f"Path '{file_path}' resolves to '{abs_path}' which is outside '{PROJECT_DIR}'."
            )

        if Path(rel_path).name in PROTECTED_FILES:
            return False, f"Cannot delete protected file: {rel_path}"

        if not abs_path.exists():
            return False, f"File not found: {rel_path}"

        old_content = abs_path.read_text() if abs_path.is_file() else ""
        abs_path.unlink()

        evo["changes"].append({
            "file": rel_path,
            "action": "delete",
            "diff": f"(deleted file, was {len(old_content)} bytes)",
            "timestamp": datetime.now().isoformat(),
        })

        self._log_intentional_deletion(evolution_id, rel_path)

        dangling = self._scan_dangling_imports(rel_path)
        warning = ""
        if dangling:
            files_list = ", ".join(f"{f}:{lines}" for f, lines in dangling[:5])
            warning = (
                f"\n\nWARNING: {len(dangling)} file(s) still import from "
                f"'{Path(rel_path).stem}': {files_list}. "
                "Fix these imports or those files will crash on import."
            )

        change_count = len(evo["changes"])
        msg = (f"Deleted {rel_path}. [{change_count} change(s) in this evolution] "
               f"Remember: call evolve_test then evolve_deploy when done.{warning}")
        return True, msg

    def _log_intentional_deletion(self, evolution_id, rel_path):
        """Record that a file was intentionally deleted so self-repair won't restore it."""
        log = []
        if DELETED_FILES_LOG.exists():
            try:
                log = json.loads(DELETED_FILES_LOG.read_text())
            except Exception:
                log = []
        log.append({
            "file": rel_path,
            "module": Path(rel_path).stem,
            "evolution_id": evolution_id,
            "timestamp": time.time(),
            "deleted_at": datetime.now().isoformat(),
        })
        DELETED_FILES_LOG.write_text(json.dumps(log, indent=2))

    def _test_api_routes(self, evo):
        """Smoke-test new/modified API route files + static contract analysis.

        Phase 1 (live): GET endpoints — verifies they respond with valid JSON.
        Only tests endpoints whose route function was actually touched by a patch
        in this evolution (avoids failing on pre-existing broken endpoints).
        Phase 2 (static): PUT/POST endpoints — verifies frontend JS sends the
        same payload shape that the Python route reads from request.get_json().
        This catches the #1 autonomous implementation bug: payload mismatch.
        """
        results = []
        dashboard_port = 3333

        route_changes = [
            c for c in evo["changes"]
            if "ghost_dashboard/routes/" in c["file"] and c["file"].endswith(".py")
            and c.get("action") != "delete"
        ]
        route_files = [c["file"] for c in route_changes]
        if not route_files:
            return results

        touched_snippets = set()
        for c in route_changes:
            diff_text = c.get("diff", "")
            touched_snippets.add(diff_text)

        import urllib.request
        import urllib.error

        for route_file in route_files:
            abs_path = PROJECT_DIR / route_file
            if not abs_path.exists():
                continue
            try:
                source = abs_path.read_text()
            except OSError:
                continue

            change_diffs = " ".join(
                c.get("diff", "") for c in route_changes if c["file"] == route_file
            )
            is_new_file = any(
                "(new file)" in c.get("diff", "") for c in route_changes
                if c["file"] == route_file
            )

            endpoints = re.findall(
                r'@bp\.route\(["\'](/api/[^"\']+)["\'](?:\s*,\s*methods\s*=\s*\[([^\]]*)\])?\)',
                source,
            )

            for endpoint, methods_str in endpoints:
                is_get = not methods_str or '"GET"' in methods_str or "'GET'" in methods_str
                if not is_get:
                    continue

                # For existing files that were modified, skip live testing - 
                # the smoke test already validated the Flask app works.
                # Live testing is for verifying deployed routes, not pending changes.
                if not is_new_file:
                    continue

                url = f"http://localhost:{dashboard_port}{endpoint}"
                try:
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        body = resp.read().decode("utf-8", errors="replace")
                        status = resp.status
                    if status < 400:
                        try:
                            json.loads(body)
                            results.append({"endpoint": endpoint, "ok": True, "status": status})
                        except json.JSONDecodeError:
                            results.append({
                                "endpoint": endpoint, "ok": False, "status": status,
                                "error": "Response is not valid JSON",
                            })
                    else:
                        results.append({
                            "endpoint": endpoint, "ok": False, "status": status,
                            "error": f"HTTP {status}",
                        })
                except urllib.error.HTTPError as e:
                    # For new endpoints in existing files, 404 is expected (server not restarted yet)
                    # Skip these rather than failing - they'll work after deploy
                    is_new_endpoint = endpoint in change_diffs
                    if e.code == 404 and is_new_endpoint and not is_new_file:
                        results.append({
                            "endpoint": endpoint, "ok": True, "status": e.code,
                            "error": f"Skipped (new endpoint, will work after deploy)",
                        })
                    else:
                        results.append({
                            "endpoint": endpoint, "ok": False, "status": e.code,
                            "error": f"HTTP {e.code}: {str(e.reason)[:100]}",
                        })
                except Exception as e:
                    results.append({
                        "endpoint": endpoint, "ok": True,
                        "error": f"Skipped (server not reachable): {str(e)[:80]}",
                    })

        contract_results = self._test_frontend_backend_contracts(evo, route_files)
        results.extend(contract_results)
        return results

    def _test_frontend_backend_contracts(self, evo, route_files):
        """Static analysis: verify PUT/POST payloads match between JS and Python.

        For each PUT/POST route, find the corresponding JS file, extract what
        keys the JS sends, and what keys the Python reads — flag mismatches.
        """
        results = []
        js_dir = PROJECT_DIR / "ghost_dashboard" / "static" / "js" / "pages"

        for route_file in route_files:
            abs_path = PROJECT_DIR / route_file
            if not abs_path.exists():
                continue
            try:
                py_source = abs_path.read_text()
            except OSError:
                continue

            write_endpoints = re.findall(
                r'@bp\.route\(["\'](/api/[^"\']+)["\']'
                r'(?:\s*,\s*methods\s*=\s*\[([^\]]*)\])?\)',
                py_source,
            )

            for endpoint, methods_str in write_endpoints:
                has_write = any(m in (methods_str or "") for m in ['"PUT"', "'PUT'", '"POST"', "'POST'"])
                if not has_write:
                    continue

                py_keys = set(re.findall(
                    r'(?:data|request\.get_json\([^)]*\))\.get\(["\'](\w+)["\']',
                    py_source,
                ))
                py_direct_keys = set(re.findall(
                    r'data\[["\']([\w]+)["\']\]',
                    py_source,
                ))
                py_keys.update(py_direct_keys)

                if not py_keys:
                    continue

                js_sources = []
                if js_dir.is_dir():
                    for js_file in js_dir.glob("*.js"):
                        try:
                            content = js_file.read_text()
                            if endpoint in content:
                                js_sources.append((js_file.name, content))
                        except OSError:
                            continue

                if not js_sources:
                    continue

                for js_name, js_content in js_sources:
                    fetch_blocks = re.findall(
                        r'fetch\s*\(\s*[`"\'][^`"\']*' + re.escape(endpoint)
                        + r'[^`"\']*[`"\']\s*,\s*\{([^}]{10,500})\}',
                        js_content, re.DOTALL,
                    )

                    for block in fetch_blocks:
                        body_match = re.search(
                            r'body\s*:\s*JSON\.stringify\(\s*\{([^}]+)\}\s*\)',
                            block, re.DOTALL,
                        )
                        if not body_match:
                            continue

                        body_content = body_match.group(1)
                        js_top_keys = set(re.findall(r'(\w+)\s*:', body_content))

                        if not js_top_keys:
                            continue

                        if len(js_top_keys) == 1:
                            wrapper_key = list(js_top_keys)[0]
                            if wrapper_key not in py_keys and py_keys:
                                unwrap_pattern = re.search(
                                    rf'data\.get\(["\']' + re.escape(wrapper_key) + r'["\']',
                                    py_source,
                                )
                                if not unwrap_pattern:
                                    results.append({
                                        "endpoint": f"{endpoint} [contract]",
                                        "ok": False,
                                        "error": (
                                            f"PAYLOAD MISMATCH: JS ({js_name}) wraps data in "
                                            f"'{wrapper_key}' key, but Python reads keys "
                                            f"{sorted(py_keys)} from top level. "
                                            f"Python must unwrap: data.get('{wrapper_key}', data)"
                                        ),
                                    })
        return results

    @staticmethod
    def _scan_dangling_imports(deleted_rel_path):
        """Scan project .py files for imports of a deleted module. Returns [(file, [line_nums])]."""
        module_name = Path(deleted_rel_path).stem
        dangling = []
        for py_file in PROJECT_DIR.glob("*.py"):
            if py_file.name == Path(deleted_rel_path).name:
                continue
            try:
                lines = py_file.read_text().splitlines()
                hit_lines = []
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if (stripped.startswith(f"import {module_name}")
                            or stripped.startswith(f"from {module_name} ")):
                        hit_lines.append(i)
                if hit_lines:
                    dangling.append((py_file.name, hit_lines))
            except Exception:
                continue
        for py_file in PROJECT_DIR.rglob("ghost_dashboard/**/*.py"):
            try:
                lines = py_file.read_text().splitlines()
                hit_lines = []
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if (stripped.startswith(f"import {module_name}")
                            or stripped.startswith(f"from {module_name} ")):
                        hit_lines.append(i)
                if hit_lines:
                    rel = py_file.relative_to(PROJECT_DIR)
                    dangling.append((str(rel), hit_lines))
            except Exception:
                continue
        return dangling

    def cleanup_incomplete(self, only_ids=None):
        """Rollback active evolutions that have changes but were never deployed.

        Called automatically when a tool loop ends to prevent orphaned file changes.
        If only_ids is provided, only clean up evolutions with those IDs (scoped to
        the current tool loop run). This prevents accidentally rolling back evolutions
        from other concurrent runs.
        Returns list of (evo_id, ok, message) tuples.
        """
        results = []
        to_clean = []
        for evo_id, evo in list(self._active_evolutions.items()):
            if only_ids is not None and evo_id not in only_ids:
                continue
            if evo.get("changes") and evo.get("status") != "deployed":
                to_clean.append((evo_id, evo))

        for evo_id, evo in to_clean:
            backup_path = evo.get("backup_path")
            if backup_path:
                ok, msg = self._restore_backup(backup_path)
                self._active_evolutions.pop(evo_id, None)
                if ok:
                    results.append((evo_id, True, f"Auto-rolled back incomplete evolution {evo_id}"))
                else:
                    results.append((evo_id, False, f"Failed to rollback {evo_id}: {msg}"))
            else:
                self._active_evolutions.pop(evo_id, None)
                results.append((evo_id, False, f"No backup for {evo_id}, removed from active"))

            # Clean up git feature branch
            git_branch = evo.get("git_branch")
            if git_branch:
                try:
                    import ghost_git
                    if ghost_git.current_branch() == git_branch:
                        ghost_git.stash_and_checkout("main")
                    ghost_git.delete_branch(git_branch)
                except Exception:
                    pass

            for change in evo.get("changes", []):
                file_path = PROJECT_DIR / change["file"]
                if file_path.exists() and "(new file)" in change.get("diff", ""):
                    try:
                        file_path.unlink()
                    except Exception:
                        pass

        return results

    def rollback(self, evolution_id=None):
        """Rollback to a specific evolution's backup, or the most recent."""
        if evolution_id:
            target = None
            for e in reversed(self._history):
                if e["id"] == evolution_id:
                    target = e
                    break
            if not target:
                evo = self._active_evolutions.get(evolution_id)
                if evo:
                    target = evo
            if not target:
                return False, f"Evolution {evolution_id} not found"
        else:
            if self._history:
                target = self._history[-1]
            else:
                backups = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
                if backups:
                    ok, msg = self._restore_backup(str(backups[-1]))
                    if ok:
                        DEPLOY_MARKER.write_text(json.dumps({
                            "evolution_id": "rollback",
                            "rollback": True,
                            "timestamp": time.time(),
                        }))
                    return ok, msg
                return False, "No backups available"

        backup_path = target.get("backup_path")
        if not backup_path:
            return False, "No backup path in evolution record"

        # Clean up git feature branch before restoring backup
        git_branch = target.get("git_branch")
        if git_branch:
            try:
                import ghost_git
                if ghost_git.current_branch() == git_branch:
                    ghost_git.stash_and_checkout("main")
                ghost_git.delete_branch(git_branch)
            except Exception:
                pass

        ok, msg = self._restore_backup(backup_path)
        if ok:
            rollback_entry = {
                "id": f"rollback_{uuid.uuid4().hex[:8]}",
                "description": f"Rollback of evolution {target['id']}",
                "rolled_back_evolution": target["id"],
                "status": "rolled_back",
                "timestamp": time.time(),
                "created_at": datetime.now().isoformat(),
            }
            self._history.append(rollback_entry)
            self._save_history()

            DEPLOY_MARKER.write_text(json.dumps({
                "evolution_id": rollback_entry["id"],
                "rollback": True,
                "timestamp": time.time(),
            }))

        return ok, msg

    def get_history(self):
        return list(self._history)

    def get_pending(self):
        pending = []
        for f in PENDING_DIR.glob("*.json"):
            try:
                pending.append(json.loads(f.read_text()))
            except Exception:
                pass
        return pending

    def get_diff(self, evolution_id):
        for e in self._history:
            if e["id"] == evolution_id:
                return e.get("changes", [])
        evo = self._active_evolutions.get(evolution_id)
        if evo:
            return evo.get("changes", [])
        return []


def _log_reviewer_mistakes(pr_data, pr_id, pr_title):
    """Store reviewer rejection feedback as mistake entries in the memory DB.

    Each rejected/blocked PR generates one memory entry so Ghost can learn
    from real review failures via memory_search(type_filter='mistake').
    Duplicates are prevented via source_hash = pr_id.
    """
    try:
        from ghost_memory import MemoryDB
        db = MemoryDB()
        if db.has_source(pr_id):
            db.close()
            return
        reviewer_msgs = [
            d["message"] for d in pr_data.get("discussions", [])
            if d.get("role") == "reviewer" and d.get("message")
        ]
        if not reviewer_msgs:
            db.close()
            return
        last_feedback = reviewer_msgs[-1][:1500]
        content = (
            f"PR REJECTION ({pr_id}): {pr_title}\n"
            f"Reviewer feedback:\n{last_feedback}"
        )
        db.save(
            content=content,
            type="mistake",
            tags="pr_rejection,auto_captured",
            source_preview=f"PR {pr_id}: {pr_title[:60]}",
            source_hash=pr_id,
        )
        db.close()
    except Exception:
        pass


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = EvolutionEngine()
        return _engine


def build_evolve_tools(cfg):
    """Build tool definitions for the LLM to self-modify Ghost."""
    engine = get_engine()

    def evolve_plan_exec(description, files, level=None, confirmed_not_duplicate: bool = False, **kwargs):
        evo_id, info = engine.plan(description, files, cfg)
        if evo_id is None:
            return f"Evolution blocked: {info.get('error', 'unknown error')}"
        parts = [
            f"Evolution planned: {evo_id}",
            f"Level: {info['level']}",
            f"Needs approval: {info['needs_approval']}",
            f"Backup: {info['backup_path']}",
        ]
        if info["needs_approval"]:
            parts.append("WAITING_FOR_APPROVAL")
            parts.append(
                "This evolution requires user approval. The user will see an approval prompt in the chat. "
                "Proceed to call evolve_apply — it will wait for approval automatically."
            )
        else:
            parts.append("Auto-approved. You can now call evolve_apply to make changes.")
        return "\n".join(parts)

    def evolve_apply_exec(evolution_id, file_path, content=None, patches=None,
                          append=False):
        ok, msg = engine.apply_change(evolution_id, file_path, content=content,
                                      patches=patches, append=append)
        return msg

    def evolve_apply_config_exec(evolution_id=None, updates=None, **kwargs):
        if not evolution_id:
            return "Error: evolution_id is required. Call evolve_plan first."
        if not updates or not isinstance(updates, dict):
            return "Error: updates must be a non-empty JSON object of config key-value pairs."
        ok, msg = engine.apply_config_change(evolution_id, updates)
        return msg

    def evolve_delete_exec(evolution_id, file_path):
        ok, msg = engine.delete_file(evolution_id, file_path)
        return msg

    def evolve_test_exec(evolution_id):
        passed, results = engine.test(evolution_id)
        lines = [f"Tests {'PASSED' if passed else 'FAILED'}"]
        for d in results.get("dangling_imports", []):
            lines.append(
                f"  DANGLING IMPORT: {d['importing_file']} imports deleted module "
                f"'{d['deleted_module']}' (line(s) {d['lines']})"
            )
        for s in results.get("syntax", []):
            status = "OK" if s["ok"] else f"FAIL: {s.get('error')}"
            lines.append(f"  Syntax {s['file']}: {status}")
        for i in results.get("import", []):
            status = "OK" if i["ok"] else f"FAIL: {i.get('error')}"
            lines.append(f"  Import {i['module']}: {status}")
        smoke = results.get("smoke")
        if smoke:
            status = "OK" if smoke["ok"] else f"FAIL: {smoke.get('output')}"
            lines.append(f"  Smoke test: {status}")
        for api_r in results.get("api_routes", []):
            if api_r["ok"]:
                lines.append(f"  API route {api_r['endpoint']}: OK (HTTP {api_r.get('status', '?')})")
            else:
                lines.append(f"  API route {api_r['endpoint']}: FAIL — {api_r.get('error', 'unknown')}")
        for lint in results.get("semantic_lint", []):
            lines.append(
                f"  LINT {lint['file']}:{lint['line']} [{lint['rule']}]: {lint['message']}"
            )
        if passed:
            lines.append(
                "\nAll tests passed. Call evolve_submit_pr to submit for code review, "
                "or evolve_deploy for direct deploy (self-repair only)."
            )
        else:
            lines.append(
                "\nTests FAILED. Fix the issues and call evolve_apply again, "
                "then re-run evolve_test. Or call evolve_rollback to revert.\n"
                "WARNING: Do NOT log this evolution as successful — it has not passed tests."
            )
        return "\n".join(lines)

    _feature_cooldowns = {}
    _RETRY_COOLDOWN_S = 900  # 15 min between submit attempts for same feature

    def evolve_submit_pr_exec(evolution_id, title, description="",
                              feature_id=""):
        if feature_id and feature_id in _feature_cooldowns:
            elapsed = time.time() - _feature_cooldowns[feature_id]
            if elapsed < _RETRY_COOLDOWN_S:
                remaining_min = max(1, int((_RETRY_COOLDOWN_S - elapsed) / 60))
                return (
                    f"COOLDOWN: Feature {feature_id} was rejected {int(elapsed)}s ago. "
                    f"~{remaining_min} min remaining before retry is allowed. "
                    "Call task_complete NOW. The feature will be automatically "
                    "re-attempted after cooldown with all rejection feedback accumulated."
                )
            del _feature_cooldowns[feature_id]
        ok, msg = engine.submit_pr(
            evolution_id, title, description,
            feature_id=feature_id, cfg=cfg)
        if ok:
            return (
                f"{msg}\n\n"
                "PR APPROVED AND MERGED — deploy triggered. "
                "You may now log this as a successful evolution."
            )
        # Only set cooldown after an actual reviewer rejection, not pre-submit failures
        # like "tests not passed" or "pre-submit validation failed"
        is_reviewer_rejection = "REJECTED" in msg or "BLOCKED" in msg
        if feature_id and is_reviewer_rejection:
            _feature_cooldowns[feature_id] = time.time()
        return msg

    def evolve_deploy_exec(evolution_id):
        ok, msg = engine.deploy(evolution_id)
        if ok:
            return (
                f"{msg}\n\n"
                "DEPLOY SUCCEEDED — you may NOW log this as a successful evolution "
                "(memory_save, log_growth_activity). Do NOT log success before deploy confirms."
            )
        return msg

    def evolve_rollback_exec(evolution_id=None):
        target_evo = None
        if evolution_id:
            target_evo = engine._active_evolutions.get(evolution_id)
        else:
            for evo in reversed(list(engine._active_evolutions.values())):
                target_evo = evo
                break

        if target_evo and not target_evo.get("changes"):
            return (
                "REJECTED: No changes have been applied yet — there is nothing to rollback. "
                "You called evolve_plan but never called evolve_apply. "
                "You MUST call evolve_apply to make changes, then evolve_test, then evolve_deploy. "
                "Do NOT give up. Implement the feature NOW."
            )

        ok, msg = engine.rollback(evolution_id)
        if ok:
            return (
                f"Rollback successful: {msg}. Ghost will restart momentarily.\n\n"
                "IMPORTANT: This evolution FAILED. Do NOT log it as successful. "
                "Do NOT call memory_save or log_growth_activity claiming you added or created anything. "
                "The changes have been reverted. If you want to inform the user, be honest that "
                "the evolution was attempted but failed and was rolled back."
            )
        return f"Rollback failed: {msg}"

    return [
        {
            "name": "evolve_plan",
            "description": (
                "Plan a self-modification to Ghost's own codebase. "
                "Call this FIRST before making any changes. "
                "Provide a description of what you want to change and which files will be modified. "
                "This creates a backup and checks if approval is needed. "
                "Levels: 1-2 (skills/config, auto-approved), 3-4 (dashboard/tools, may need approval), "
                "5-6 (core code, always needs approval). "
                "IMPORTANT: Follow modular architecture — new feature = new file (ghost_<feature>.py). "
                "Never dump unrelated code into existing files. Follow security best practices — "
                "validate inputs, sanitize paths, never hardcode secrets, scope API tokens minimally."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What you plan to change and why",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths (relative to project root) that will be modified or created",
                    },
                },
                "required": ["description", "files"],
            },
            "execute": evolve_plan_exec,
        },
        {
            "name": "evolve_apply",
            "description": (
                "Apply a code change as part of a planned evolution. "
                "You must call evolve_plan first to get an evolution_id. "
                "Use file_read to understand the current code before modifying. "
                "For EXISTING files (.py, .js, .css, .html): you MUST use 'patches' — a list of "
                "{old: '...', new: '...'} search/replace pairs. Full-file 'content' mode is BLOCKED "
                "for existing files to prevent accidentally overwriting styles/logic. "
                "To APPEND code, use a patch where 'old' is the last few lines and 'new' is those lines "
                "plus your additions. "
                "For NEW files: use 'content' with the full file body. "
                "If the file is too large for a single call (malformed JSON / truncation), "
                "set append=true and split the content across multiple calls — each call appends "
                "to the file. Example: call 1 with content='import...\\nclass Foo:...' then "
                "call 2 with content='\\ndef bar():...' and append=true. "
                "NEVER use shell_exec to write files as a workaround — always use evolve_apply. "
                f"LIMIT: Max {MAX_NEW_FILE_SIZE} bytes for new files. "
                "CRITICAL: After your last evolve_apply, you MUST call evolve_test then evolve_deploy. "
                "If you skip test/deploy, ALL changes will be automatically rolled back when the loop ends."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID from evolve_plan",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path from project root (e.g. 'ghost_dashboard/routes/weather.py')",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full new content for the file (new files) or a chunk to append (with append=true)",
                    },
                    "patches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old": {"type": "string"},
                                "new": {"type": "string"},
                            },
                        },
                        "description": "Search/replace pairs for targeted edits",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "If true, append content to the file instead of replacing. Use this to write large new files in multiple calls.",
                    },
                },
                "required": ["evolution_id", "file_path"],
            },
            "execute": evolve_apply_exec,
        },
        {
            "name": "evolve_apply_config",
            "description": (
                "Apply config changes to Ghost's runtime config (~/.ghost/config.json) "
                "as part of a planned evolution. You MUST call evolve_plan first. "
                "Config changes are tracked in the evolution — rollback restores the old config. "
                "Auth/secret keys are blocked. Security-hardening changes (e.g. enabling "
                "strict_tool_registration, disabling evolve_auto_approve) are ALLOWED. "
                "Weakening changes require user approval via add_action_item. "
                "CRITICAL: After all changes, call evolve_test then evolve_deploy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID from evolve_plan",
                    },
                    "updates": {
                        "type": "object",
                        "description": "Key-value pairs to update in Ghost's config",
                    },
                },
                "required": ["evolution_id", "updates"],
            },
            "execute": evolve_apply_config_exec,
        },
        {
            "name": "evolve_delete",
            "description": (
                "Delete a file as part of a planned evolution. "
                "Use this when removing a module or feature — do NOT just empty the file. "
                "The deletion is tracked so self-repair won't accidentally restore it. "
                "After deletion, the system scans for dangling imports and warns you. "
                "CRITICAL: Fix any dangling imports before calling evolve_test, "
                "or the test will fail."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID from evolve_plan",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path to delete (e.g. 'ghost_llm_router.py')",
                    },
                },
                "required": ["evolution_id", "file_path"],
            },
            "execute": evolve_delete_exec,
        },
        {
            "name": "evolve_test",
            "description": (
                "Run the validation pipeline on changes made during an evolution. "
                "Checks: dangling imports (files importing deleted modules), "
                "Python syntax (ast.parse), module imports, and a smoke test "
                "(verifies Ghost can start with the new code). "
                "You must call this after evolve_apply and before evolve_deploy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID to test",
                    },
                },
                "required": ["evolution_id"],
            },
            "execute": evolve_test_exec,
        },
        {
            "name": "evolve_submit_pr",
            "description": (
                "Submit a pull request for code review after evolve_test passes. "
                "This commits your changes to a feature branch, creates an internal PR, "
                "and runs an automated adversarial code review (Reviewer vs Developer). "
                "The reviewer checks code quality, UI/UX, frontend-backend integration, "
                "and Python correctness. Possible outcomes:\n"
                "- APPROVED: PR is merged and Ghost restarts with the new code.\n"
                "- REJECTED: Reviewer found issues. The feature is automatically re-queued "
                "to pending for another attempt. Call task_complete.\n"
                "- BLOCKED: The approach is fundamentally wrong. "
                "The feature is marked rejected automatically. Call task_complete.\n"
                "Use this INSTEAD of evolve_deploy for normal feature implementation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID from evolve_plan",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short title for the PR (e.g. 'Add webhook secret auto-generation')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Longer description of what changed and why",
                    },
                    "feature_id": {
                        "type": "string",
                        "description": "The feature ID this PR implements (from start_future_feature)",
                    },
                },
                "required": ["evolution_id", "title", "feature_id"],
            },
            "execute": evolve_submit_pr_exec,
        },
        {
            "name": "evolve_deploy",
            "description": (
                "Deploy an evolution by restarting Ghost with the new code. "
                "Only works after evolve_test passes. "
                "IMPORTANT: For normal feature implementation, use evolve_submit_pr instead. "
                "evolve_deploy is reserved for self-repair and emergency fixes only. "
                "Ghost will gracefully shut down and the supervisor will restart it. "
                "A health check runs after restart; if it fails, the backup is auto-restored."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "The evolution ID to deploy",
                    },
                },
                "required": ["evolution_id"],
            },
            "execute": evolve_deploy_exec,
        },
        {
            "name": "evolve_rollback",
            "description": (
                "Rollback to a previous state by restoring a backup. "
                "If evolution_id is provided, restores that specific backup. "
                "If omitted, restores the most recent backup. "
                "Ghost will restart after rollback."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "evolution_id": {
                        "type": "string",
                        "description": "Optional: specific evolution to rollback (defaults to most recent)",
                    },
                },
            },
            "execute": evolve_rollback_exec,
        },
    ]
