from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, WebSocket, WebSocketDisconnect
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
from app.db.models import ModelVersion
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
import os
import time
import tarfile
import secrets
import requests
import asyncio
import json

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

            if notebook.dependencies:
                req_content = "\n".join(notebook.dependencies) + "\n"
                Path(tmpdir, "requirements.txt").write_text(req_content)

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

        env_vars = {}
        active_model = db.query(ModelVersion).filter(
            ModelVersion.notebook_id == notebook.id,
            ModelVersion.is_active == True
        ).first()

        if active_model:
            admin_api_key = secrets.token_urlsafe(32)
            deployment.admin_api_key = admin_api_key
            env_vars = {
                "GCS_BUCKET": settings.gcp_bucket_name,
                "MODEL_GCS_PATH": active_model.gcs_path.replace(f"gs://{settings.gcp_bucket_name}/", ""),
                "MODEL_FILE_EXTENSION": active_model.file_extension or "pkl",
                "ADMIN_API_KEY": admin_api_key,
                "GCP_PROJECT_ID": settings.gcp_project_id
            }

        service = cloud_run.deploy_service(
            service_name=deployment.name,
            image_uri=image_name,
            port=8080,
            env_vars=env_vars if env_vars else None
        )

        base_service_url = cloud_run.get_service_url(deployment.name)
        deployment.service_url = f"{base_service_url}/docs"
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


