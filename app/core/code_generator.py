from typing import List, Dict, Any


class CodeGenerator:
    def generate_fastapi_wrapper(
        self,
        notebook_name: str,
        dependencies: List[str],
        cell_classifications: List[Dict[str, Any]]
    ) -> str:
        has_ml_model = any("training" in c.get("type", "") for c in cell_classifications)

        imports = """from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import main
"""

        if has_ml_model:
            imports += "import pickle\nfrom pathlib import Path\n"

        app_code = f"""
app = FastAPI(title="{notebook_name} API")

@app.get("/")
def root():
    return RedirectResponse(url="/docs")

@app.get("/health")
def health():
    return {{"status": "healthy"}}
"""

        if has_ml_model:
            app_code += """
class PredictionRequest(BaseModel):
    features: list

class PredictionResponse(BaseModel):
    prediction: Any

@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):
    try:
        result = main.predict(request.features)
        return {"prediction": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
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

        return f"""# {notebook_name}

Generated from Jupyter Notebook using NotebookDeploy

## Files

- `main.py` - Converted notebook code
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration
- `app.py` - {"FastAPI" if app_type == "fastapi" else "Streamlit"} wrapper
- `docker-compose.yml` - Local development setup
- `deploy.sh` - Deployment script
{deploy_info}
## Local Development

### Using Docker Compose

```bash
docker-compose up
```

Access at: http://localhost:8080

### Using Python

```bash
python -m venv venv
source venv/bin/activate  # or venv\\Scripts\\activate on Windows
pip install -r requirements.txt
{"uvicorn app:app --reload" if app_type == "fastapi" else "streamlit run app.py"}
```

## Dependencies

{chr(10).join(f"- {dep}" for dep in dependencies)}

## Deployment

### Google Cloud Run

```bash
./deploy.sh
```

### Manual Docker Build

```bash
docker build -t {notebook_name.lower()} .
docker run -p 8080:8080 {notebook_name.lower()}
```

## API Documentation

{"Visit /docs for interactive API documentation" if app_type == "fastapi" else "Streamlit UI available at root path"}
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
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - .:/app
    {"command: uvicorn app:app --host 0.0.0.0 --port 8080 --reload" if app_type == "fastapi" else 'command: streamlit run app.py --server.port=8080 --server.address=0.0.0.0'}
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

PROJECT_ID="{project_id}"
REGION="{region}"
SERVICE_NAME="{service_name}"
IMAGE_NAME="{image_name}"

echo "Building Docker image..."
docker build -t $IMAGE_NAME .

echo "Pushing to Artifact Registry..."
docker push $IMAGE_NAME

echo "Deploying to Cloud Run..."
gcloud run deploy $SERVICE_NAME \\
  --image $IMAGE_NAME \\
  --platform managed \\
  --region $REGION \\
  --allow-unauthenticated \\
  --project $PROJECT_ID

echo "Deployment complete!"
gcloud run services describe $SERVICE_NAME --region $REGION --project $PROJECT_ID --format="value(status.url)"
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
from app import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()

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

def test_app_exists():
    assert Path("app.py").exists()

def test_requirements_exists():
    assert Path("requirements.txt").exists()
"""
