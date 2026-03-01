"""
ghost_code_intel.py - Code intelligence and analysis

Provides deep code understanding: structure analysis, complexity metrics,
bug patterns, dependency mapping, and improvement suggestions.
"""

import os
import re
import ast
import json
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class CodeMetrics:
    """Metrics for a code file."""
    lines_of_code: int
    blank_lines: int
    comment_lines: int
    function_count: int
    class_count: int
    import_count: int
    complexity_score: float  # Cyclomatic complexity approximation
    maintainability_index: float
    issues: List[Dict[str, Any]]


@dataclass
class FunctionInfo:
    """Information about a function/method."""
    name: str
    line_start: int
    line_end: int
    args: List[str]
    returns: Optional[str]
    docstring: Optional[str]
    complexity: int
    is_method: bool
    is_async: bool


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    line_start: int
    line_end: int
    methods: List[FunctionInfo]
    bases: List[str]
    docstring: Optional[str]


class PythonAnalyzer:
    """Analyze Python source code."""
    
    # Common bug patterns
    BUG_PATTERNS = [
        (r"except\s*:\s*$", "bare_except", "Bare except clause - catches KeyboardInterrupt and SystemExit"),
        (r"\.has_key\s*\(", "deprecated_has_key", "dict.has_key() is deprecated, use 'in'"),
        (r"print\s+[\"']", "python2_print", "Python 2 print statement found"),
        (r"__future__.*print_function", None, None),  # Ignore if using future
        (r"eval\s*\(", "dangerous_eval", "eval() can execute arbitrary code"),
        (r"exec\s*\(", "dangerous_exec", "exec() can execute arbitrary code"),
        (r"input\s*\(", "python2_input", "input() in Python 2 is dangerous, use raw_input()"),
        (r"\.format\s*\([^)]*%", "format_security", "String formatting with user input can lead to injection"),
        (r"os\.system\s*\(", "os_system", "os.system() is unsafe with user input"),
        (r"subprocess\.call.*shell\s*=\s*True", "shell_injection", "shell=True with user input is dangerous"),
        (r"password\s*=\s*[\"'][^\"']+[\"']", "hardcoded_password", "Possible hardcoded password"),
        (r"SECRET\s*=\s*[\"'][^\"']+[\"']", "hardcoded_secret", "Possible hardcoded secret"),
        (r"API_KEY\s*=\s*[\"'][^\"']+[\"']", "hardcoded_api_key", "Possible hardcoded API key"),
        (r"TODO|FIXME|XXX|HACK", "todo_marker", "TODO/FIXME marker found"),
    ]
    
    def __init__(self, source_code: str, filename: str = "<unknown>"):
        self.source = source_code
        self.filename = filename
        self.lines = source_code.split('\n')
        self.tree = None
        try:
            self.tree = ast.parse(source_code)
        except SyntaxError as e:
            self.syntax_error = e
        
    def analyze(self) -> Dict[str, Any]:
        """Perform full analysis."""
        if hasattr(self, 'syntax_error'):
            return {
                "error": f"Syntax error: {self.syntax_error}",
                "filename": self.filename
            }
        
        metrics = self._calculate_metrics()
        functions = self._extract_functions()
        classes = self._extract_classes()
        imports = self._extract_imports()
        issues = self._find_issues()
        
        return {
            "filename": self.filename,
            "language": "python",
            "metrics": asdict(metrics),
            "functions": [asdict(f) for f in functions],
            "classes": [asdict(c) for c in classes],
            "imports": imports,
            "issues": issues,
            "summary": self._generate_summary(metrics, functions, classes, issues)
        }
    
    def _calculate_metrics(self) -> CodeMetrics:
        """Calculate code metrics."""
        loc = len(self.lines)
        blank = sum(1 for line in self.lines if not line.strip())
        comments = sum(1 for line in self.lines if line.strip().startswith('#'))
        
        functions = [node for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)]
        classes = [node for node in ast.walk(self.tree) if isinstance(node, ast.ClassDef)]
        imports = [node for node in ast.walk(self.tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        
        # Calculate complexity
        complexity = self._calculate_complexity()
        
        # Maintainability index approximation
        halstead_volume = loc * 1.5  # Simplified
        mi = max(0, 171 - 5.2 * (complexity / 10) - 0.23 * loc - 16.2 * (comments / max(loc, 1)))
        
        return CodeMetrics(
            lines_of_code=loc,
            blank_lines=blank,
            comment_lines=comments,
            function_count=len(functions),
            class_count=len(classes),
            import_count=len(imports),
            complexity_score=complexity,
            maintainability_index=round(mi, 2),
            issues=[]
        )
    
    def _calculate_complexity(self) -> float:
        """Calculate cyclomatic complexity approximation."""
        complexity = 0
        
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, ast.Compare):
                complexity += len(node.ops) - 1
        
        return max(1, complexity)
    
    def _extract_functions(self) -> List[FunctionInfo]:
        """Extract function information."""
        functions = []
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                # Get docstring
                docstring = ast.get_docstring(node)
                
                # Get args
                args = []
                if node.args.args:
                    args = [arg.arg for arg in node.args.args]
                if node.args.vararg:
                    args.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg:
                    args.append(f"**{node.args.kwarg.arg}")
                
                # Get return annotation
                returns = None
                if node.returns:
                    returns = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
                
                # Calculate function complexity
                func_complexity = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For)):
                        func_complexity += 1
                
                functions.append(FunctionInfo(
                    name=node.name,
                    line_start=node.lineno,
                    line_end=getattr(node, 'end_lineno', node.lineno),
                    args=args,
                    returns=returns,
                    docstring=docstring,
                    complexity=func_complexity,
                    is_method=False,  # Determined by parent check
                    is_async=isinstance(node, ast.AsyncFunctionDef)
                ))
        
        return functions
    
    def _extract_classes(self) -> List[ClassInfo]:
        """Extract class information."""
        classes = []
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        docstring = ast.get_docstring(child)
                        args = [arg.arg for arg in child.args.args[1:]]  # Exclude self
                        
                        func_complexity = 1
                        for grandchild in ast.walk(child):
                            if isinstance(grandchild, (ast.If, ast.While, ast.For)):
                                func_complexity += 1
                        
                        methods.append(FunctionInfo(
                            name=child.name,
                            line_start=child.lineno,
                            line_end=getattr(child, 'end_lineno', child.lineno),
                            args=args,
                            returns=None,
                            docstring=docstring,
                            complexity=func_complexity,
                            is_method=True,
                            is_async=isinstance(child, ast.AsyncFunctionDef)
                        ))
                
                classes.append(ClassInfo(
                    name=node.name,
                    line_start=node.lineno,
                    line_end=getattr(node, 'end_lineno', node.lineno),
                    methods=methods,
                    bases=[ast.unparse(base) if hasattr(ast, 'unparse') else str(base) for base in node.bases],
                    docstring=ast.get_docstring(node)
                ))
        
        return classes
    
    def _extract_imports(self) -> List[Dict[str, Any]]:
        """Extract import information."""
        imports = []
        
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "type": "import",
                        "module": alias.name,
                        "name": alias.asname or alias.name,
                        "line": node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append({
                        "type": "from_import",
                        "module": module,
                        "name": alias.asname or alias.name,
                        "line": node.lineno
                    })
        
        return imports
    
    def _find_issues(self) -> List[Dict[str, Any]]:
        """Find code quality and security issues."""
        issues = []
        
        for pattern, issue_type, description in self.BUG_PATTERNS:
            if issue_type is None:
                continue  # Skip exclusion patterns
            
            for match in re.finditer(pattern, self.source, re.MULTILINE | re.IGNORECASE):
                # Find line number
                line_num = self.source[:match.start()].count('\n') + 1
                
                # Get surrounding context
                line_start = max(0, line_num - 1)
                line_end = min(len(self.lines), line_num + 1)
                context = '\n'.join(self.lines[line_start:line_end])
                
                severity = "error" if issue_type in ["dangerous_eval", "dangerous_exec", "shell_injection"] else \
                          "warning" if issue_type in ["bare_except", "hardcoded_password", "hardcoded_secret", "hardcoded_api_key"] else \
                          "info"
                
                issues.append({
                    "type": issue_type,
                    "severity": severity,
                    "line": line_num,
                    "message": description,
                    "context": context.strip()
                })
        
        return issues
    
    def _generate_summary(self, metrics: CodeMetrics, functions: List[FunctionInfo],
                         classes: List[ClassInfo], issues: List[Dict]) -> str:
        """Generate human-readable summary."""
        errors = sum(1 for i in issues if i["severity"] == "error")
        warnings = sum(1 for i in issues if i["severity"] == "warning")
        
        summary = f"""
📊 Code Analysis Summary for {self.filename}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 Lines of Code: {metrics.lines_of_code} ({metrics.comment_lines} comments)
🔧 Functions: {len(functions)} | Classes: {len(classes)} | Imports: {metrics.import_count}
📈 Complexity: {metrics.complexity_score:.1f} | Maintainability: {metrics.maintainability_index:.1f}/171
⚠️  Issues: {errors} errors, {warnings} warnings

""".strip()
        
        if errors > 0:
            summary += "\n\n🚨 Critical issues require immediate attention!"
        elif warnings > 0:
            summary += "\n\n⚡ Some improvements recommended."
        else:
            summary += "\n\n✅ Clean code! No major issues found."
        
        return summary


