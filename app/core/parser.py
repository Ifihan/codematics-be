import json
from pathlib import Path
from typing import Dict, List


class NotebookParser:
    """Parse Jupyter notebooks and extract code cells"""

    def __init__(self, notebook_path: str):
        self.notebook_path = Path(notebook_path)

    def parse(self, output_dir: str = None) -> Dict:
        """Parse notebook and generate main.py"""
        # Load notebook
        with open(self.notebook_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract code cells
        code_cells = []
        for cell in data.get('cells', []):
            if cell.get('cell_type') == 'code':
                source = cell.get('source', [])
                code = ''.join(source) if isinstance(source, list) else source
                if code.strip():
                    code_cells.append(code)

        if not code_cells:
            raise ValueError("No code cells found in notebook")

        # Build main.py content
        sections = [f"# Cell {i}\n{cell.rstrip()}" for i, cell in enumerate(code_cells, 1)]
        main_content = "\n\n".join(sections) + "\n"

        # Validate syntax
        try:
            compile(main_content, '<string>', 'exec')
            is_valid = True
        except SyntaxError:
            is_valid = False

        # Write to file if output_dir specified
        main_py_path = None
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            main_py_path = output_path / "main.py"
            main_py_path.write_text(main_content, encoding='utf-8')

        return {
            "main_py_content": main_content,
            "main_py_path": str(main_py_path) if main_py_path else None,
            "code_cells_count": len(code_cells),
            "syntax_valid": is_valid,
            "metadata": data.get('metadata', {})
        }