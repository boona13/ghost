import ast
import os
from pathlib import Path

def register(api):
    """Register code complexity analysis tools."""
    
    def analyze_complexity(code_or_path, **kwargs):
        """Analyze Python code complexity metrics."""
        # Load code from file or use string directly
        if isinstance(code_or_path, str) and (code_or_path.endswith('.py') or '/' in code_or_path or '\\' in code_or_path):
            try:
                path = Path(code_or_path).expanduser().resolve()
                if path.exists() and path.suffix == '.py':
                    code = path.read_text(encoding='utf-8')
                    filename = path.name
                else:
                    code = code_or_path
                    filename = "<string>"
            except (OSError, ValueError):
                code = code_or_path
                filename = "<string>"
        else:
            code = code_or_path
            filename = "<string>"
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}", "filename": filename}
        
        lines = code.split('\n')
        functions = []
        classes = []
        
        # Collect functions and classes
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node)
            elif isinstance(node, ast.ClassDef):
                classes.append(node)
        
        # Calculate per-function complexity and nesting depth
        decision_nodes = (ast.If, ast.While, ast.For, ast.ExceptHandler, ast.With, ast.Assert)
        bool_nodes = (ast.BoolOp, ast.Compare)
        
        func_results = []
        for func in functions:
            func_name = func.name
            start_line = func.lineno
            end_line = getattr(func, 'end_lineno', start_line)
            func_lines = end_line - start_line + 1 if end_line else 0
            
            # Cyclomatic complexity: 1 + decision points
            complexity = 1
            max_depth = 0
            
            for child in ast.walk(func):
                if isinstance(child, decision_nodes):
                    complexity += 1
                    # Track nesting depth roughly by checking parent-child in func
                    depth = 0
                    for sub in ast.walk(child):
                        if isinstance(sub, decision_nodes):
                            depth += 1
                    max_depth = max(max_depth, depth)
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
                elif isinstance(child, ast.Compare):
                    complexity += len(child.ops)
            
            func_results.append({
                "name": func_name,
                "line_start": start_line,
                "line_end": end_line,
                "lines": func_lines,
                "complexity": complexity,
                "max_nesting": max_depth
            })
        
        # Find high complexity functions (>10 is considered high)
        high_complexity = [f for f in func_results if f["complexity"] > 10]
        
        return {
            "filename": filename,
            "total_lines": len(lines),
            "function_count": len(functions),
            "class_count": len(classes),
            "functions": func_results,
            "high_complexity_functions": high_complexity,
            "summary": f"{len(functions)} functions, {len(classes)} classes, {len(high_complexity)} high-complexity functions"
        }
    
    def find_long_functions(path, max_lines=50, **kwargs):
        """Find Python functions exceeding a line limit."""
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return {"error": f"File not found: {path}"}
            if file_path.suffix != '.py':
                return {"error": "Only .py files are supported"}
            
            code = file_path.read_text(encoding='utf-8')
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}
        except (OSError, ValueError) as e:
            return {"error": f"Failed to read file: {e}"}
        
        long_funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, 'end_lineno', start)
                lines = end - start + 1 if end else 0
                
                if lines > max_lines:
                    long_funcs.append({
                        "name": node.name,
                        "line_start": start,
                        "line_end": end,
                        "lines": lines
                    })
        
        long_funcs.sort(key=lambda x: x["lines"], reverse=True)
        
        return {
            "filename": file_path.name,
            "max_lines_threshold": max_lines,
            "long_functions": long_funcs,
            "count": len(long_funcs),
            "summary": f"Found {len(long_funcs)} functions exceeding {max_lines} lines"
        }
    
    api.register_tool({
        "name": "analyze_complexity",
        "description": "Analyze Python code complexity: counts functions/classes, calculates cyclomatic complexity per function, tracks nesting depth, and identifies high-complexity functions. Accepts code string or .py file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "code_or_path": {"type": "string", "description": "Python code as string, or path to .py file"}
            },
            "required": ["code_or_path"]
        },
        "execute": analyze_complexity
    })
    
    api.register_tool({
        "name": "find_long_functions",
        "description": "Scan a Python file and list all functions exceeding a line count threshold (default 50 lines). Useful for refactoring candidates.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to Python file"},
                "max_lines": {"type": "integer", "description": "Maximum lines allowed per function", "default": 50}
            },
            "required": ["path"]
        },
        "execute": find_long_functions
    })