import json
from typing import Dict, List, Optional
from pathlib import Path


class NotebookParser:
    """Parse Jupyter notebooks and extract code cells"""

    def __init__(self, notebook_path: str):
        """Initialize parser with notebook path"""
        self.notebook_path = Path(notebook_path)
        self.notebook_data: Optional[Dict] = None
        self.code_cells: List[str] = []

    def load_notebook(self) -> Dict:
        """Load and parse notebook JSON"""
        if not self.notebook_path.exists():
            raise FileNotFoundError(f"Notebook not found: {self.notebook_path}")

        with open(self.notebook_path, 'r', encoding='utf-8') as f:
            self.notebook_data = json.load(f)

        if not isinstance(self.notebook_data, dict):
            raise ValueError("Invalid notebook format")

        return self.notebook_data

    def extract_code_cells(self) -> List[str]:
        """Extract only executable code cells, filtering out markdown and outputs"""
        if not self.notebook_data:
            self.load_notebook()

        cells = self.notebook_data.get('cells', [])
        self.code_cells = []

        for cell in cells:
            cell_type = cell.get('cell_type')
            if cell_type == 'code':
                source = cell.get('source', [])
                if isinstance(source, list):
                    code = ''.join(source)
                else:
                    code = source

                if code.strip():
                    self.code_cells.append(code)

        return self.code_cells

    def generate_main_py(self, output_path: Optional[str] = None) -> str:
        """Generate a clean main.py from extracted code cells"""
        if not self.code_cells:
            self.extract_code_cells()

        if not self.code_cells:
            raise ValueError("No code cells found in notebook")

        main_content = self._build_main_content()

        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(main_content)

        return main_content

    def _build_main_content(self) -> str:
        """Build the main.py content from code cells"""
        sections = []

        for idx, cell_code in enumerate(self.code_cells, 1):
            cell_code = cell_code.rstrip()
            if cell_code:
                sections.append(f"# Cell {idx}\n{cell_code}")

        return "\n\n".join(sections) + "\n"

    def validate_syntax(self, code: str) -> bool:
        """Validate Python syntax"""
        try:
            compile(code, '<string>', 'exec')
            return True
        except SyntaxError:
            return False

    def get_notebook_metadata(self) -> Dict:
        """Extract notebook metadata"""
        if not self.notebook_data:
            self.load_notebook()

        return self.notebook_data.get('metadata', {})

    def parse(self, output_dir: Optional[str] = None) -> Dict[str, str]:
        """Complete parsing pipeline - load, extract, and generate"""
        self.load_notebook()
        self.extract_code_cells()

        main_py_path = None
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            main_py_path = output_path / "main.py"

        main_content = self.generate_main_py(str(main_py_path) if main_py_path else None)

        is_valid = self.validate_syntax(main_content)

        return {
            "main_py_content": main_content,
            "main_py_path": str(main_py_path) if main_py_path else None,
            "code_cells_count": len(self.code_cells),
            "syntax_valid": is_valid,
            "metadata": self.get_notebook_metadata()
        }