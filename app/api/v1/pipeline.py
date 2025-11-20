from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pathlib import Path
import shutil
import logging
from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.db.models import User, Notebook, Build, Deployment
from app.utils.deps import get_current_active_user
from app.core.parser import NotebookParser
from app.core.dependencies import DependencyExtractor
from app.core.storage import StorageService
from app.core.cloud_build import CloudBuildService
from app.core.cloud_run import CloudRunService
from app.config import settings
from pydantic import BaseModel
import time

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    """One-click deployment request"""

    cpu: str = "1"
    memory: str = "512Mi"
    min_instances: int = 0
    max_instances: int = 10
    auto_deploy: bool = True


class PipelineStatus(BaseModel):
    """Pipeline execution status"""

    pipeline_id: str
    notebook_id: Optional[int]
    build_id: Optional[int]
    deployment_id: Optional[int]
    current_step: str
    status: str
    steps_completed: list
    error_message: Optional[str]


class PipelineResponse(BaseModel):
    """Pipeline response"""

    pipeline_id: str
    notebook_id: int
    status: str
    message: str


@router.post("/deploy", response_model=PipelineResponse)
async def one_click_deploy(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    cpu: str = "1",
    memory: str = "512Mi",
    min_instances: int = 0,
    max_instances: int = 10,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """One-click deploy: Upload notebook and automatically build & deploy"""

    if not file.filename.endswith(".ipynb"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .ipynb files are allowed",
        )

    user_dir = Path(f"uploads/user_{current_user.id}")
    user_dir.mkdir(parents=True, exist_ok=True)

    notebook_name = file.filename.replace(".ipynb", "")
    file_path = user_dir / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    notebook = Notebook(
        name=notebook_name,
        filename=file.filename,
        file_path=str(file_path),
        user_id=current_user.id,
        status="uploaded",
    )

    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    pipeline_id = f"pipeline-{notebook.id}-{int(datetime.utcnow().timestamp())}"

    background_tasks.add_task(
        execute_pipeline,
        notebook.id,
        pipeline_id,
        cpu,
        memory,
        min_instances,
        max_instances,
    )

    return PipelineResponse(
        pipeline_id=pipeline_id,
        notebook_id=notebook.id,
        status="processing",
        message="Pipeline started. Use /pipeline/status/{pipeline_id} to track progress.",
    )


def execute_pipeline(
    notebook_id: int,
    pipeline_id: str,
    cpu: str,
    memory: str,
    min_instances: int,
    max_instances: int,
):
    """Execute the complete deployment pipeline"""
    from app.db.database import SessionLocal

    db = SessionLocal()

    try:
        notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
        if not notebook:
            db.close()
            return

        steps_completed = []
        notebook.status = "parsing"
        db.commit()

        parser = NotebookParser(notebook.file_path)
        code_cells = parser.extract_code_cells()

        if not code_cells:
            raise Exception("No code cells found in notebook")

        notebook.code_cells_count = len(code_cells)

        notebook_dir = Path(notebook.file_path).parent
        main_py_path = notebook_dir / "main.py"
        parser.generate_main_py(str(main_py_path))
        notebook.main_py_path = str(main_py_path)

        steps_completed.append("parse")

        combined_code = "\n\n".join(code_cells)
        extractor = DependencyExtractor(code=combined_code)
        dependencies = extractor.get_dependencies()
        notebook.dependencies = dependencies

        requirements_path = notebook_dir / "requirements.txt"
        extractor.generate_requirements_txt(str(requirements_path))
        notebook.requirements_txt_path = str(requirements_path)

        # Detect app type and generate appropriate Procfile
        has_fastapi = "fastapi" in [dep.lower() for dep in dependencies]
        has_streamlit = "streamlit" in [dep.lower() for dep in dependencies]
        has_flask = "flask" in [dep.lower() for dep in dependencies]
        
        # Check if main.py has uvicorn.run or app startup code
        main_py_content = main_py_path.read_text(encoding='utf-8')
        has_uvicorn_run = "uvicorn.run" in main_py_content
        has_fastapi_app = "FastAPI()" in main_py_content or "= FastAPI(" in main_py_content
        
        procfile_path = notebook_dir / "Procfile"
        
        # Generate Dockerfile based on app type
        dockerfile_content = """
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
"""

        if has_fastapi:
            # FastAPI app
            if not has_uvicorn_run and has_fastapi_app:
                # Inject startup code
                startup_code = '''

# Auto-generated startup code
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
'''
                with open(main_py_path, 'a', encoding='utf-8') as f:
                    f.write(startup_code)
                
                # Ensure uvicorn is in dependencies
                if 'uvicorn' not in dependencies:
                    dependencies.append('uvicorn')
                    dependencies.sort()
                    notebook.dependencies = dependencies
                    with open(requirements_path, 'w', encoding='utf-8') as f:
                        f.write("\n".join(dependencies) + "\n")
            
            dockerfile_content += '\nCMD ["python", "main.py"]'
                
        elif has_flask:
            # Flask app
            dockerfile_content += '\nCMD ["python", "main.py"]'
                
        else:
            # Streamlit or Generic Python app
            # Default to Streamlit for generic notebooks
            
            # Ensure streamlit is in dependencies
            if 'streamlit' not in dependencies:
                dependencies.append('streamlit')
                dependencies.sort()
                notebook.dependencies = dependencies
                with open(requirements_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(dependencies) + "\n")
            
            dockerfile_content += '\nEXPOSE 8080\nCMD ["streamlit", "run", "main.py", "--server.port=8080", "--server.address=0.0.0.0"]'

        # Write Dockerfile
        dockerfile_path = notebook_dir / "Dockerfile"
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)

        notebook.status = "parsed"
        notebook.parsed_at = datetime.utcnow()
        db.commit()

        steps_completed.append("dependencies")

        image_name = f"{settings.gcp_artifact_registry}/{notebook.name}:latest"
        source_dir = Path(notebook.file_path).parent

        storage_service = StorageService()
        source_object = f"builds/notebook-{notebook_id}/source-{datetime.utcnow().timestamp()}.tar.gz"
        storage_service.upload_source(str(source_dir), source_object)

        steps_completed.append("upload")

        build = Build(
            notebook_id=notebook.id,
            build_id=f"build-{notebook.id}-{int(datetime.utcnow().timestamp())}",
            status="queued",
            image_name=image_name,
            source_bucket=settings.gcp_bucket_name,
            source_object=source_object,
        )

        db.add(build)
        db.commit()
        db.refresh(build)

        build.status = "building"
        build.started_at = datetime.utcnow()
        db.commit()

        cloud_build_service = CloudBuildService()
        build_result = cloud_build_service.trigger_build(
            source_bucket=build.source_bucket,
            source_object=build.source_object,
            image_name=build.image_name,
        )

        build.build_id = build_result.metadata.build.id
        build.log_url = f"https://console.cloud.google.com/cloud-build/builds/{build_result.metadata.build.id}?project={settings.gcp_project_id}"
        db.commit()

        while True:
            build_status = cloud_build_service.get_build(build_result.metadata.build.id)
            status_value = build_status.status

            if status_value == 3:
                build.status = "success"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            elif status_value in [4, 5, 6, 7]:
                build.status = "failed"
                build.error_message = f"Build failed with status {status_value}"
                build.finished_at = datetime.utcnow()
                db.commit()
                raise Exception(f"Build failed: {build.error_message}")
            else:
                time.sleep(5)

        steps_completed.append("build")

        service_name = f"notebook-{notebook.id}-{notebook.user_id}"

        deployment = Deployment(
            notebook_id=notebook.id,
            build_id=build.id,
            service_name=service_name,
            status="deploying",
            image_uri=build.image_name,
        )

        db.add(deployment)
        db.commit()
        db.refresh(deployment)

        cloud_run_service = CloudRunService()
        service = cloud_run_service.create_or_update_service(
            service_name=deployment.service_name,
            image_uri=deployment.image_uri,
            env_vars={},
            cpu=cpu,
            memory=memory,
            min_instances=min_instances,
            max_instances=max_instances,
            allow_unauthenticated=True,
        )

        cloud_run_service.set_iam_policy(deployment.service_name, allow_public=True)

        deployment.status = "deployed"
        deployment.service_url = service.uri
        deployment.revision_name = (
            service.latest_created_revision
            if hasattr(service, "latest_created_revision")
            else None
        )
        deployment.deployed_at = datetime.utcnow()
        db.commit()

        steps_completed.append("deploy")

        notebook.status = "deployed"
        db.commit()

    except Exception as e:
        logger.error(f"Pipeline {pipeline_id} failed: {str(e)}", exc_info=True)

        notebook.status = "failed"
        db.commit()

        if "build" in locals():
            build.status = "failed"
            build.error_message = str(e)
            build.finished_at = datetime.utcnow()
            db.commit()

        if "deployment" in locals():
            deployment.status = "failed"
            deployment.error_message = str(e)
            db.commit()

    finally:
        db.close()


