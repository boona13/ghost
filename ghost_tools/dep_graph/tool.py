"""Python Import Dependency Graph Tool.

Analyzes Python import dependencies in a project.
Features:
- Build a dependency graph showing which files import which
- Classify imports as stdlib, third-party, or local
- Impact analysis: find all files that depend on a target module
"""

import ast
import json
import sys
from pathlib import Path
from collections import defaultdict


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""
    
    def python_dep_graph(project_path: str, target_file: str = None, allowed_roots: list = None, **kwargs):
        """
        Analyze Python import dependencies in a project.
        
        Args:
            project_path: Path to the Python project to analyze
            target_file: Optional file to analyze impact (find all files that depend on it)
            allowed_roots: List of allowed root paths for security validation
        
        Returns:
            JSON with dependency graph, import classifications, and impact analysis
        """
        try:
            # Validate inputs
            if not project_path:
                return json.dumps({"error": "project_path is required"})
            
            # Resolve and validate project path
            try:
                project_root = Path(project_path).expanduser().resolve()
            except Exception as e:
                return json.dumps({"error": f"Invalid project_path: {e}"})
            
            if not project_root.exists():
                return json.dumps({"error": f"Project path does not exist: {project_path}"})
            
            if not project_root.is_dir():
                return json.dumps({"error": f"Project path is not a directory: {project_path}"})
            
            # Security: check against allowed_roots
            if allowed_roots:
                allowed = False
                for root in allowed_roots:
                    try:
                        root_resolved = Path(root).expanduser().resolve()
                        if str(project_root).startswith(str(root_resolved)):
                            allowed = True
                            break
                    except Exception:
                        continue
                if not allowed:
                    return json.dumps({"error": "Project path is not within allowed roots"})
            
            api.log(f"Analyzing Python imports in: {project_root}")
            
            # Find all Python files
            py_files = list(project_root.rglob("*.py"))
            api.log(f"Found {len(py_files)} Python files")
            
            if not py_files:
                return json.dumps({
                    "files_analyzed": 0,
                    "dependency_graph": {},
                    "import_summary": {"stdlib": 0, "third_party": 0, "local": 0},
                    "impact_analysis": None
                })
            
            # Get stdlib module names for classification
            stdlib_modules = sys.stdlib_module_names if hasattr(sys, 'stdlib_module_names') else set()
            
            # Build dependency graph
            dependency_graph = {}
            all_imports = {"stdlib": set(), "third_party": set(), "local": set()}
            
            for py_file in py_files:
                rel_path = str(py_file.relative_to(project_root))
                imports = analyze_file_imports(py_file, project_root, stdlib_modules)
                dependency_graph[rel_path] = imports
                
                # Aggregate imports by category
                for category, modules in imports["classified"].items():
                    all_imports[category].update(modules)
            
            # Build import summary
            import_summary = {
                "stdlib": len(all_imports["stdlib"]),
                "third_party": len(all_imports["third_party"]),
                "local": len(all_imports["local"])
            }
            
            # Impact analysis if target_file provided
            impact_analysis = None
            if target_file:
                impact_analysis = build_impact_analysis(target_file, dependency_graph, project_root)
            
            result = {
                "files_analyzed": len(py_files),
                "dependency_graph": dependency_graph,
                "import_summary": import_summary,
                "impact_analysis": impact_analysis
            }
            
            api.log(f"Analysis complete: {len(py_files)} files, "
                   f"{import_summary['stdlib']} stdlib, "
                   f"{import_summary['third_party']} third-party, "
                   f"{import_summary['local']} local imports")
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            api.log(f"Error analyzing imports: {e}")
            return json.dumps({"error": f"Failed to analyze imports: {str(e)}"})
    
    api.register_tool({
        "name": "python_dep_graph",
        "description": "Analyze Python import dependencies in a project. Builds a dependency graph, classifies imports (stdlib/third-party/local), and optionally performs impact analysis to find all files that depend on a target module.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Path to the Python project to analyze"
                },
                "target_file": {
                    "type": "string",
                    "description": "Optional target file for impact analysis. Returns all files that import this file directly or transitively."
                }
            },
            "required": ["project_path"]
        },
        "execute": python_dep_graph
    })


def analyze_file_imports(py_file: Path, project_root: Path, stdlib_modules: set) -> dict:
    """Analyze imports in a single Python file."""
    result = {
        "imports": [],
        "classified": {
            "stdlib": [],
            "third_party": [],
            "local": []
        }
    }
    
    try:
        content = py_file.read_text(encoding='utf-8')
        tree = ast.parse(content)
    except SyntaxError:
        # Skip files with syntax errors
        return result
    except Exception:
        return result
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split('.')[0]
                result["imports"].append(module_name)
                classify_import(module_name, project_root, stdlib_modules, result["classified"])
                
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_name = node.module.split('.')[0]
                result["imports"].append(module_name)
                classify_import(module_name, project_root, stdlib_modules, result["classified"])
    
    return result


def classify_import(module_name: str, project_root: Path, stdlib_modules: set, classified: dict):
    """Classify an import as stdlib, third_party, or local."""
    # Check if it's a stdlib module
    if module_name in stdlib_modules:
        if module_name not in classified["stdlib"]:
            classified["stdlib"].append(module_name)
        return
    
    # Check if it's a local module (exists as .py file in project)
    local_candidates = [
        project_root / f"{module_name}.py",
        project_root / module_name / "__init__.py",
    ]
    
    for candidate in local_candidates:
        if candidate.exists():
            if module_name not in classified["local"]:
                classified["local"].append(module_name)
            return
    
    # Otherwise it's third-party
    if module_name not in classified["third_party"]:
        classified["third_party"].append(module_name)


def build_impact_analysis(target_file: str, dependency_graph: dict, project_root: Path) -> dict:
    """Build impact analysis showing all files that depend on target_file."""
    # Normalize target file path
    target_normalized = target_file.replace('\\', '/')
    if target_normalized.startswith('./'):
        target_normalized = target_normalized[2:]
    
    # Find the module name for the target file
    target_module = Path(target_normalized).stem
    
    # Find direct dependents
    direct_dependents = []
    for file_path, imports in dependency_graph.items():
        if target_module in imports["imports"]:
            direct_dependents.append(file_path)
    
    # Find transitive dependents (files that depend on direct dependents)
    all_dependents = set(direct_dependents)
    changed = True
    max_iterations = 100  # Prevent infinite loops
    iteration = 0
    
    while changed and iteration < max_iterations:
        changed = False
        iteration += 1
        new_dependents = set()
        
        for dependent in all_dependents:
            dependent_module = Path(dependent).stem
            for file_path, imports in dependency_graph.items():
                if file_path not in all_dependents and dependent_module in imports["imports"]:
                    new_dependents.add(file_path)
                    changed = True
        
        all_dependents.update(new_dependents)
    
    return {
        "target_file": target_file,
        "target_module": target_module,
        "direct_dependents": sorted(direct_dependents),
        "transitive_dependents": sorted(all_dependents - set(direct_dependents)),
        "total_affected_files": len(all_dependents)
    }
