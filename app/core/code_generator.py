from typing import List, Dict, Any


class CodeGenerator:
    def generate_fastapi_wrapper(
        self,
        notebook_name: str,
        dependencies: List[str],
        cell_classifications: List[Dict[str, Any]],
        use_gcs_model: bool = True,
        model_info: Dict[str, Any] = None
    ) -> str:
        has_ml_model = (model_info and model_info.get("has_model")) or any("training" in c.get("type", "") for c in cell_classifications)

        if model_info is None:
            model_info = {}

        imports = """from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Any
from datetime import datetime
import main
"""

        if has_ml_model and use_gcs_model:
            imports += """import os
import pickle
from google.cloud import storage
"""

        app_code = f"""
app = FastAPI(title="{notebook_name} API")
"""

        if has_ml_model and use_gcs_model:
            app_code += """
_model = None

def load_model():
    client = storage.Client()
    bucket_name = os.getenv("GCS_BUCKET")
    model_path = os.getenv("MODEL_GCS_PATH")

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(model_path)

    model_bytes = blob.download_as_bytes()
    return pickle.loads(model_bytes)

@app.on_event("startup")
def startup():
    global _model
    _model = load_model()

@app.post("/admin/reload-model")
def reload_model(x_api_key: str = Header(...)):
    expected_key = os.getenv("ADMIN_API_KEY")
    if not expected_key or x_api_key != expected_key:
        raise HTTPException(401, "Invalid API key")

    global _model
    _model = load_model()
    return {"status": "reloaded", "timestamp": datetime.utcnow().isoformat()}
"""

        app_code += """
@app.get("/")
def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
def health():
    return {"status": "healthy"}
"""

        if has_ml_model:
            output_type = model_info.get("output_type", "classification")
            n_features = model_info.get("n_features", 0)
            feature_names = model_info.get("feature_names", [])
            class_names = model_info.get("class_names", [])
            prediction_method = model_info.get("prediction_method", "predict")

            if feature_names and len(feature_names) == n_features:
                request_fields = "\n    ".join([f"{name}: float" for name in feature_names])
                features_array = f"[{', '.join([f'request.{name}' for name in feature_names])}]"
            elif n_features > 0:
                request_fields = f"features: list[float]  # Expects {n_features} features"
                features_array = "request.features"
            else:
                request_fields = "features: list"
                features_array = "request.features"

            if output_type == "classification" and class_names:
                response_fields = """prediction: Any
    confidence: float = None
    probabilities: dict = None"""
                prediction_logic = f"""
    import numpy as np
    X = np.array([{features_array}])

    prediction = _model.{prediction_method}(X)[0]

    has_proba = hasattr(_model, 'predict_proba')
    probabilities = _model.predict_proba(X)[0] if has_proba else None

    class_names = {class_names}
    pred_label = class_names[int(prediction)] if isinstance(prediction, (int, np.integer)) and len(class_names) > 0 else str(prediction)

    return {{
        "prediction": pred_label,
        "confidence": float(max(probabilities)) if probabilities is not None else None,
        "probabilities": dict(zip(class_names, probabilities.tolist())) if probabilities is not None and len(class_names) > 0 else None
    }}"""
            elif output_type == "regression":
                response_fields = """value: float
    prediction: Any"""
                prediction_logic = f"""
    import numpy as np
    X = np.array([{features_array}])
    result = _model.{prediction_method}(X)[0]

    return {{
        "value": float(result),
        "prediction": float(result)
    }}"""
            else:
                response_fields = "prediction: Any"
                prediction_logic = f"""
    import numpy as np
    X = np.array([{features_array}])
    result = _model.{prediction_method}(X)

    return {{"prediction": result.tolist() if hasattr(result, 'tolist') else result}}"""

            app_code += f"""
class PredictionRequest(BaseModel):
    {request_fields}

class PredictionResponse(BaseModel):
    {response_fields}

@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    global _model
    if _model is None:
        raise HTTPException(503, "Model not loaded")
    try:{prediction_logic}
    except Exception as e:
        raise HTTPException(500, str(e))
"""

        return imports + app_code

    def generate_streamlit_wrapper(self, notebook_name: str) -> str:
        return f"""import streamlit as st
import main

st.set_page_config(page_title="{notebook_name}", layout="wide")

st.title("{notebook_name}")
st.write("Deployed from Jupyter Notebook")

if __name__ == "__main__":
    main.main()
"""

    def generate_readme(
        self,
        notebook_name: str,
        dependencies: List[str],
        app_type: str,
        service_url: str = None
    ) -> str:
        deploy_info = f"\n## Live Deployment\n\nService URL: {service_url}\n" if service_url else ""
        has_model = 'google-cloud-storage' in dependencies

        # Pre-build strings to avoid backslashes in f-strings
        main_desc = "Complete FastAPI application with model loading from GCS" if app_type == "fastapi" else "Converted notebook code"
        env_note = "(configure for model loading)" if has_model else ""
        config_section = "## Configuration" if has_model else ""
        docker_env_comment = "# Copy and configure .env first" if has_model else ""
        docker_cp_command = "cp .env.template .env" if has_model else ""
        python_env_comment = "# Set environment variables from .env" if has_model else ""
        python_export = "export $(cat .env | grep -v '^#' | xargs)" if has_model else ""
        python_command = "python main.py" if app_type == "fastapi" else "streamlit run main.py"
        deploy_comment = "# Configure .env file first with your GCS bucket and model path" if has_model else ""
        docker_env_flag = "--env-file .env " if has_model else ""
        api_docs = "Visit /docs for interactive API documentation" if app_type == "fastapi" else "Streamlit UI available at root path"
        venv_activate = "source venv/bin/activate  # or venv\\Scripts\\activate on Windows"
        curl_backslash = "\\"

        config_details = ""
        if has_model:
            config_details = """
Before running, copy `.env.template` to `.env` and configure:

```bash
cp .env.template .env
# Edit .env with your actual values
```

Required environment variables:
- `GCS_BUCKET`: Your Google Cloud Storage bucket name
- `MODEL_GCS_PATH`: Path to your model file in GCS
- `MODEL_FILE_EXTENSION`: Model file extension (pkl, joblib, pth, h5, etc.)
- `ADMIN_API_KEY`: API key for admin endpoints
"""

        model_management = ""
        if has_model:
            model_management = f"""

## Model Management

### Endpoints
- `POST /predict` - Make predictions with the loaded model
- `GET /health` - Health check endpoint
- `POST /admin/reload-model` - Reload model from GCS (requires x-api-key header)

### Reloading Models
To reload a new model version without redeploying:

```bash
curl -X POST https://your-service-url/admin/reload-model {curl_backslash}
  -H "x-api-key: your-admin-api-key"
```
"""

        deps_list = "\n".join(f"- {dep}" for dep in dependencies)

        return f"""# {notebook_name}

Generated from Jupyter Notebook using Codematics

## Files

- `main.py` - {main_desc}
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration
- `.env.template` - Environment variables template {env_note}
- `docker-compose.yml` - Local development setup
- `deploy.sh` - Deployment script
{deploy_info}
{config_section}{config_details}
## Local Development

### Using Docker Compose

```bash
{docker_env_comment}
{docker_cp_command}
docker-compose up
```

Access at: http://localhost:8080

### Using Python

```bash
python -m venv venv
{venv_activate}
pip install -r requirements.txt
{python_env_comment}
{python_export}
{python_command}
```

## Dependencies

{deps_list}

## Deployment

### Google Cloud Run

```bash
{deploy_comment}
./deploy.sh
```

The deploy script will automatically load environment variables from `.env` and pass them to Cloud Run.

### Manual Docker Build

```bash
docker build -t {notebook_name.lower()} .
docker run -p 8080:8080 {docker_env_flag}{notebook_name.lower()}
```

## API Documentation

{api_docs}{model_management}
"""

    def generate_docker_compose(
        self,
        notebook_name: str,
        app_type: str
    ) -> str:
        return f"""version: '3.8'

services:
  app:
    build: .
    ports:
      - "8080:8080"
    env_file:
      - .env
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - .:/app
    {"command: python main.py" if app_type == "fastapi" else 'command: streamlit run main.py --server.port=8080 --server.address=0.0.0.0'}
"""

    def generate_deploy_script(
        self,
        notebook_name: str,
        project_id: str,
        region: str,
        artifact_registry: str
    ) -> str:
        service_name = notebook_name.lower().replace("_", "-")
        image_name = f"{artifact_registry}/{service_name}:latest"

        return f"""#!/bin/bash
set -e

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    export $(cat .env | grep -v '^#' | xargs)
fi

PROJECT_ID="{project_id}"
REGION="{region}"
SERVICE_NAME="{service_name}"
IMAGE_NAME="{image_name}"

echo "Building Docker image..."
docker build -t $IMAGE_NAME .

echo "Pushing to Artifact Registry..."
docker push $IMAGE_NAME

echo "Deploying to Cloud Run..."

# Build environment variables arguments
ENV_VARS=""
if [ ! -z "$GCS_BUCKET" ]; then
    ENV_VARS="$ENV_VARS,GCS_BUCKET=$GCS_BUCKET"
fi
if [ ! -z "$MODEL_GCS_PATH" ]; then
    ENV_VARS="$ENV_VARS,MODEL_GCS_PATH=$MODEL_GCS_PATH"
fi
if [ ! -z "$MODEL_FILE_EXTENSION" ]; then
    ENV_VARS="$ENV_VARS,MODEL_FILE_EXTENSION=$MODEL_FILE_EXTENSION"
fi
if [ ! -z "$ADMIN_API_KEY" ]; then
    ENV_VARS="$ENV_VARS,ADMIN_API_KEY=$ADMIN_API_KEY"
fi

# Remove leading comma if exists
ENV_VARS=${{ENV_VARS#,}}

# Deploy with or without env vars
if [ ! -z "$ENV_VARS" ]; then
    echo "Deploying with environment variables..."
    gcloud run deploy $SERVICE_NAME \\
      --image $IMAGE_NAME \\
      --platform managed \\
      --region $REGION \\
      --allow-unauthenticated \\
      --set-env-vars "$ENV_VARS" \\
      --project $PROJECT_ID
else
    echo "Deploying without environment variables..."
    gcloud run deploy $SERVICE_NAME \\
      --image $IMAGE_NAME \\
      --platform managed \\
      --region $REGION \\
      --allow-unauthenticated \\
      --project $PROJECT_ID
fi

echo "Deployment complete!"
gcloud run services describe $SERVICE_NAME --region $REGION --project $PROJECT_ID --format="value(status.url)"
"""

    def generate_env_template(
        self,
        notebook_id: int,
        model_version: int = None,
        model_file_extension: str = None
    ) -> str:
        """Generate .env template file with placeholders for configuration"""
        model_path = f"models/notebook_{notebook_id}/model.{model_file_extension}" if model_file_extension else f"models/notebook_{notebook_id}/model.pkl"

        return f"""# Google Cloud Storage Configuration
GCS_BUCKET=your-bucket-name
MODEL_GCS_PATH={model_path}
MODEL_FILE_EXTENSION={model_file_extension or 'pkl'}

# API Configuration
ADMIN_API_KEY=your-secure-api-key-here

# Server Configuration
PORT=8080

# Instructions:
# 1. Replace 'your-bucket-name' with your actual GCS bucket name
# 2. Update MODEL_GCS_PATH if your model is stored at a different path
# 3. Set MODEL_FILE_EXTENSION based on your model format (pkl, joblib, pth, h5, etc.)
# 4. Generate a secure ADMIN_API_KEY for the /admin/reload-model endpoint
# 5. PORT is set to 8080 by default for Cloud Run compatibility
#
# For Cloud Run deployment, set these as environment variables in the deployment:
# gcloud run deploy SERVICE_NAME \\
#   --set-env-vars GCS_BUCKET=your-bucket-name,MODEL_GCS_PATH={model_path},MODEL_FILE_EXTENSION={model_file_extension or 'pkl'},ADMIN_API_KEY=your-key
"""

    def generate_gitignore(self) -> str:
        return """__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/
.env
.venv
*.ipynb_checkpoints
.DS_Store
*.log
"""

    def generate_test_file(self, notebook_name: str, app_type: str) -> str:
        if app_type == "fastapi":
            return """from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 307  # Redirect to /docs
    assert response.headers["location"] == "/docs"

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
"""
        else:
            return f"""import pytest
from pathlib import Path

def test_main_exists():
    assert Path("main.py").exists()

def test_requirements_exists():
    assert Path("requirements.txt").exists()

def test_dockerfile_exists():
    assert Path("Dockerfile").exists()
"""