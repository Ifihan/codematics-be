from pathlib import Path
from datetime import datetime
import shutil
import tempfile
import os

from sqlalchemy.orm import Session
from app.core.parser import NotebookParser
from app.core.dependencies import DependencyExtractor
from app.db.models import Notebook
from app.core.storage import StorageService
from app.core.gemini import GeminiService


class NotebookService:
    """Service for notebook processing operations"""

    def __init__(self):
        self.storage = StorageService()
        self.gemini = GeminiService()

    def save_uploaded_file(self, content: bytes, filename: str, user_id: int, notebook_id: int) -> str:
        """Save uploaded notebook file to GCS"""
        blob_name = f"notebooks/{user_id}/{notebook_id}/{filename}"
        return self.storage.upload_from_bytes(content, blob_name, content_type="application/json")

    def parse_notebook(self, notebook: Notebook, db: Session) -> dict:
        """Parse notebook and extract dependencies"""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Handle GCS file path
            if notebook.file_path.startswith("gs://"):
                blob_name = self.storage.parse_gcs_uri(notebook.file_path)
                local_notebook_path = tmp_path / notebook.filename
                self.storage.download_file(blob_name, str(local_notebook_path))
            else:
                # Fallback for legacy local files
                local_notebook_path = Path(notebook.file_path)
                if not local_notebook_path.exists():
                    raise FileNotFoundError(f"Notebook file not found: {notebook.file_path}")

            # Parse notebook
            parse_result = NotebookParser(str(local_notebook_path)).parse(str(tmp_path))

            # Extract dependencies
            deps_result = DependencyExtractor(file_path=parse_result['main_py_path']).analyze(str(tmp_path))

            # Analyze with Gemini and Generate FastAPI App if model detected
            try:
                notebook_content = parse_result['main_py_content']
                dependencies = deps_result['dependencies']
                
                analysis = self.gemini.analyze_notebook(notebook_content, dependencies)
                
                if analysis['model_info']['has_model']:
                    generated_code = self.gemini.generate_fastapi_app(notebook_content, analysis['model_info'])
                    
                    # Overwrite main.py with generated FastAPI app
                    main_py_path = Path(parse_result['main_py_path'])
                    main_py_path.write_text(generated_code)
                    
                    # Re-analyze dependencies for the new app
                    deps_result = DependencyExtractor(file_path=str(main_py_path)).analyze(str(tmp_path))
                    
                    # Update parse result content
                    parse_result['main_py_content'] = generated_code
            except Exception as e:
                print(f"Gemini generation failed: {e}")
                # Fallback to original parsing if generation fails
                pass

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
            (tmp_path / "Procfile").write_text("web: python main.py")

            # Upload generated files to GCS
            user_id = notebook.user_id
            nb_id = notebook.id
            
            main_py_blob = f"notebooks/{user_id}/{nb_id}/main.py"
            req_txt_blob = f"notebooks/{user_id}/{nb_id}/requirements.txt"
            
            main_py_gcs = self.storage.upload_file(parse_result['main_py_path'], main_py_blob)
            req_txt_gcs = self.storage.upload_file(deps_result['requirements_txt_path'], req_txt_blob)

            # Update notebook record
            notebook.status = "parsed"
            notebook.main_py_path = main_py_gcs
            notebook.requirements_txt_path = req_txt_gcs
            notebook.dependencies = deps_result['dependencies']
            notebook.code_cells_count = parse_result['code_cells_count']
            notebook.syntax_valid = parse_result['syntax_valid']
            notebook.parsed_at = datetime.utcnow()
            db.commit()
            db.refresh(notebook)

            # Update result paths to GCS for consistency
            parse_result['main_py_path'] = main_py_gcs
            deps_result['requirements_txt_path'] = req_txt_gcs

            return {"parse_result": parse_result, "deps_result": deps_result, "notebook": notebook}

    def delete_notebook_files(self, notebook: Notebook):
        """Delete all files associated with notebook from GCS"""
        # Helper to delete if GCS URI
        def delete_if_gcs(path):
            if path and path.startswith("gs://"):
                try:
                    blob_name = self.storage.parse_gcs_uri(path)
                    self.storage.delete_blob(blob_name)
                except Exception:
                    pass # Ignore if already deleted or not found

        delete_if_gcs(notebook.file_path)
        delete_if_gcs(notebook.main_py_path)
        delete_if_gcs(notebook.requirements_txt_path)
