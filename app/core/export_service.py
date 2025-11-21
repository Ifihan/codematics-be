from pathlib import Path
import zipfile
import tempfile
import shutil
from typing import Optional
from app.db.models import Notebook, Analysis, Deployment
from app.core.code_generator import CodeGenerator
from app.core.dockerfile_generator import DockerfileGenerator
from app.config import settings


from app.core.storage import StorageService

class ExportService:
    def __init__(self):
        self.code_gen = CodeGenerator()
        self.dockerfile_gen = DockerfileGenerator()
        self.storage = StorageService()

    def create_export_package(
        self,
        notebook: Notebook,
        analysis: Optional[Analysis] = None,
        deployment: Optional[Deployment] = None
    ) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / notebook.name

            export_dir.mkdir(parents=True)

            # Handle main.py (GCS or local)
            if notebook.main_py_path and notebook.main_py_path.startswith("gs://"):
                blob_name = self.storage.parse_gcs_uri(notebook.main_py_path)
                self.storage.download_file(blob_name, str(export_dir / "main.py"))
            elif notebook.main_py_path and Path(notebook.main_py_path).exists():
                shutil.copy(notebook.main_py_path, export_dir / "main.py")

            # Handle requirements.txt (GCS or local)
            if notebook.requirements_txt_path and notebook.requirements_txt_path.startswith("gs://"):
                blob_name = self.storage.parse_gcs_uri(notebook.requirements_txt_path)
                self.storage.download_file(blob_name, str(export_dir / "requirements.txt"))
            elif notebook.requirements_txt_path and Path(notebook.requirements_txt_path).exists():
                shutil.copy(notebook.requirements_txt_path, export_dir / "requirements.txt")

            app_type = self.dockerfile_gen.detect_app_type(notebook.dependencies or [])

            if app_type == "fastapi":
                cell_classifications = analysis.cell_classifications if analysis else []
                app_wrapper = self.code_gen.generate_fastapi_wrapper(
                    notebook.name,
                    notebook.dependencies or [],
                    cell_classifications
                )
                (export_dir / "app.py").write_text(app_wrapper)
            elif app_type == "streamlit":
                app_wrapper = self.code_gen.generate_streamlit_wrapper(notebook.name)
                (export_dir / "app.py").write_text(app_wrapper)

            analysis_dict = {
                "issues": analysis.issues if analysis else [],
                "health_score": analysis.health_score if analysis else 100
            }
            dockerfile_content = self.dockerfile_gen.generate(
                analysis_dict,
                notebook.dependencies or [],
                app_type
            )
            (export_dir / "Dockerfile").write_text(dockerfile_content)

            service_url = deployment.service_url if deployment else None
            readme = self.code_gen.generate_readme(
                notebook.name,
                notebook.dependencies or [],
                app_type,
                service_url
            )
            (export_dir / "README.md").write_text(readme)

            docker_compose = self.code_gen.generate_docker_compose(notebook.name, app_type)
            (export_dir / "docker-compose.yml").write_text(docker_compose)

            deploy_script = self.code_gen.generate_deploy_script(
                notebook.name,
                settings.gcp_project_id,
                settings.gcp_region,
                settings.gcp_artifact_registry
            )
            deploy_path = export_dir / "deploy.sh"
            deploy_path.write_text(deploy_script)
            deploy_path.chmod(0o755)

            gitignore = self.code_gen.generate_gitignore()
            (export_dir / ".gitignore").write_text(gitignore)

            test_file = self.code_gen.generate_test_file(notebook.name, app_type)
            (export_dir / "test_app.py").write_text(test_file)

            zip_path = Path(tempfile.gettempdir()) / f"{notebook.name}.zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in export_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(export_dir.parent)
                        zipf.write(file_path, arcname)

            return str(zip_path)