@router.post("/{deployment_id}/reload-model")
def reload_model(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()
    if not deployment:
        raise HTTPException(404, "Deployment not found")

    if not deployment.service_url or deployment.status != "deployed":
        raise HTTPException(400, "Deployment not active")

    notebook = db.query(Notebook).filter_by(id=deployment.notebook_id).first()
    active_model = db.query(ModelVersion).filter(
        ModelVersion.notebook_id == notebook.id,
        ModelVersion.is_active == True
    ).first()

    if not active_model:
        raise HTTPException(404, "No active model version found")

    if not deployment.admin_api_key:
        raise HTTPException(500, "Admin API key not configured")

    # Update Cloud Run environment variables with new model info
    try:
        env_vars = {
            "GCS_BUCKET": settings.gcp_bucket_name,
            "MODEL_GCS_PATH": active_model.gcs_path.replace(f"gs://{settings.gcp_bucket_name}/", ""),
            "MODEL_FILE_EXTENSION": active_model.file_extension or "pkl",
            "ADMIN_API_KEY": deployment.admin_api_key,
            "GCP_PROJECT_ID": settings.gcp_project_id
        }

        cloud_run.update_service(
            service_name=deployment.name,
            image_uri=deployment.image_url,
            env_vars=env_vars
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to update Cloud Run environment: {str(e)}")

    # Now reload the model in the running container
    # Extract base URL (remove /docs suffix if present)
    base_url = deployment.service_url
    if base_url.endswith("/docs"):
        base_url = base_url[:-5]  # Remove the last 5 characters ("/docs")
    reload_url = f"{base_url}/admin/reload-model"
    headers = {"X-API-Key": deployment.admin_api_key}

    for attempt in range(3):
        try:
            response = requests.post(reload_url, headers=headers, timeout=30)
            if response.status_code == 200:
                return {
                    "status": "success",
                    "message": "Model reloaded with updated environment",
                    "version": active_model.version,
                    "model_path": active_model.gcs_path,
                    "file_extension": active_model.file_extension,
                    "timestamp": response.json().get("timestamp")
                }
            elif response.status_code == 401:
                raise HTTPException(401, "Invalid admin API key")
        except requests.RequestException as e:
            if attempt == 2:
                raise HTTPException(503, f"Failed to reload model: {str(e)}")
            time.sleep(2)

    raise HTTPException(503, "Model reload failed after 3 attempts")


@router.get("/{deployment_id}/logs")
def get_deployment_logs(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get build logs for a deployment (REST endpoint).

    Returns the complete log as text or JSON entries.
    """
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()

    if not deployment:
        raise HTTPException(404, "Deployment not found")

    if not deployment.build_id:
        raise HTTPException(400, "No build associated with this deployment")

    # Fetch log entries
    log_entries = cloud_build.fetch_build_log_entries(deployment.build_id)

    return {
        "deployment_id": deployment.id,
        "build_id": deployment.build_id,
        "status": deployment.status,
        "build_status": cloud_build.get_build_status(deployment.build_id) if deployment.build_id else None,
        "log_entries": log_entries,
        "total_entries": len(log_entries)
    }


@router.get("/{deployment_id}/logs/text")
def get_deployment_logs_text(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get build logs as plain text.

    Returns logs formatted as a text file.
    """
    deployment = db.query(Deployment).filter(
        Deployment.id == deployment_id,
        Deployment.user_id == current_user.id
    ).first()

    if not deployment:
        raise HTTPException(404, "Deployment not found")

    if not deployment.build_id:
        raise HTTPException(400, "No build associated with this deployment")

    log_text = cloud_build.fetch_build_log_text(deployment.build_id)

    return {
        "deployment_id": deployment.id,
        "build_id": deployment.build_id,
        "status": deployment.status,
        "logs": log_text
    }


@router.websocket("/{deployment_id}/logs/stream")
async def stream_logs(
    websocket: WebSocket,
    deployment_id: int,
    db: Session = Depends(get_db)
):
    """
    Stream build logs via WebSocket in real-time.

    Sends log entries as they become available during the build.

    Note: This endpoint does not require authentication as the deployment_id
    acts as a unique identifier. For production, consider adding token-based auth.
    """
    await websocket.accept()

    try:
        # Verify deployment exists
        deployment = db.query(Deployment).filter_by(id=deployment_id).first()
        if not deployment:
            await websocket.send_json({
                "type": "error",
                "message": "Deployment not found"
            })
            await websocket.close()
            return

        if not deployment.build_id:
            await websocket.send_json({
                "type": "error",
                "message": "Build ID not found. Build may not have started yet."
            })
            await websocket.close()
            return

        # Send initial connection success message
        await websocket.send_json({
            "type": "connected",
            "deployment_id": deployment.id,
            "build_id": deployment.build_id,
            "deployment_status": deployment.status,
            "message": "WebSocket connected. Streaming logs..."
        })

        last_log_count = 0
        max_iterations = 200  # Prevent infinite loops (200 * 3s = 10 minutes max)
        iteration = 0

        # Stream logs until build completes OR deployment finishes
        while iteration < max_iterations:
            try:
                iteration += 1

                # Get current build status from GCP
                build_status = cloud_build.get_build_status(deployment.build_id)

                # Fetch new log entries from Cloud Logging
                log_entries = cloud_build.fetch_build_log_entries(deployment.build_id, page_size=200)

                # Send only new logs since last check
                if len(log_entries) > last_log_count:
                    new_entries = log_entries[last_log_count:]
                    for entry in new_entries:
                        await websocket.send_json({
                            "type": "log",
                            "timestamp": entry.get("timestamp"),
                            "severity": entry.get("severity"),
                            "message": entry.get("message")
                        })
                    last_log_count = len(log_entries)
                elif iteration == 1 and len(log_entries) == 0:
                    # First iteration and no logs yet
                    await websocket.send_json({
                        "type": "info",
                        "message": "Waiting for logs... Cloud Logging may have a slight delay (10-30 seconds)."
                    })

                # Refresh deployment status from database
                db.refresh(deployment)

                # Send status update
                await websocket.send_json({
                    "type": "status",
                    "deployment_status": deployment.status,
                    "build_status": build_status,
                    "total_logs": last_log_count
                })

                # Check if build is complete
                if build_status in ["SUCCESS", "FAILURE", "CANCELLED", "TIMEOUT"]:
                    # Wait a bit for final logs to propagate to Cloud Logging
                    await asyncio.sleep(2)

                    # Fetch final logs one more time
                    final_logs = cloud_build.fetch_build_log_entries(deployment.build_id, page_size=200)
                    if len(final_logs) > last_log_count:
                        final_new = final_logs[last_log_count:]
                        for entry in final_new:
                            await websocket.send_json({
                                "type": "log",
                                "timestamp": entry.get("timestamp"),
                                "severity": entry.get("severity"),
                                "message": entry.get("message")
                            })

                    await websocket.send_json({
                        "type": "complete",
                        "build_status": build_status,
                        "deployment_status": deployment.status,
                        "total_logs": len(final_logs),
                        "message": f"Build {build_status.lower()}. Stream complete."
                    })
                    break

                # Also check if deployment reached a terminal state
                if deployment.status in ["deployed", "failed"]:
                    await websocket.send_json({
                        "type": "complete",
                        "build_status": build_status,
                        "deployment_status": deployment.status,
                        "total_logs": last_log_count,
                        "message": f"Deployment {deployment.status}. Stream complete."
                    })
                    break

                await asyncio.sleep(3)  # Poll every 3 seconds

            except WebSocketDisconnect:
                break
            except Exception as e:
                # Log error but continue streaming
                await websocket.send_json({
                    "type": "warning",
                    "message": f"Error during streaming: {str(e)}"
                })
                await asyncio.sleep(3)

        # Check if we hit max iterations
        if iteration >= max_iterations:
            await websocket.send_json({
                "type": "timeout",
                "message": "Stream timeout after 10 minutes. Please refresh to continue monitoring."
            })

        await websocket.close()

    except WebSocketDisconnect:
        # Client disconnected - this is normal
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Fatal error: {str(e)}"
            })
            await websocket.close()
        except:
            pass  # WebSocket might already be closed
