# System Flow & Testing Guide

This document outlines the high-level architecture of the **Notebook to Cloud** system and provides instructions on how to test its core functionalities, including the recently implemented backend features.

## 1. System Architecture & Flow

The system is designed to transform local Jupyter Notebooks into production-ready web applications on Google Cloud Run.

### High-Level Data Flow
1.  **User** uploads a `.ipynb` file via the REST API.
2.  **API Server** (FastAPI) receives the file and:
    *   Validates the user (Auth).
    *   Stores the raw notebook in **Google Cloud Storage (GCS)** (Stateless).
3.  **Parser Service** extracts code cells and dependencies, generating `main.py` and `requirements.txt`.
4.  **AI Service (Gemini)** analyzes the code for security, performance, and Cloud Run compatibility.
5.  **Deployment Service**:
    *   Generates a `Dockerfile`.
    *   Builds a container image using **Google Cloud Build**.
    *   Deploys the container to **Google Cloud Run**.
6.  **Observability**: Custom metrics (deployment success/failure, health scores) are pushed to **Google Cloud Monitoring**.

---

## 2. How to Test the System

### A. Automated Testing (CI/CD)
The project includes a suite of unit and integration tests.

**Prerequisites:**
- Python 3.11+
- `uv` package manager installed.
- Valid `.env` file with GCP credentials (for integration tests).

**Running Tests:**
```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest
```

**CI/CD Pipeline:**
- On every push to `main`, GitHub Actions automatically runs these tests. Check the "Actions" tab in the repository to see the status.

### B. Manual Testing Workflow

Follow these steps to manually verify the end-to-end flow using `curl` or an API client (like Postman).

#### 1. Authentication
Obtain an access token to interact with the API.
*   **Endpoint:** `POST /api/v1/auth/login`
*   **Body:** `username=testuser&password=testpass`
*   **Result:** Copy the `access_token`.

#### 2. Upload Notebook
*   **Endpoint:** `POST /api/v1/notebooks/upload`
*   **Header:** `Authorization: Bearer <access_token>`
*   **Body:** Form-data with `file=@your_notebook.ipynb`
*   **Verification:** Check GCS bucket; the file should appear in `uploads/<user_id>/`.

#### 3. Parse Notebook
*   **Endpoint:** `POST /api/v1/notebooks/{notebook_id}/parse`
*   **Result:** Returns extracted dependencies and code stats.
*   **Verification:** `main.py` and `requirements.txt` are generated and stored in GCS.

#### 4. AI Analysis (New Feature)
*   **Endpoint:** `POST /api/v1/notebooks/{notebook_id}/analyze`
*   **Result:** JSON report with:
    *   Security issues (e.g., hardcoded secrets).
    *   Cloud Run compatibility checks (e.g., local file writes).
    *   Health Score (0-100).
*   **Verification:** Check Google Cloud Monitoring for the `custom.googleapis.com/notebook_health_score` metric.

#### 5. Deploy to Cloud Run
*   **Endpoint:** `POST /api/v1/deployments/{notebook_id}`
*   **Result:** Returns a `deployment_id` and initial status.
*   **Process:**
    *   The system triggers Cloud Build (logs available via API).
    *   On success, returns the **Service URL**.
*   **Verification:**
    *   Visit the Service URL to see your running app.
    *   Check Google Cloud Monitoring for `custom.googleapis.com/notebook_deployments`.

### C. Verifying Specific Features

#### Rate Limiting
*   **Test:** Send >100 requests within 1 minute from the same user.
*   **Expected Result:** `429 Too Many Requests`.

#### Observability
*   **Test:** Perform a deployment or analysis.
*   **Verification:** Go to **Google Cloud Console > Monitoring > Metrics Explorer**.
    *   Select Metric: `custom.googleapis.com/notebook_deployments` or `notebook_health_score`.
    *   You should see data points corresponding to your actions.