class RepositoryAnalyzer:
    """Analyze an entire repository."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.files_analyzed = 0
        self.total_issues = 0
        self.dependency_graph = {}
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze entire repository."""
        python_files = list(self.repo_path.rglob("*.py"))
        
        file_analyses = []
        all_imports = []
        all_issues = []
        
        for py_file in python_files:
            # Skip common directories
            if any(part.startswith('.') or part in ['venv', 'env', '__pycache__', 'node_modules'] 
                   for part in py_file.parts):
                continue
            
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    source = f.read()
                
                relative_path = py_file.relative_to(self.repo_path)
                analyzer = PythonAnalyzer(source, str(relative_path))
                result = analyzer.analyze()
                
                if "error" not in result:
                    file_analyses.append(result)
                    all_imports.extend(result.get("imports", []))
                    all_issues.extend(result.get("issues", []))
                    self.files_analyzed += 1
                    
            except Exception as e:
                continue
        
        # Calculate aggregate metrics
        total_loc = sum(f["metrics"]["lines_of_code"] for f in file_analyses)
        total_functions = sum(f["metrics"]["function_count"] for f in file_analyses)
        total_classes = sum(f["metrics"]["class_count"] for f in file_analyses)
        
        # Find most complex files
        complex_files = sorted(file_analyses, 
                              key=lambda x: x["metrics"]["complexity_score"], 
                              reverse=True)[:5]
        
        # Find files with most issues
        problematic_files = sorted(file_analyses,
                                  key=lambda x: len(x.get("issues", [])),
                                  reverse=True)[:5]
        
        return {
            "repository": str(self.repo_path),
            "files_analyzed": self.files_analyzed,
            "total_python_files": len(python_files),
            "aggregate_metrics": {
                "total_lines_of_code": total_loc,
                "total_functions": total_functions,
                "total_classes": total_classes,
                "total_issues": len(all_issues),
                "errors": sum(1 for i in all_issues if i["severity"] == "error"),
                "warnings": sum(1 for i in all_issues if i["severity"] == "warning")
            },
            "most_complex_files": [
                {"file": f["filename"], "complexity": f["metrics"]["complexity_score"]}
                for f in complex_files
            ],
            "most_problematic_files": [
                {"file": f["filename"], "issues": len(f.get("issues", []))}
                for f in problematic_files
            ],
            "top_issues": self._categorize_issues(all_issues),
            "recommendations": self._generate_recommendations(file_analyses, all_issues)
        }
    
    def _categorize_issues(self, issues: List[Dict]) -> Dict[str, int]:
        """Categorize issues by type."""
        categories = {}
        for issue in issues:
            issue_type = issue["type"]
            categories[issue_type] = categories.get(issue_type, 0) + 1
        return dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10])
    
    def _generate_recommendations(self, analyses: List[Dict], issues: List[Dict]) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []
        
        # Security issues
        security_issues = [i for i in issues if i["severity"] == "error"]
        if security_issues:
            recommendations.append(f"🔒 Fix {len(security_issues)} security issues immediately")
        
        # Complexity
        high_complexity = [a for a in analyses if a["metrics"]["complexity_score"] > 20]
        if high_complexity:
            recommendations.append(f"📝 Refactor {len(high_complexity)} files with high complexity")
        
        # Documentation
        no_docstrings = 0
        for analysis in analyses:
            for func in analysis.get("functions", []):
                if not func.get("docstring"):
                    no_docstrings += 1
        if no_docstrings > 0:
            recommendations.append(f"📚 Add docstrings to {no_docstrings} functions")
        
        # Maintainability
        low_maintainability = [a for a in analyses if a["metrics"]["maintainability_index"] < 50]
        if low_maintainability:
            recommendations.append(f"🏗️ Improve maintainability in {len(low_maintainability)} files")
        
        return recommendations


