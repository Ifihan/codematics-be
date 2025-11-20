import ast
import sys
import importlib.metadata
from typing import Set, List, Dict, Optional
from pathlib import Path


class DependencyExtractor:
    """Extract Python dependencies using AST parsing"""

    STDLIB_MODULES = set(sys.stdlib_module_names)

    def __init__(self, code: Optional[str] = None, file_path: Optional[str] = None):
        """Initialize with either code string or file path"""
        self.code = code
        self.file_path = file_path
        self.imports: Set[str] = set()
        self.tree: Optional[ast.AST] = None
        self._package_cache: Dict[str, Optional[str]] = {}

    def load_code(self) -> str:
        """Load code from file if not already provided"""
        if self.code:
            return self.code

        if not self.file_path:
            raise ValueError("Either code or file_path must be provided")

        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.code = f.read()

        return self.code

    def parse_ast(self) -> ast.AST:
        """Parse code into AST"""
        if not self.code:
            self.load_code()

        self.tree = ast.parse(self.code)
        return self.tree

    def extract_imports(self) -> Set[str]:
        """Extract all import statements from AST"""
        if not self.tree:
            self.parse_ast()

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base_module = alias.name.split('.')[0]
                    self.imports.add(base_module)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    base_module = node.module.split('.')[0]
                    self.imports.add(base_module)

        return self.imports

    def filter_stdlib(self, imports: Set[str]) -> Set[str]:
        """Remove Python standard library modules"""
        return {imp for imp in imports if imp not in self.STDLIB_MODULES}

    def resolve_package_name(self, import_name: str) -> str:
        """Resolve import name to PyPI package name using installed packages metadata"""
        if import_name in self._package_cache:
            cached = self._package_cache[import_name]
            return cached if cached else import_name

        try:
            for dist in importlib.metadata.distributions():
                if dist.name.lower().replace('-', '_') == import_name.lower().replace('-', '_'):
                    self._package_cache[import_name] = dist.name
                    return dist.name

                if dist.files:
                    for file in dist.files:
                        top_level = str(file).split('/')[0].replace('.py', '')
                        if top_level == import_name:
                            self._package_cache[import_name] = dist.name
                            return dist.name
        except Exception:
            pass

        self._package_cache[import_name] = None
        return import_name

    def get_dependencies(self) -> List[str]:
        """Get final list of third-party dependencies"""
        imports = self.extract_imports()
        third_party = self.filter_stdlib(imports)
        resolved = {self.resolve_package_name(imp) for imp in third_party}
        return sorted(resolved)

    def generate_requirements_txt(self, output_path: Optional[str] = None) -> str:
        """Generate requirements.txt content"""
        dependencies = self.get_dependencies()

        if not dependencies:
            content = ""
        else:
            content = "\n".join(dependencies) + "\n"

        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)

        return content

    def analyze(self, output_dir: Optional[str] = None) -> Dict[str, any]:
        """Complete analysis pipeline"""
        self.load_code()
        self.parse_ast()
        dependencies = self.get_dependencies()

        requirements_path = None
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            requirements_path = output_path / "requirements.txt"

        requirements_content = self.generate_requirements_txt(
            str(requirements_path) if requirements_path else None
        )

        return {
            "dependencies": dependencies,
            "dependencies_count": len(dependencies),
            "requirements_txt_content": requirements_content,
            "requirements_txt_path": str(requirements_path) if requirements_path else None,
            "has_fastapi_app": self.has_fastapi_app(),
            "has_uvicorn_run": self.has_uvicorn_run(),
            "fastapi_app_name": self.get_fastapi_app_name()
        }

    def has_fastapi_app(self) -> bool:
        """Check if code instantiates FastAPI"""
        if not self.tree:
            self.parse_ast()

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name) and node.value.func.id == 'FastAPI':
                        return True
                    if isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'FastAPI':
                        return True
        return False

    def get_fastapi_app_name(self) -> Optional[str]:
        """Get the variable name of the FastAPI instance"""
        if not self.tree:
            self.parse_ast()

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    is_fastapi = False
                    if isinstance(node.value.func, ast.Name) and node.value.func.id == 'FastAPI':
                        is_fastapi = True
                    elif isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'FastAPI':
                        is_fastapi = True
                    
                    if is_fastapi:
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                return target.id
        return None

    def has_uvicorn_run(self) -> bool:
        """Check if code calls uvicorn.run"""
        if not self.tree:
            self.parse_ast()

        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == 'run' and isinstance(node.func.value, ast.Name) and node.func.value.id == 'uvicorn':
                        return True
        return False