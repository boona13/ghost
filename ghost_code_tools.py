"""
ghost_code_tools.py — Fast code search tools inspired by OpenCode.

Provides grep (content search) and glob (file pattern search) using ripgrep
when available, with Python fallback. Results are sorted by modification time
(most recently edited files first) for coding relevance.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_DIR = Path(__file__).resolve().parent
MAX_LINE_LENGTH = 2000
MAX_MATCHES = 100
MAX_GLOB_RESULTS = 100

_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", "venv", "env",
    ".venv", ".env", "dist", "build", ".next", ".cache", ".tox",
    "eggs", "*.egg-info", ".mypy_cache", ".pytest_cache",
}


def _has_ripgrep() -> Optional[str]:
    """Return ripgrep binary path if available."""
    return shutil.which("rg")


def _resolve_search_path(path: Optional[str]) -> Path:
    """Resolve a search path, defaulting to PROJECT_DIR."""
    if not path:
        return PROJECT_DIR
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (PROJECT_DIR / p).resolve()
    return p


def _should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in _SKIP_DIRS or part.startswith("."):
            return True
    return False


# ─────────────────────────────────────────────────────
#  GREP — regex content search
# ─────────────────────────────────────────────────────

def _grep_ripgrep(pattern: str, search_path: Path, include: str = "") -> str:
    """Use ripgrep for fast content search."""
    rg = _has_ripgrep()
    if not rg:
        return ""

    args = [
        rg, "-nH", "--no-heading", "--hidden", "--no-messages",
        "--color=never", "--max-columns", str(MAX_LINE_LENGTH),
        "--max-count", "500",
    ]
    if include:
        for glob in include.split(","):
            glob = glob.strip()
            if glob:
                args.extend(["--glob", glob])

    args.extend(["--regexp", pattern, str(search_path)])

    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=30,
            cwd=str(search_path),
        )
        if result.returncode in (0, 1, 2):
            return result.stdout
        return ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _grep_python(pattern: str, search_path: Path, include: str = "") -> List[Dict]:
    """Pure Python fallback for grep."""
    import fnmatch

    include_patterns = [p.strip() for p in include.split(",") if p.strip()] if include else []
    compiled = re.compile(pattern, re.MULTILINE)
    matches = []

    for root, dirs, files in os.walk(search_path):
        rel_root = Path(root).relative_to(search_path)
        if _should_skip(rel_root):
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            if include_patterns and not any(fnmatch.fnmatch(fname, p) for p in include_patterns):
                continue

            fpath = Path(root) / fname
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            for m in compiled.finditer(text):
                line_num = text[:m.start()].count("\n") + 1
                line_text = text.split("\n")[line_num - 1] if line_num <= text.count("\n") + 1 else ""
                mtime = fpath.stat().st_mtime
                matches.append({
                    "path": str(fpath),
                    "line": line_num,
                    "text": line_text[:MAX_LINE_LENGTH],
                    "mtime": mtime,
                })
                if len(matches) >= MAX_MATCHES * 5:
                    return matches
    return matches


def _format_grep_results(raw_output: str, search_path: Path) -> str:
    """Parse ripgrep output, sort by mtime, format for LLM."""
    if not raw_output.strip():
        return "No matches found"

    entries = []
    for line in raw_output.strip().split("\n"):
        if not line:
            continue
        parts = line.split(":", 2)
        if len(parts) < 3:
            continue
        fpath, line_num_str, line_text = parts[0], parts[1], parts[2]
        try:
            line_num = int(line_num_str)
        except ValueError:
            continue
        try:
            mtime = Path(fpath).stat().st_mtime
        except OSError:
            mtime = 0
        entries.append({
            "path": fpath,
            "line": line_num,
            "text": line_text[:MAX_LINE_LENGTH],
            "mtime": mtime,
        })

    entries.sort(key=lambda e: e["mtime"], reverse=True)

    truncated = len(entries) > MAX_MATCHES
    entries = entries[:MAX_MATCHES]

    if not entries:
        return "No matches found"

    total = len(entries) if not truncated else f"{MAX_MATCHES}+ (truncated)"
    lines = [f"Found {total} matches (sorted by most recently modified):\n"]
    current_file = ""
    for e in entries:
        if e["path"] != current_file:
            if current_file:
                lines.append("")
            current_file = e["path"]
            lines.append(f"{current_file}:")
        text = e["text"].rstrip()
        if len(text) > MAX_LINE_LENGTH:
            text = text[:MAX_LINE_LENGTH] + "..."
        lines.append(f"  Line {e['line']}: {text}")

    if truncated:
        lines.append(f"\n(Showing {MAX_MATCHES} of many matches. Use a more specific pattern or path.)")

    return "\n".join(lines)


def _format_python_results(matches: List[Dict]) -> str:
    """Format Python fallback results."""
    if not matches:
        return "No matches found"

    matches.sort(key=lambda e: e["mtime"], reverse=True)
    truncated = len(matches) > MAX_MATCHES
    matches = matches[:MAX_MATCHES]

    total = len(matches) if not truncated else f"{MAX_MATCHES}+ (truncated)"
    lines = [f"Found {total} matches (sorted by most recently modified):\n"]
    current_file = ""
    for m in matches:
        if m["path"] != current_file:
            if current_file:
                lines.append("")
            current_file = m["path"]
            lines.append(f"{current_file}:")
        lines.append(f"  Line {m['line']}: {m['text'].rstrip()}")

    if truncated:
        lines.append(f"\n(Showing {MAX_MATCHES} of many matches. Use a more specific pattern or path.)")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────
#  GLOB — file pattern search
# ─────────────────────────────────────────────────────

def _glob_ripgrep(pattern: str, search_path: Path) -> List[str]:
    """Use ripgrep --files with glob."""
    rg = _has_ripgrep()
    if not rg:
        return []

    args = [rg, "--files", "--hidden", "--no-messages", "--glob", pattern, str(search_path)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if result.returncode in (0, 1):
            return [p for p in result.stdout.strip().split("\n") if p]
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _glob_python(pattern: str, search_path: Path) -> List[str]:
    """Pure Python fallback for glob."""
    if not pattern.startswith("**/"):
        pattern = "**/" + pattern

    results = []
    for p in search_path.glob(pattern):
        if _should_skip(p.relative_to(search_path)):
            continue
        if p.is_file():
            results.append(str(p))
            if len(results) >= MAX_GLOB_RESULTS * 2:
                break
    return results


def _sort_by_mtime(paths: List[str]) -> List[str]:
    """Sort file paths by modification time (newest first)."""
    timed = []
    for p in paths:
        try:
            mtime = Path(p).stat().st_mtime
        except OSError:
            mtime = 0
        timed.append((p, mtime))
    timed.sort(key=lambda x: x[1], reverse=True)
    return [t[0] for t in timed]


# ─────────────────────────────────────────────────────
#  TOOL BUILDERS
# ─────────────────────────────────────────────────────

def build_code_search_tools(cfg: dict = None) -> List[Dict[str, Any]]:
    """Build grep and glob tools for the Ghost tool registry."""
    cfg = cfg or {}

    def _grep_execute(pattern: str, path: str = "", include: str = ""):
        if not pattern:
            return "Error: pattern is required"
        search_path = _resolve_search_path(path)

        if search_path.is_file():
            search_path = search_path.parent
            include = Path(path).name

        if not search_path.is_dir():
            return f"Error: not a directory: {search_path}"

        if _has_ripgrep():
            raw = _grep_ripgrep(pattern, search_path, include)
            return _format_grep_results(raw, search_path)
        else:
            matches = _grep_python(pattern, search_path, include)
            return _format_python_results(matches)

    def _glob_execute(pattern: str, path: str = ""):
        if not pattern:
            return "Error: pattern is required"
        search_path = _resolve_search_path(path)
        if search_path.is_file():
            search_path = search_path.parent
        if not search_path.is_dir():
            return f"Error: not a directory: {search_path}"

        if _has_ripgrep():
            files = _glob_ripgrep(pattern, search_path)
        else:
            files = _glob_python(pattern, search_path)

        files = _sort_by_mtime(files)
        truncated = len(files) > MAX_GLOB_RESULTS
        files = files[:MAX_GLOB_RESULTS]

        if not files:
            return "No files found"

        output = [f"Found {len(files)} files{' (truncated)' if truncated else ''} (sorted by most recently modified):\n"]
        output.extend(files)
        if truncated:
            output.append(f"\n(Showing {MAX_GLOB_RESULTS} results. Use a more specific pattern or path.)")
        return "\n".join(output)

    return [
        {
            "name": "grep",
            "description": (
                "Fast content search across the codebase using regular expressions. "
                "Results are sorted by most recently modified files first. "
                "Supports full regex syntax (e.g. 'log.*Error', 'function\\s+\\w+'). "
                "Use the include parameter to filter files (e.g. '*.py', '*.{ts,tsx}'). "
                "Use this when you need to find code containing specific patterns. "
                "For broad open-ended exploration, combine with glob."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for in file contents",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Defaults to Ghost project root.",
                        "default": "",
                    },
                    "include": {
                        "type": "string",
                        "description": "File pattern filter (e.g. '*.py', '*.js', '*.{ts,tsx}')",
                        "default": "",
                    },
                },
                "required": ["pattern"],
            },
            "execute": _grep_execute,
        },
        {
            "name": "glob",
            "description": (
                "Fast file pattern matching tool that works with any codebase size. "
                "Returns matching file paths sorted by modification time (newest first). "
                "Use this when you need to find files by name patterns. "
                "Supports patterns like '*.py', '**/*.test.js', 'src/**/*.ts'. "
                "Prefer grep for searching file CONTENTS, glob for finding files by NAME."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match files (e.g. '*.py', '**/*.test.js')",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Defaults to Ghost project root.",
                        "default": "",
                    },
                },
                "required": ["pattern"],
            },
            "execute": _glob_execute,
        },
    ]
