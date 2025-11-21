from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.database import get_db, SessionLocal
from app.db.models import Deployment, Notebook, Analysis, User, DeploymentMetric
from app.schemas.deployment import DeploymentCreate, DeploymentResponse
from app.utils.deps import get_current_active_user
from app.core.storage import StorageService
from app.core.cloud_build import CloudBuildService
from app.core.cloud_run import CloudRunService
from app.core.dockerfile_generator import DockerfileGenerator
from app.core.export_service import ExportService
from app.core.logging_service import LoggingService
from app.core.monitoring import MonitoringService
from app.config import settings
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
import os
import time
import tarfile

router = APIRouter(prefix="/deployments", tags=["deployments"])

storage = StorageService()
cloud_build = CloudBuildService()
cloud_run = CloudRunService()
dockerfile_gen = DockerfileGenerator()
export_service = ExportService()


def process_deployment(deployment_id: int, db_url: str):
    db = SessionLocal()
    logger = LoggingService()
    monitoring = MonitoringService()
    start_time = time.time()

    try:
        deployment = db.query(Deployment).filter_by(id=deployment_id).first()
        if not deployment:
            return

        notebook = db.query(Notebook).filter_by(id=deployment.notebook_id).first()
        analysis = (
            db.query(Analysis).filter_by(notebook_id=deployment.notebook_id).first()
        )

        logger.log_deployment_start(deployment.id, notebook.id, deployment.user_id)

        deployment.status = "building"
        db.commit()

        with tempfile.TemporaryDirectory() as tmpdir:
            if notebook.main_py_path.startswith("gs://"):
                main_blob = notebook.main_py_path.replace(f"gs://{settings.gcp_bucket_name}/", "")
                storage.download_file(main_blob, str(Path(tmpdir) / "main.py"))
            else:
                shutil.copy(notebook.main_py_path, Path(tmpdir) / "main.py")

            if notebook.requirements_txt_path.startswith("gs://"):
                req_blob = notebook.requirements_txt_path.replace(f"gs://{settings.gcp_bucket_name}/", "")
                storage.download_file(req_blob, str(Path(tmpdir) / "requirements.txt"))
            else:
                shutil.copy(notebook.requirements_txt_path, Path(tmpdir) / "requirements.txt")

            app_type = dockerfile_gen.detect_app_type(notebook.dependencies or [])
            analysis_dict = {
                "issues": analysis.issues if analysis else [],
                "health_score": analysis.health_score if analysis else 100,
            }
            dockerfile_content = dockerfile_gen.generate(
                analysis_dict, notebook.dependencies or [], app_type
            )

            dockerfile_path = Path(tmpdir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            for file_path in Path(tmpdir).iterdir():
                blob_name = f"deployments/{deployment.id}/{file_path.name}"
                storage.upload_file(str(file_path), blob_name)

            source_uri = f"gs://{settings.gcp_bucket_name}/deployments/{deployment.id}/source.tar.gz"

            tar_path = Path(tmpdir) / "source.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                for file in Path(tmpdir).iterdir():
                    if file.name != "source.tar.gz":
                        tar.add(file, arcname=file.name)

            storage.upload_file(
                str(tar_path), f"deployments/{deployment.id}/source.tar.gz"
            )

        image_name = f"{settings.gcp_artifact_registry}/{deployment.name}:latest"

        build_start_time = time.time()
        build_id = cloud_build.submit_build(source_uri, image_name)
        logger.log_build_start(build_id, deployment.id)

        deployment.build_id = build_id
        deployment.image_url = image_name
        deployment.build_logs_url = cloud_build.get_build_logs(build_id)
        deployment.status = "deploying"
        db.commit()

        max_wait = 600
        waited = 0
        while waited < max_wait:
            build_status = cloud_build.get_build_status(build_id)
            if build_status == "SUCCESS":
                break
            elif build_status in ["FAILURE", "CANCELLED", "TIMEOUT"]:
                build_duration = int(time.time() - build_start_time)
                deployment.build_duration = build_duration
                deployment.status = "failed"
                deployment.error_message = f"Build failed with status: {build_status}"
                db.commit()
                logger.log_build_complete(build_id, build_status, build_duration)
                logger.log_deployment_failure(
                    deployment.id, deployment.error_message, "build"
                )

                total_duration = time.time() - start_time
                monitoring.track_deployment("failed", total_duration)
                return
            time.sleep(10)
            waited += 10

        if waited >= max_wait:
            deployment.status = "failed"
            deployment.error_message = "Build timeout"
            db.commit()
            logger.log_deployment_failure(deployment.id, "Build timeout", "build")

            total_duration = time.time() - start_time
            monitoring.track_deployment("failed", total_duration)
            return

        build_duration = int(time.time() - build_start_time)
        deployment.build_duration = build_duration
        logger.log_build_complete(build_id, "SUCCESS", build_duration)

        service = cloud_run.deploy_service(
            service_name=deployment.name, image_uri=image_name, port=8080
        )

        deployment.service_url = cloud_run.get_service_url(deployment.name)
        deployment.status = "deployed"
        deployment.deployed_at = datetime.utcnow()
        db.commit()

        total_duration = time.time() - start_time
        logger.log_deployment_success(
            deployment.id, deployment.service_url, total_duration
        )

        monitoring.track_deployment("success", total_duration)

        metric = DeploymentMetric(
            deployment_id=deployment.id,
            metric_type="deployment_success",
            value={
                "total_duration": total_duration,
                "build_duration": build_duration,
                "deploy_duration": total_duration - build_duration,
            },
        )
        db.add(metric)
        db.commit()

    except Exception as e:
        deployment.status = "failed"
        deployment.error_message = str(e)
        db.commit()
        logger.log_deployment_failure(deployment.id, str(e), "unknown")
        logger.log_error("deployment_error", str(e), {"deployment_id": deployment.id})

        total_duration = time.time() - start_time
        monitoring.track_deployment("failed", total_duration)
    finally:
        db.close()


@router.post(
    "/one-click", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED
)
def create_one_click_deployment(
    deployment: DeploymentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    notebook = (
        db.query(Notebook)
        .filter_by(id=deployment.notebook_id, user_id=current_user.id)
        .first()
    )
    if not notebook:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")

    if notebook.status != "analyzed":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Notebook must be analyzed before deployment"
        )

    region = deployment.region or settings.gcp_region

    new_deployment = Deployment(
        notebook_id=deployment.notebook_id,
        user_id=current_user.id,
        name=deployment.name,
        region=region,
        status="pending",
    )
    db.add(new_deployment)
    db.commit()
    db.refresh(new_deployment)

    background_tasks.add_task(
        process_deployment, new_deployment.id, settings.database_url
    )

    return new_deployment


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deployment = (
        db.query(Deployment)
        .filter_by(id=deployment_id, user_id=current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")
    return deployment


@router.get("/", response_model=list[DeploymentResponse])
def list_deployments(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    deployments = (
        db.query(Deployment)
        .filter_by(user_id=current_user.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return deployments


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deployment = (
        db.query(Deployment)
        .filter_by(id=deployment_id, user_id=current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")

    if deployment.service_url:
        try:
            cloud_run.delete_service(deployment.name)
        except Exception:
            pass

    db.delete(deployment)
    db.commit()


@router.get("/{deployment_id}/download")
def download_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deployment = (
        db.query(Deployment)
        .filter_by(id=deployment_id, user_id=current_user.id)
        .first()
    )
    if not deployment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Deployment not found")

    notebook = db.query(Notebook).filter_by(id=deployment.notebook_id).first()
    analysis = db.query(Analysis).filter_by(notebook_id=deployment.notebook_id).first()

    zip_path = export_service.create_export_package(notebook, analysis, deployment)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{notebook.name}-deployment.zip",
    )
