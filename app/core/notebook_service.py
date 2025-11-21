from pathlib import Path
from datetime import datetime
import shutil

from sqlalchemy.orm import Session
from app.core.parser import NotebookParser
from app.core.dependencies import DependencyExtractor
from app.db.models import Notebook


class NotebookService:
    """Service for notebook processing operations"""

    def __init__(self, storage_base: str = "storage/notebooks"):
        self.storage_base = Path(storage_base)
        self.storage_base.mkdir(parents=True, exist_ok=True)

    def _get_notebook_dir(self, user_id: int, notebook_id: int) -> Path:
        """Get notebook storage directory"""
        path = self.storage_base / str(user_id) / str(notebook_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_uploaded_file(self, content: bytes, filename: str, user_id: int, notebook_id: int) -> str:
        """Save uploaded notebook file"""
        file_path = self._get_notebook_dir(user_id, notebook_id) / filename
        file_path.write_bytes(content)
        return str(file_path)

    def parse_notebook(self, notebook: Notebook, db: Session) -> dict:
        """Parse notebook and extract dependencies"""
        output_dir = Path(notebook.file_path).parent

        # Parse notebook
        parse_result = NotebookParser(notebook.file_path).parse(str(output_dir))

        # Extract dependencies
        deps_result = DependencyExtractor(file_path=parse_result['main_py_path']).analyze(str(output_dir))

        # Auto-inject uvicorn startup for FastAPI apps
        if deps_result['has_fastapi_app'] and not deps_result['has_uvicorn_run']:
            app_name = deps_result['fastapi_app_name'] or 'app'
            startup_code = f'''

# Auto-generated startup code
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8080))
    uvicorn.run({app_name}, host="0.0.0.0", port=port)
'''
            # Append startup code
            main_py = Path(parse_result['main_py_path'])
            main_py.write_text(main_py.read_text() + startup_code)

            # Add uvicorn to dependencies
            if 'uvicorn' not in deps_result['dependencies']:
                deps_result['dependencies'].append('uvicorn')
                deps_result['dependencies'].sort()

                # Update requirements.txt
                req_path = Path(deps_result['requirements_txt_path'])
                req_path.write_text("\n".join(deps_result['dependencies']) + "\n")

        # Generate Procfile
        (output_dir / "Procfile").write_text("web: python main.py")

        # Update notebook record
        notebook.status = "parsed"
        notebook.main_py_path = parse_result['main_py_path']
        notebook.requirements_txt_path = deps_result['requirements_txt_path']
        notebook.dependencies = deps_result['dependencies']
        notebook.code_cells_count = parse_result['code_cells_count']
        notebook.syntax_valid = parse_result['syntax_valid']
        notebook.parsed_at = datetime.utcnow()
        db.commit()
        db.refresh(notebook)

        return {"parse_result": parse_result, "deps_result": deps_result, "notebook": notebook}

    def delete_notebook_files(self, notebook: Notebook):
        """Delete all files associated with notebook"""
        notebook_dir = Path(notebook.file_path).parent
        if notebook_dir.exists():
            shutil.rmtree(notebook_dir)
