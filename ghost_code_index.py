"""
ghost_code_index.py — AST-based codebase index for Ghost self-knowledge.

Provides:
  - CodeIndex: Parses Ghost's own source files into a symbol table
  - generate_repo_map(): Compact, always-current codebase map for LLM prompts
  - code_symbol_lookup / code_symbol_list: Precise symbol retrieval tools
  - build_code_index_tools(): ToolRegistry integration

Inspired by Aider's repo-map (tree-sitter + PageRank) and jCodeMunch
(AST symbol indexing with O(1) byte-offset seeking). Uses Python's built-in
ast module — no external dependencies.
"""

import ast
import hashlib
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger("ghost.code_index")

PROJECT_DIR = Path(__file__).resolve().parent
GHOST_HOME = Path.home() / ".ghost"
CACHE_PATH = GHOST_HOME / "code_index.json"

INDEX_GLOBS = [
    "ghost_*.py",
    "ghost_dashboard/routes/*.py",
]

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", "openclaw_ref"}


@dataclass
class SymbolEntry:
    """A single indexed symbol (class, method, function, or constant)."""
    name: str
    kind: str  # class, method, function, constant
    file: str  # relative path from PROJECT_DIR
    line_start: int
    line_end: int
    signature: str  # the def/class line with args
    docstring_first_line: str = ""
    parent_class: str = ""  # for methods: enclosing class name
    args: list = field(default_factory=list)
    returns: str = ""
    is_async: bool = False
    is_public: bool = True
    symbol_id: str = ""  # stable ID: file::QualifiedName#kind (jCodeMunch pattern)
    byte_offset: int = 0  # start byte in source file (for O(1) seeking)
    byte_length: int = 0  # byte length of symbol source
    content_hash: str = ""  # SHA-256 of symbol source bytes (drift detection)


