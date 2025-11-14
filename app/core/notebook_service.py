from pathlib import Path
from datetime import datetime
from typing import Optional
import shutil
from app.core.parser import NotebookParser
from app.core.dependencies import DependencyExtractor
from app.db.models import Notebook
from sqlalchemy.orm import Session


class NotebookService:
    """Service for notebook processing operations"""

    def __init__(self, storage_base_path: str = "storage/notebooks"):
        """Initialize with storage base path"""
        self.storage_base_path = Path(storage_base_path)
        self.storage_base_path.mkdir(parents=True, exist_ok=True)

    def get_user_storage_path(self, user_id: int) -> Path:
        """Get storage path for a specific user"""
        path = self.storage_base_path / str(user_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_notebook_storage_path(self, user_id: int, notebook_id: int) -> Path:
        """Get storage path for a specific notebook"""
        path = self.get_user_storage_path(user_id) / str(notebook_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_uploaded_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: int,
        notebook_id: int
    ) -> str:
        """Save uploaded notebook file"""
        storage_path = self.get_notebook_storage_path(user_id, notebook_id)
        file_path = storage_path / filename

        with open(file_path, 'wb') as f:
            f.write(file_content)

        return str(file_path)

    def parse_notebook(self, notebook: Notebook, db: Session) -> dict:
        """Parse notebook and extract dependencies"""
        notebook_path = notebook.file_path
        output_dir = Path(notebook.file_path).parent

        parser = NotebookParser(notebook_path)
        parse_result = parser.parse(str(output_dir))

        extractor = DependencyExtractor(file_path=parse_result['main_py_path'])
        deps_result = extractor.analyze(str(output_dir))

        notebook.status = "parsed"
        notebook.main_py_path = parse_result['main_py_path']
        notebook.requirements_txt_path = deps_result['requirements_txt_path']
        notebook.dependencies = deps_result['dependencies']
        notebook.code_cells_count = parse_result['code_cells_count']
        notebook.syntax_valid = parse_result['syntax_valid']
        notebook.parsed_at = datetime.utcnow()

        db.commit()
        db.refresh(notebook)

        return {
            "parse_result": parse_result,
            "deps_result": deps_result,
            "notebook": notebook
        }

    def get_file_content(self, file_path: str) -> Optional[bytes]:
        """Read file content as bytes"""
        path = Path(file_path)
        if not path.exists():
            return None

        with open(path, 'rb') as f:
            return f.read()

    def delete_notebook_files(self, notebook: Notebook):
        """Delete all files associated with a notebook"""
        notebook_dir = Path(notebook.file_path).parent
        if notebook_dir.exists():
            shutil.rmtree(notebook_dir)