import ast
import sys
from pathlib import Path
from typing import Dict, Optional


class DependencyExtractor:
    """Extract Python dependencies using AST parsing"""

    STDLIB_MODULES = set(sys.stdlib_module_names)

    def __init__(self, code: Optional[str] = None, file_path: Optional[str] = None):
        self.code = code or (Path(file_path).read_text() if file_path else None)
        if not self.code:
            raise ValueError("Either code or file_path required")

    def analyze(self, output_dir: str = None) -> Dict:
        """Extract dependencies and generate requirements.txt"""
        tree = ast.parse(self.code)

        # Extract imports
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])

        # Filter stdlib and sort
        dependencies = sorted(imp for imp in imports if imp not in self.STDLIB_MODULES)

        # Generate requirements.txt
        req_content = "\n".join(dependencies) + "\n" if dependencies else ""
        req_path = None
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            req_path = output_path / "requirements.txt"
            req_path.write_text(req_content)

        return {
            "dependencies": dependencies,
            "dependencies_count": len(dependencies),
            "requirements_txt_content": req_content,
            "requirements_txt_path": str(req_path) if req_path else None,
            "has_fastapi_app": self._has_fastapi_app(tree),
            "has_uvicorn_run": self._has_uvicorn_run(tree),
            "fastapi_app_name": self._get_fastapi_app_name(tree)
        }

    def _has_fastapi_app(self, tree: ast.AST) -> bool:
        """Check if code instantiates FastAPI"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if (isinstance(func, ast.Name) and func.id == 'FastAPI') or \
                   (isinstance(func, ast.Attribute) and func.attr == 'FastAPI'):
                    return True
        return False

    def _get_fastapi_app_name(self, tree: ast.AST) -> Optional[str]:
        """Get FastAPI instance variable name"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                func = node.value.func
                if (isinstance(func, ast.Name) and func.id == 'FastAPI') or \
                   (isinstance(func, ast.Attribute) and func.attr == 'FastAPI'):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            return target.id
        return None

    def _has_uvicorn_run(self, tree: ast.AST) -> bool:
        """Check if code calls uvicorn.run"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == 'run' and isinstance(node.func.value, ast.Name) and \
                   node.func.value.id == 'uvicorn':
                    return True
        return False