class CodeIndex:
    """AST-based symbol index of Ghost's own codebase."""

    def __init__(self, project_dir: Path = PROJECT_DIR):
        self._project_dir = project_dir.resolve()
        self._symbols: Dict[str, List[SymbolEntry]] = {}  # file -> symbols
        self._all_symbols: List[SymbolEntry] = []
        self._file_mtimes: Dict[str, float] = {}
        self._file_imports: Dict[str, Set[str]] = {}  # file -> set of imported module names
        self._file_ranks: Dict[str, float] = {}  # file -> importance score
        self._lock = threading.Lock()
        self._built = False

    def build(self, force: bool = False) -> int:
        """Parse source files and build the symbol index. Returns symbol count."""
        with self._lock:
            if self._built and not force:
                if not self._any_files_changed():
                    return len(self._all_symbols)

            cached = self._load_cache()
            if cached and not force and not self._any_files_changed_vs(cached.get("mtimes", {})):
                self._symbols = {}
                self._all_symbols = []
                for file_key, entries in cached.get("symbols", {}).items():
                    syms = [SymbolEntry(**e) for e in entries]
                    self._symbols[file_key] = syms
                    self._all_symbols.extend(syms)
                self._file_mtimes = cached.get("mtimes", {})
                self._file_imports = {
                    k: set(v) for k, v in cached.get("imports", {}).items()
                }
                self._compute_reference_ranks()
                self._built = True
                log.info("CodeIndex loaded from cache: %d symbols", len(self._all_symbols))
                return len(self._all_symbols)

            self._symbols = {}
            self._all_symbols = []
            self._file_mtimes = {}
            self._file_imports = {}

            source_files = self._discover_files()
            for fpath in source_files:
                try:
                    symbols = self._parse_file(fpath)
                    rel = str(fpath.relative_to(self._project_dir))
                    self._symbols[rel] = symbols
                    self._all_symbols.extend(symbols)
                    self._file_mtimes[rel] = fpath.stat().st_mtime
                except Exception as exc:
                    log.warning("CodeIndex: failed to parse %s: %s", fpath, exc)

            self._compute_reference_ranks()

            self._built = True
            self._save_cache()
            log.info("CodeIndex built: %d symbols across %d files",
                     len(self._all_symbols), len(self._symbols))
            return len(self._all_symbols)

    def rebuild(self) -> int:
        """Force a full rebuild, discarding cache."""
        return self.build(force=True)

    def generate_repo_map(self, token_budget: int = 3000) -> str:
        """Produce a compact text map of the codebase for LLM system prompts.

        Fits within token_budget (estimated as chars/4). Uses import-based
        reference ranking (Aider pattern) to prioritize the most-referenced
        files first.
        """
        if not self._built:
            self.build()

        char_budget = token_budget * 4
        lines: list[str] = []
        lines.append("\n## GHOST SYSTEM MAP (auto-generated from AST — always current)\n")

        sorted_files = sorted(
            self._symbols.keys(),
            key=lambda f: (-self._file_ranks.get(f, 0), f),
        )

        for rel in sorted_files:
            symbols = self._symbols[rel]
            public_symbols = [s for s in symbols if s.is_public and s.kind in ("class", "function")]
            if not public_symbols:
                continue

            section_lines = [f"{rel}:"]
            for sym in public_symbols:
                if sym.kind == "class":
                    section_lines.append(f"  class {sym.signature}")
                    methods = [s for s in symbols if s.parent_class == sym.name and s.is_public]
                    for m in methods:
                        section_lines.append(f"    {m.signature}")
                elif sym.kind == "function":
                    section_lines.append(f"  {sym.signature}")

            section = "\n".join(section_lines) + "\n"
            current_size = sum(len(l) for l in lines)
            if current_size + len(section) > char_budget:
                if self._file_ranks.get(rel, 0) >= 0.3 and current_size < char_budget * 2:
                    lines.append(section)
                continue
            lines.append(section)

        return "\n".join(lines)

    def lookup_symbol(self, symbol_name: str, file: Optional[str] = None,
                       verify: bool = False) -> Optional[str]:
        """Return the full source code of a symbol by name or stable ID.

        Uses byte-offset seeking when available (jCodeMunch O(1) pattern),
        falling back to line-based reading. Optionally verifies content hash.
        """
        if not self._built:
            self.build()

        # Support lookup by stable symbol_id (jCodeMunch pattern)
        if "::" in symbol_name and "#" in symbol_name:
            for sym in self._all_symbols:
                if sym.symbol_id == symbol_name:
                    return self._read_symbol_source(sym, verify=verify)
            return None

        matches = self._find_symbol(symbol_name, file)
        if not matches:
            return None

        results = []
        for sym in matches[:3]:
            src = self._read_symbol_source(sym, verify=verify)
            if src:
                results.append(src)

        return "\n\n".join(results) if results else None

    def _read_symbol_source(self, sym: SymbolEntry, verify: bool = False) -> Optional[str]:
        """Read symbol source, preferring O(1) byte-offset seek."""
        fpath = self._project_dir / sym.file
        if not fpath.exists():
            return None
        try:
            if sym.byte_length > 0:
                raw = fpath.read_bytes()
                chunk = raw[sym.byte_offset:sym.byte_offset + sym.byte_length]
                code = chunk.decode("utf-8", errors="replace")
            else:
                source_lines = fpath.read_text(encoding="utf-8").split("\n")
                start = max(0, sym.line_start - 1)
                end = min(len(source_lines), sym.line_end)
                code = "\n".join(source_lines[start:end])

            header = f"# {sym.file}:{sym.line_start}-{sym.line_end} ({sym.kind})"
            if sym.symbol_id:
                header += f"  [id: {sym.symbol_id}]"

            drift_note = ""
            if verify and sym.content_hash:
                current_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
                if current_hash != sym.content_hash:
                    drift_note = "\n# WARNING: source has changed since last index — rebuild recommended"

            return f"{header}{drift_note}\n{code}"
        except Exception as exc:
            return f"# Error reading {sym.file}: {exc}"

    def list_symbols(self, file: Optional[str] = None) -> str:
        """Return all symbols with signatures, optionally filtered to a file."""
        if not self._built:
            self.build()

        if file:
            target_files = [f for f in self._symbols if file in f]
        else:
            target_files = sorted(self._symbols.keys())

        lines: list[str] = []
        for rel in target_files:
            symbols = self._symbols.get(rel, [])
            if not symbols:
                continue
            lines.append(f"\n{rel}:")
            for sym in symbols:
                if not sym.is_public:
                    continue
                indent = "    " if sym.parent_class else "  "
                prefix = f"[{sym.kind}] " if sym.kind != "method" else ""
                doc = f"  -- {sym.docstring_first_line}" if sym.docstring_first_line else ""
                lines.append(f"{indent}{prefix}{sym.signature}{doc}")

        return "\n".join(lines) if lines else "No symbols found."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_files(self) -> List[Path]:
        """Find all source files to index."""
        files = set()
        for glob_pat in INDEX_GLOBS:
            for fpath in self._project_dir.glob(glob_pat):
                if fpath.is_file() and not any(p in fpath.parts for p in SKIP_DIRS):
                    files.add(fpath)

        tools_dir = self._project_dir / "ghost_tools"
        if tools_dir.is_dir():
            for tool_py in tools_dir.glob("*/tool.py"):
                files.add(tool_py)

        return sorted(files)

    def _parse_file(self, fpath: Path) -> List[SymbolEntry]:
        """Parse a single Python file and extract symbols."""
        source = fpath.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError:
            return []

        rel = str(fpath.relative_to(self._project_dir))
        source_lines = source.split("\n")
        symbols: List[SymbolEntry] = []

        def _walk_class(cls_node, qualified_prefix=""):
            qualified_name = f"{qualified_prefix}.{cls_node.name}" if qualified_prefix else cls_node.name
            symbols.append(self._class_entry(cls_node, rel, source_lines, qualified_name=qualified_name))
            for child in cls_node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(self._method_entry(child, cls_node.name, rel, source_lines, qualified_prefix=qualified_name))
                elif isinstance(child, ast.ClassDef):
                    _walk_class(child, qualified_prefix=qualified_name)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                _walk_class(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(self._function_entry(node, rel, source_lines))

        # Extract import references (Aider pattern: track cross-file dependencies)
        imports: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        self._file_imports[rel] = imports

        return symbols

    @staticmethod
    def _byte_info(node, source_lines: List[str]):
        """Compute byte_offset, byte_length, content_hash from AST node."""
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        chunk = "\n".join(source_lines[start:end]).encode("utf-8")
        offset = len("\n".join(source_lines[:start]).encode("utf-8"))
        if start > 0:
            offset += 1
        return offset, len(chunk), hashlib.sha256(chunk).hexdigest()

    @staticmethod
    def _make_symbol_id(rel: str, qualified_name: str, kind: str) -> str:
        """Generate stable symbol ID (jCodeMunch pattern: file::QualifiedName#kind)."""
        return f"{rel}::{qualified_name}#{kind}"

    def _class_entry(self, node: ast.ClassDef, rel: str, source_lines: List[str],
                      qualified_name: str = "") -> SymbolEntry:
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except Exception:
                bases.append("?")
        base_str = f"({', '.join(bases)})" if bases else ""
        sig = f"{node.name}{base_str}:"
        doc = ast.get_docstring(node) or ""
        first_line = doc.split("\n")[0].strip() if doc else ""
        b_off, b_len, c_hash = self._byte_info(node, source_lines)
        qname = qualified_name or node.name
        parent = qname.rsplit(".", 1)[0] if "." in qname else ""

        return SymbolEntry(
            name=node.name, kind="class", file=rel,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            signature=sig, docstring_first_line=first_line,
            parent_class=parent,
            is_public=not node.name.startswith("_"),
            symbol_id=self._make_symbol_id(rel, qname, "class"),
            byte_offset=b_off, byte_length=b_len, content_hash=c_hash,
        )

    def _method_entry(self, node, parent_class: str, rel: str, source_lines: List[str],
                       qualified_prefix: str = "") -> SymbolEntry:
        sig = self._build_signature(node)
        doc = ast.get_docstring(node) or ""
        first_line = doc.split("\n")[0].strip() if doc else ""

        args = self._extract_args(node, skip_self=True)
        returns = ""
        if node.returns:
            try:
                returns = ast.unparse(node.returns)
            except Exception:
                pass
        b_off, b_len, c_hash = self._byte_info(node, source_lines)
        prefix = qualified_prefix or parent_class
        qualified = f"{prefix}.{node.name}"

        return SymbolEntry(
            name=node.name, kind="method", file=rel,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            signature=sig, docstring_first_line=first_line,
            parent_class=parent_class,
            args=args, returns=returns,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_public=not node.name.startswith("_"),
            symbol_id=self._make_symbol_id(rel, qualified, "method"),
            byte_offset=b_off, byte_length=b_len, content_hash=c_hash,
        )

    def _function_entry(self, node, rel: str, source_lines: List[str]) -> SymbolEntry:
        sig = self._build_signature(node)
        doc = ast.get_docstring(node) or ""
        first_line = doc.split("\n")[0].strip() if doc else ""

        args = self._extract_args(node, skip_self=False)
        returns = ""
        if node.returns:
            try:
                returns = ast.unparse(node.returns)
            except Exception:
                pass
        b_off, b_len, c_hash = self._byte_info(node, source_lines)

        return SymbolEntry(
            name=node.name, kind="function", file=rel,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            signature=sig, docstring_first_line=first_line,
            args=args, returns=returns,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_public=not node.name.startswith("_"),
            symbol_id=self._make_symbol_id(rel, node.name, "function"),
            byte_offset=b_off, byte_length=b_len, content_hash=c_hash,
        )

    @staticmethod
    def _build_signature(node) -> str:
        """Build a human-readable signature string from a function/method AST node."""
        is_async = isinstance(node, ast.AsyncFunctionDef)
        prefix = "async def " if is_async else "def "

        args_parts = []
        args_node = node.args
        num_args = len(args_node.args)
        num_defaults = len(args_node.defaults)
        default_offset = num_args - num_defaults

        for i, arg in enumerate(args_node.args):
            name = arg.arg
            if name == "self" or name == "cls":
                continue
            ann = ""
            if arg.annotation:
                try:
                    ann = ": " + ast.unparse(arg.annotation)
                except Exception:
                    pass
            default_idx = i - default_offset
            default = ""
            if default_idx >= 0:
                try:
                    raw = ast.unparse(args_node.defaults[default_idx])
                    default = "=" + (raw if len(raw) < 30 else "...")
                except Exception:
                    default = "=..."
            args_parts.append(f"{name}{ann}{default}")

        if args_node.vararg:
            args_parts.append(f"*{args_node.vararg.arg}")
        elif args_node.kwonlyargs:
            args_parts.append("*")
        for ki, kw in enumerate(args_node.kwonlyargs):
            name = kw.arg
            ann = ""
            if kw.annotation:
                try:
                    ann = ": " + ast.unparse(kw.annotation)
                except Exception:
                    pass
            kw_default = ""
            if ki < len(args_node.kw_defaults) and args_node.kw_defaults[ki] is not None:
                try:
                    raw = ast.unparse(args_node.kw_defaults[ki])
                    kw_default = "=" + (raw if len(raw) < 30 else "...")
                except Exception:
                    kw_default = "=..."
            args_parts.append(f"{name}{ann}{kw_default}")
        if args_node.kwarg:
            args_parts.append(f"**{args_node.kwarg.arg}")

        ret = ""
        if node.returns:
            try:
                ret = " -> " + ast.unparse(node.returns)
            except Exception:
                pass

        return f"{prefix}{node.name}({', '.join(args_parts)}){ret}"

    @staticmethod
    def _extract_args(node, skip_self: bool = False) -> list:
        args = []
        for arg in node.args.args:
            if skip_self and arg.arg in ("self", "cls"):
                continue
            args.append(arg.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        return args

    def _find_symbol(self, name: str, file: Optional[str] = None) -> List[SymbolEntry]:
        """Find symbols matching a name, optionally scoped to a file."""
        results = []
        search = name.lower()

        if "." in name:
            parts = name.split(".", 1)
            class_name, method_name = parts[0], parts[1]
            for sym in self._all_symbols:
                if file and file not in sym.file:
                    continue
                if sym.kind == "method" and sym.parent_class.lower() == class_name.lower() and sym.name.lower() == method_name.lower():
                    results.append(sym)
            if results:
                return results

        for sym in self._all_symbols:
            if file and file not in sym.file:
                continue
            if sym.name.lower() == search:
                results.append(sym)

        if not results:
            for sym in self._all_symbols:
                if file and file not in sym.file:
                    continue
                if search in sym.name.lower():
                    results.append(sym)

        results.sort(key=lambda s: (0 if s.kind == "class" else 1, s.file))
        return results

    def _any_files_changed(self) -> bool:
        for rel, mtime in self._file_mtimes.items():
            fpath = self._project_dir / rel
            if not fpath.exists() or fpath.stat().st_mtime != mtime:
                return True
        current = {str(f.relative_to(self._project_dir)) for f in self._discover_files()}
        return current != set(self._file_mtimes.keys())

    def _any_files_changed_vs(self, cached_mtimes: Dict[str, float]) -> bool:
        for rel, mtime in cached_mtimes.items():
            fpath = self._project_dir / rel
            if not fpath.exists() or fpath.stat().st_mtime != mtime:
                return True
        current = {str(f.relative_to(self._project_dir)) for f in self._discover_files()}
        return current != set(cached_mtimes.keys())

    def _compute_reference_ranks(self):
        """Compute file importance scores based on cross-file import references.

        Implements a simplified version of Aider's PageRank: files that are
        imported by many other files rank higher. This replaces the crude
        3-level static priority with data-driven relevance.
        """
        indexed_modules: Dict[str, str] = {}
        for rel in self._symbols:
            stem = Path(rel).stem
            indexed_modules[stem] = rel

        in_degree: Dict[str, int] = defaultdict(int)
        for rel, imports in self._file_imports.items():
            for imp in imports:
                target = indexed_modules.get(imp)
                if target and target != rel:
                    in_degree[target] += 1

        max_refs = max(in_degree.values()) if in_degree else 1
        self._file_ranks = {}
        for rel in self._symbols:
            refs = in_degree.get(rel, 0)
            base_score = refs / max_refs if max_refs > 0 else 0

            symbols = self._symbols[rel]
            has_build_tools = any(
                s.kind == "function" and s.name.startswith("build_") and s.name.endswith("_tools")
                for s in symbols
            )
            has_engine = any(
                s.kind == "class" and s.name in (
                    "ToolLoopEngine", "ToolRegistry", "EvolutionEngine",
                    "GhostDaemon", "SkillLoader", "PRStore",
                )
                for s in symbols
            )
            if has_build_tools:
                base_score += 0.3
            if has_engine:
                base_score += 0.3
            self._file_ranks[rel] = base_score

    def _load_cache(self) -> Optional[dict]:
        if not CACHE_PATH.exists():
            return None
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if data.get("project_dir") != str(self._project_dir):
                return None
            return data
        except Exception:
            return None

    def _save_cache(self):
        try:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "project_dir": str(self._project_dir),
                "built_at": time.time(),
                "mtimes": self._file_mtimes,
                "imports": {k: list(v) for k, v in self._file_imports.items()},
                "symbols": {
                    file_key: [asdict(s) for s in syms]
                    for file_key, syms in self._symbols.items()
                },
            }
            CACHE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            log.warning("CodeIndex: failed to save cache: %s", exc)


# ═══════════════════════════════════════════════════════════════
#  Singleton
# ═══════════════════════════════════════════════════════════════

_code_index: Optional[CodeIndex] = None


def get_code_index(project_dir: Path = PROJECT_DIR) -> CodeIndex:
    """Get or create the singleton CodeIndex instance."""
    global _code_index
    if _code_index is None:
        _code_index = CodeIndex(project_dir)
    return _code_index


# ═══════════════════════════════════════════════════════════════
#  Tool builders
# ═══════════════════════════════════════════════════════════════

def build_code_index_tools(cfg: Dict[str, Any], code_index: Optional[CodeIndex] = None):
    """Build code_symbol_lookup and code_symbol_list tools for ToolRegistry."""
    idx = code_index or get_code_index()
    idx.build()

    def code_symbol_lookup(symbol: str, file: str = "", **kwargs) -> str:
        """Look up the full source code of a class, method, or function by name.

        Returns the exact current source code of the symbol, read directly
        from the file. Use 'Class.method' notation for methods.

        Args:
            symbol: Name to look up (e.g. 'ToolRegistry', 'ToolLoopEngine.run',
                    'build_evolve_tools'). Case-insensitive.
            file: Optional filename filter (e.g. 'ghost_loop.py').

        Returns:
            The source code of the matching symbol(s), or an error message.
        """
        if not symbol or not symbol.strip():
            return "Error: symbol name is required."

        result = idx.lookup_symbol(symbol.strip(), file=file.strip() or None)
        if result is None:
            suggestions = []
            search = symbol.strip().lower()
            for sym in idx._all_symbols[:500]:
                if search in sym.name.lower() or sym.name.lower() in search:
                    suggestions.append(f"  {sym.name} ({sym.kind} in {sym.file})")
                    if len(suggestions) >= 5:
                        break
            hint = "\nDid you mean:\n" + "\n".join(suggestions) if suggestions else ""
            return f"Symbol '{symbol}' not found in the code index.{hint}"

        if len(result) > 8000:
            result = result[:8000] + "\n... [truncated — symbol too large]"
        return result

    def code_symbol_list(file: str = "", **kwargs) -> str:
        """List all public symbols (classes, functions) with their signatures.

        Args:
            file: Optional filename filter (e.g. 'ghost_loop.py'). If empty,
                  lists symbols across all indexed files.

        Returns:
            Formatted list of symbols with signatures and brief descriptions.
        """
        result = idx.list_symbols(file=file.strip() or None)
        if len(result) > 10000:
            result = result[:10000] + "\n... [truncated]"
        return result

    tools = []

    tools.append({
        "name": "code_symbol_lookup",
        "description": (
            "Look up the full source code of a class, method, or function in Ghost's "
            "codebase by name. Much more efficient than file_read — returns only the "
            "requested symbol (~200 tokens vs ~15000 for a full file). Use 'Class.method' "
            "for methods. Always prefer this over file_read for exploring Ghost's code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name (e.g. 'ToolRegistry', 'ToolLoopEngine.run', 'build_evolve_tools')",
                },
                "file": {
                    "type": "string",
                    "description": "Optional filename filter (e.g. 'ghost_loop.py')",
                    "default": "",
                },
            },
            "required": ["symbol"],
        },
        "execute": code_symbol_lookup,
    })

    tools.append({
        "name": "code_symbol_list",
        "description": (
            "List all public classes and functions with their signatures in Ghost's "
            "codebase. Optionally filter to a specific file. Use this to understand "
            "what's available in a module before looking up specific symbols."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Optional filename filter (e.g. 'ghost_loop.py'). Empty = all files.",
                    "default": "",
                },
            },
            "required": [],
        },
        "execute": code_symbol_list,
    })

    return tools