def make_analyze_code_file():
    """Create the analyze_code_file tool."""
    
    def execute(file_path: str):
        """
        Analyze a single code file for structure, quality, and issues.
        
        Args:
            file_path: Path to the code file
            
        Returns:
            Detailed analysis with metrics, issues, and recommendations
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            return {"error": f"Could not read file: {str(e)}"}
        
        analyzer = PythonAnalyzer(source, os.path.basename(file_path))
        return analyzer.analyze()
    
    return {
        "name": "analyze_code_file",
        "description": "Analyze a code file for structure, complexity, bugs, and quality issues.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the code file to analyze"}
            },
            "required": ["file_path"]
        },
        "execute": execute
    }


def build_code_intel_tools():
    """Build code intelligence tools for the ghost tool registry."""
    return [make_analyze_code_file(), make_analyze_repository(), make_find_code_patterns()]


def make_analyze_repository():
    """Create the analyze_repository tool."""
    
    def execute(repo_path: str):
        """
        Analyze an entire repository for structure, quality, and patterns.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            Repository-wide analysis with aggregate metrics and recommendations
        """
        if not os.path.isdir(repo_path):
            return {"error": f"Not a directory: {repo_path}"}
        
        analyzer = RepositoryAnalyzer(repo_path)
        return analyzer.analyze()
    
    return {
        "name": "analyze_repository",
        "description": "Analyze an entire codebase for structure, dependencies, issues, and improvements.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Path to repository root"}
            },
            "required": ["repo_path"]
        },
        "execute": execute
    }


def make_find_code_patterns():
    """Create the find_code_patterns tool."""
    
    def execute(repo_path: str, pattern: str, file_pattern: str = "*.py"):
        """
        Search for code patterns across a repository.
        
        Args:
            repo_path: Path to repository
            pattern: Regex pattern to search for
            file_pattern: File glob pattern (default: *.py)
            
        Returns:
            List of matches with file paths and line numbers
        """
        import fnmatch
        
        results = []
        repo = Path(repo_path)
        
        for root, dirs, files in os.walk(repo):
            # Skip hidden and common non-source dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      ['venv', 'env', '__pycache__', 'node_modules', 'dist', 'build']]
            
            for file in files:
                if fnmatch.fnmatch(file, file_pattern):
                    file_path = Path(root) / file
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        for match in re.finditer(pattern, content, re.MULTILINE):
                            line_num = content[:match.start()].count('\n') + 1
                            line_content = content.split('\n')[line_num - 1].strip()
                            
                            results.append({
                                "file": str(file_path.relative_to(repo)),
                                "line": line_num,
                                "match": match.group(),
                                "context": line_content
                            })
                    except Exception:
                        continue
        
        return {
            "pattern": pattern,
            "files_searched": len(list(repo.rglob(file_pattern))),
            "matches": results[:50],  # Limit results
            "total_matches": len(results)
        }
    
    return {
        "name": "find_code_patterns",
        "description": "Search for regex patterns across all files in a repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Repository path"},
                "pattern": {"type": "string", "description": "Regex pattern to search"},
                "file_pattern": {"type": "string", "default": "*.py", "description": "File pattern to match"}
            },
            "required": ["repo_path", "pattern"]
        },
        "execute": execute
    }