@router.get("/status/{pipeline_id}")
def get_pipeline_status(
    pipeline_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get pipeline execution status"""

    parts = pipeline_id.split("-")
    if len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pipeline ID"
        )

    try:
        notebook_id = int(parts[1])
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pipeline ID format"
        )

    notebook = (
        db.query(Notebook)
        .filter(Notebook.id == notebook_id, Notebook.user_id == current_user.id)
        .first()
    )

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found"
        )

    build = (
        db.query(Build)
        .filter(Build.notebook_id == notebook_id)
        .order_by(Build.created_at.desc())
        .first()
    )
    deployment = (
        db.query(Deployment)
        .filter(Deployment.notebook_id == notebook_id)
        .order_by(Deployment.created_at.desc())
        .first()
    )

    steps_completed = []
    current_step = "upload"
    overall_status = "processing"
    error_message = None

    if notebook.status in ["parsed", "building", "deploying", "deployed"]:
        steps_completed.append("parse")
        steps_completed.append("dependencies")

    if build:
        steps_completed.append("upload")

        if build.status == "building":
            current_step = "build"
        elif build.status == "success":
            steps_completed.append("build")
            current_step = "deploy"
        elif build.status == "failed":
            current_step = "build"
            overall_status = "failed"
            error_message = build.error_message

    if deployment:
        if deployment.status == "deploying":
            current_step = "deploy"
        elif deployment.status == "deployed":
            steps_completed.append("deploy")
            current_step = "completed"
            overall_status = "deployed"
        elif deployment.status == "failed":
            current_step = "deploy"
            overall_status = "failed"
            error_message = deployment.error_message

    return {
        "pipeline_id": pipeline_id,
        "notebook_id": notebook.id,
        "build_id": build.id if build else None,
        "deployment_id": deployment.id if deployment else None,
        "current_step": current_step,
        "status": overall_status,
        "steps_completed": steps_completed,
        "error_message": error_message,
        "notebook_status": notebook.status,
        "build_status": build.status if build else None,
        "deployment_status": deployment.status if deployment else None,
        "service_url": (
            deployment.service_url
            if deployment and deployment.status == "deployed"
            else None
        ),
    }


@router.get("/history")
def get_pipeline_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get pipeline execution history"""

    notebooks = (
        db.query(Notebook)
        .filter(Notebook.user_id == current_user.id)
        .order_by(Notebook.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    history = []
    for notebook in notebooks:
        build = (
            db.query(Build)
            .filter(Build.notebook_id == notebook.id)
            .order_by(Build.created_at.desc())
            .first()
        )
        deployment = (
            db.query(Deployment)
            .filter(Deployment.notebook_id == notebook.id)
            .order_by(Deployment.created_at.desc())
            .first()
        )

        history.append(
            {
                "notebook_id": notebook.id,
                "notebook_name": notebook.name,
                "notebook_status": notebook.status,
                "build_id": build.id if build else None,
                "build_status": build.status if build else None,
                "deployment_id": deployment.id if deployment else None,
                "deployment_status": deployment.status if deployment else None,
                "service_url": (
                    deployment.service_url
                    if deployment and deployment.status == "deployed"
                    else None
                ),
                "created_at": notebook.created_at,
            }
        )

    return {"total": len(history), "pipelines": history}
