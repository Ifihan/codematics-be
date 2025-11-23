from pathlib import Path
import zipfile
import tempfile
import shutil
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import Notebook, Analysis, Deployment, ModelVersion, User
from app.core.code_generator import CodeGenerator
from app.core.dockerfile_generator import DockerfileGenerator
from app.config import settings
from app.core.storage import StorageService
from app.core.github_service import GitHubService

class ExportService:
    def __init__(self):
        self.code_gen = CodeGenerator()
        self.dockerfile_gen = DockerfileGenerator()
        self.storage = StorageService()

    def create_export_package(
        self,
        notebook: Notebook,
        analysis: Optional[Analysis] = None,
        deployment: Optional[Deployment] = None,
        db: Optional[Session] = None
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

            # Generate requirements.txt from dependencies list (ensures package mappings are applied)
            if notebook.dependencies:
                req_content = "\n".join(notebook.dependencies) + "\n"
                (export_dir / "requirements.txt").write_text(req_content)

            app_type = self.dockerfile_gen.detect_app_type(notebook.dependencies or [])

            has_model = False
            if db:
                active_model = db.query(ModelVersion).filter(
                    ModelVersion.notebook_id == notebook.id,
                    ModelVersion.is_active == True
                ).first()
                has_model = active_model is not None

            if app_type == "fastapi":
                cell_classifications = analysis.cell_classifications if analysis else []
                model_info = analysis.model_info if analysis and hasattr(analysis, 'model_info') else (analysis.get('model_info') if isinstance(analysis, dict) else {})
                app_wrapper = self.code_gen.generate_fastapi_wrapper(
                    notebook.name,
                    notebook.dependencies or [],
                    cell_classifications,
                    use_gcs_model=has_model,
                    model_info=model_info
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

    def push_to_github(
        self,
        notebook: Notebook,
        user: User,
        analysis: Optional[Analysis] = None,
        db: Optional[Session] = None,
        repo_name: Optional[str] = None,
        description: Optional[str] = None,
        private: bool = False
    ) -> Dict[str, Any]:
        if not user.github_token or not user.github_username:
            raise ValueError("GitHub not connected. User must authenticate with GitHub first.")

        github = GitHubService(user.github_token)

        if not repo_name:
            repo_name = f"{notebook.name.lower().replace(' ', '-')}-deployment"

        if not description:
            description = f"Deployment for {notebook.name} notebook"

        repo = github.create_repo(
            name=repo_name,
            description=description,
            private=private
        )

        owner = user.github_username
        files_to_upload = []

        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / notebook.name
            export_dir.mkdir(parents=True)

            if notebook.main_py_path and notebook.main_py_path.startswith("gs://"):
                blob_name = self.storage.parse_gcs_uri(notebook.main_py_path)
                self.storage.download_file(blob_name, str(export_dir / "main.py"))
                files_to_upload.append(("main.py", (export_dir / "main.py").read_text()))

            if notebook.dependencies:
                req_content = "\n".join(notebook.dependencies) + "\n"
                files_to_upload.append(("requirements.txt", req_content))

            app_type = self.dockerfile_gen.detect_app_type(notebook.dependencies or [])

            has_model = False
            if db:
                active_model = db.query(ModelVersion).filter(
                    ModelVersion.notebook_id == notebook.id,
                    ModelVersion.is_active == True
                ).first()
                has_model = active_model is not None

            if app_type == "fastapi":
                cell_classifications = analysis.cell_classifications if analysis else []
                model_info = analysis.model_info if analysis and hasattr(analysis, 'model_info') else (analysis.get('model_info') if isinstance(analysis, dict) else {})
                app_wrapper = self.code_gen.generate_fastapi_wrapper(
                    notebook.name,
                    notebook.dependencies or [],
                    cell_classifications,
                    use_gcs_model=has_model,
                    model_info=model_info
                )
                files_to_upload.append(("app.py", app_wrapper))

            analysis_dict = {
                "issues": analysis.issues if analysis else [],
                "health_score": analysis.health_score if analysis else 100
            }
            dockerfile_content = self.dockerfile_gen.generate(
                analysis_dict,
                notebook.dependencies or [],
                app_type
            )
            files_to_upload.append(("Dockerfile", dockerfile_content))

            gitignore = self.code_gen.generate_gitignore()
            files_to_upload.append((".gitignore", gitignore))

            workflow_content = f"""name: Deploy to Cloud Run

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - id: auth
        uses: google-github-actions/auth@v1
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v1

      - name: Build and Deploy
        run: |
          gcloud builds submit --tag {settings.gcp_artifact_registry}/{repo_name}
          gcloud run deploy {repo_name} \\
            --image {settings.gcp_artifact_registry}/{repo_name} \\
            --region {settings.gcp_region} \\
            --platform managed \\
            --allow-unauthenticated
"""
            files_to_upload.append((".github/workflows/deploy.yml", workflow_content))

        for file_path, content in files_to_upload:
            github.upload_file(owner, repo_name, file_path, content, f"Add {file_path}")

        webhook_url = f"{settings.github_redirect_uri.rsplit('/', 2)[0]}/webhooks/github"
        if settings.github_webhook_secret:
            github.create_webhook(owner, repo_name, webhook_url, settings.github_webhook_secret)

        return {
            "repo_url": repo["html_url"],
            "repo_name": repo_name,
            "owner": owner
        }
