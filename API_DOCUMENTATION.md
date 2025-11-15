# Notebook to Cloud - API Documentation

**Base URL:** `http://localhost:8000` (development) or your production URL

**API Version:** v1

**All endpoints are prefixed with:** `/api/v1`

---

## Table of Contents

1. [Authentication](#authentication)
2. [One-Click Deploy (Recommended)](#one-click-deploy)
3. [Manual Deploy Flow](#manual-deploy-flow)
4. [Webhooks](#webhooks)
5. [Metrics & Analytics](#metrics--analytics)
6. [Admin & IAM](#admin--iam)
7. [Error Handling](#error-handling)

---

## Authentication

### Register User

**Endpoint:** `POST /api/v1/auth/register`

**Request Body:**

```json
{
  "email": "user@example.com",
  "username": "johndoe",
  "password": "SecurePass123!"
}
```

**Response:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "johndoe",
  "is_active": true
}
```

### Login

**Endpoint:** `POST /api/v1/auth/login`

**Request Body (Form Data):**

```
username: johndoe
password: SecurePass123!
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Store the `access_token` and use it in all subsequent requests:**

```
Authorization: Bearer {access_token}
```

### Refresh Token

**Endpoint:** `POST /api/v1/auth/refresh`

**Request Body:**

```json
{
  "refresh_token": "your_refresh_token_here"
}
```

---

## One-Click Deploy (Recommended)

This is the **simplest way** to deploy a notebook - everything happens automatically!

### Deploy Notebook

**Endpoint:** `POST /api/v1/pipeline/deploy`

**Headers:**

```
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**Form Data:**

- `file`: The `.ipynb` file (required)
- `cpu`: CPU allocation, e.g., "1", "2" (optional, default: "1")
- `memory`: Memory allocation, e.g., "512Mi", "1Gi" (optional, default: "512Mi")
- `min_instances`: Minimum instances (optional, default: 0)
- `max_instances`: Maximum instances (optional, default: 10)

**JavaScript Example:**

```javascript
const formData = new FormData();
formData.append("file", notebookFile); // File object from input
formData.append("cpu", "1");
formData.append("memory", "512Mi");
formData.append("min_instances", "0");
formData.append("max_instances", "10");

const response = await fetch("http://localhost:8000/api/v1/pipeline/deploy", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
  body: formData,
});

const result = await response.json();
console.log(result);
```

**Response:**

```json
{
  "pipeline_id": "pipeline-3-1763155678",
  "notebook_id": 3,
  "status": "processing",
  "message": "Pipeline started. Use /pipeline/status/{pipeline_id} to track progress."
}
```

### Track Pipeline Status

**Endpoint:** `GET /api/v1/pipeline/status/{pipeline_id}`

**Headers:**

```
Authorization: Bearer {access_token}
```

**Response:**

```json
{
  "pipeline_id": "pipeline-3-1763155678",
  "notebook_id": 3,
  "build_id": 7,
  "deployment_id": 4,
  "current_step": "deploy",
  "status": "deployed",
  "steps_completed": ["parse", "dependencies", "upload", "build", "deploy"],
  "error_message": null,
  "notebook_status": "deployed",
  "build_status": "success",
  "deployment_status": "deployed",
  "service_url": "https://notebook-3-1-xxx.run.app"
}
```

**Status Values:**

- `processing` - Pipeline is running
- `deployed` - Successfully deployed
- `failed` - Deployment failed (check `error_message`)

**Steps:**

1. `parse` - Extracting code from notebook
2. `dependencies` - Analyzing dependencies
3. `upload` - Uploading source to cloud
4. `build` - Building container image
5. `deploy` - Deploying to Cloud Run

**JavaScript Polling Example:**

```javascript
async function pollPipelineStatus(pipelineId) {
  const response = await fetch(
    `http://localhost:8000/api/v1/pipeline/status/${pipelineId}`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    }
  );

  const status = await response.json();

  if (status.status === "deployed") {
    console.log("Deployment complete!", status.service_url);
    return status;
  } else if (status.status === "failed") {
    console.error("Deployment failed:", status.error_message);
    return status;
  } else {
    // Still processing, poll again after 5 seconds
    setTimeout(() => pollPipelineStatus(pipelineId), 5000);
  }
}
```

### Get Pipeline History

**Endpoint:** `GET /api/v1/pipeline/history?skip=0&limit=20`

**Headers:**

```
Authorization: Bearer {access_token}
```

**Response:**

```json
{
  "total": 5,
  "pipelines": [
    {
      "notebook_id": 3,
      "notebook_name": "sample_streamlit_app",
      "notebook_status": "deployed",
      "build_id": 7,
      "build_status": "success",
      "deployment_id": 4,
      "deployment_status": "deployed",
      "service_url": "https://notebook-3-1-xxx.run.app",
      "created_at": "2025-11-14T22:00:00Z"
    }
  ]
}
```

---

## Manual Deploy Flow

For advanced users who want granular control over each step.

### 1. Upload Notebook

**Endpoint:** `POST /api/v1/notebooks/upload`

**Headers:**

```
Authorization: Bearer {access_token}
Content-Type: multipart/form-data
```

**Form Data:**

- `file`: The `.ipynb` file

**Response:**

```json
{
  "id": 1,
  "name": "my_notebook",
  "filename": "my_notebook.ipynb",
  "user_id": 1,
  "status": "uploaded",
  "created_at": "2025-11-14T20:00:00Z"
}
```

### 2. Parse Notebook

**Endpoint:** `POST /api/v1/notebooks/{notebook_id}/parse`

**Headers:**

```
Authorization: Bearer {access_token}
```

**Response:**

```json
{
  "id": 1,
  "status": "parsed",
  "code_cells_count": 10,
  "dependencies": ["pandas", "numpy", "streamlit"],
  "parsed_at": "2025-11-14T20:01:00Z"
}
```

### 3. Download Generated Files (Optional)

**Endpoints:**

- `GET /api/v1/notebooks/{notebook_id}/download/main.py`
- `GET /api/v1/notebooks/{notebook_id}/download/requirements.txt`

### 4. Trigger Build

**Endpoint:** `POST /api/v1/builds/trigger/{notebook_id}`

**Headers:**

```
Authorization: Bearer {access_token}
```

**Response:**

```json
{
  "id": 1,
  "notebook_id": 1,
  "build_id": "build-1-1763149623",
  "status": "queued",
  "image_name": "us-central1-docker.pkg.dev/project/repo/notebook:latest",
  "created_at": "2025-11-14T20:02:00Z"
}
```

### 5. Monitor Build Status

**Endpoint:** `GET /api/v1/builds/{build_id}`

**Response:**

```json
{
  "id": 1,
  "status": "success",
  "log_url": "https://console.cloud.google.com/cloud-build/builds/...",
  "started_at": "2025-11-14T20:02:10Z",
  "finished_at": "2025-11-14T20:04:30Z"
}
```

**Status Values:** `queued`, `building`, `success`, `failed`

### 6. Deploy to Cloud Run

**Endpoint:** `POST /api/v1/deployments`

**Headers:**

```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:**

```json
{
  "notebook_id": 1,
  "build_id": 1,
  "cpu": "1",
  "memory": "512Mi",
  "min_instances": 0,
  "max_instances": 10
}
```

**Response:**

```json
{
  "id": 1,
  "notebook_id": 1,
  "service_name": "notebook-1-1",
  "status": "deploying",
  "created_at": "2025-11-14T20:05:00Z"
}
```

### 7. Monitor Deployment Status

**Endpoint:** `GET /api/v1/deployments/{deployment_id}`

**Response:**

```json
{
  "id": 1,
  "status": "deployed",
  "service_url": "https://notebook-1-1-xxx.run.app",
  "deployed_at": "2025-11-14T20:06:00Z"
}
```

---

## Webhooks

Configure these endpoints in GitHub/GitLab for auto-deployment on push.

### GitHub Webhook

**Endpoint:** `POST /api/v1/webhooks/github`

**No authentication required** (uses signature verification)

Set this URL in your GitHub repo settings under Webhooks.

### GitLab Webhook

**Endpoint:** `POST /api/v1/webhooks/gitlab`

**No authentication required** (uses token verification)

Set this URL in your GitLab repo settings under Webhooks.

---

## Metrics & Analytics

### Build Metrics

**Endpoint:** `GET /api/v1/metrics/builds?days=30`

**Headers:**

```
Authorization: Bearer {access_token}
```

**Response:**

```json
{
  "total_builds": 25,
  "successful_builds": 20,
  "failed_builds": 5,
  "success_rate": 80.0,
  "average_build_time_seconds": 145.5,
  "builds_by_status": {
    "success": 20,
    "failed": 5
  }
}
```

### Deployment Metrics

**Endpoint:** `GET /api/v1/metrics/deployments?days=30`

**Response:**

```json
{
  "total_deployments": 20,
  "successful_deployments": 18,
  "failed_deployments": 2,
  "active_deployments": 15,
  "success_rate": 90.0,
  "deployments_by_status": {
    "deployed": 18,
    "failed": 2
  }
}
```

### User Activity

**Endpoint:** `GET /api/v1/metrics/activity?days=7`

**Response:**

```json
{
  "total_notebooks": 10,
  "total_builds": 25,
  "total_deployments": 20,
  "recent_activity": [
    {
      "type": "deployment",
      "id": 5,
      "status": "deployed",
      "notebook_id": 3,
      "service_url": "https://...",
      "created_at": "2025-11-14T20:00:00Z"
    }
  ]
}
```

### Time-Series Data

**Endpoints:**

- `GET /api/v1/metrics/timeseries/builds?days=30`
- `GET /api/v1/metrics/timeseries/deployments?days=30`

**Response:**

```json
{
  "period_days": 30,
  "data": [
    {
      "date": "2025-01-15",
      "total": 5,
      "successful": 4,
      "failed": 1,
      "success_rate": 80.0
    }
  ]
}
```

---

## Admin & IAM

All admin endpoints require the `admin` role.

### List Users

**Endpoint:** `GET /api/v1/admin/users?skip=0&limit=100`

**Headers:**

```
Authorization: Bearer {admin_access_token}
```

### Update User

**Endpoint:** `PUT /api/v1/admin/users/{user_id}`

**Request Body:**

```json
{
  "is_active": true,
  "is_superuser": false,
  "organization_id": 1
}
```

### List Roles

**Endpoint:** `GET /api/v1/admin/roles`

**Response:**

```json
[
  {
    "id": 1,
    "name": "admin",
    "description": "Full system access",
    "permissions": ["admin:all"]
  },
  {
    "id": 2,
    "name": "developer",
    "description": "Can create and deploy notebooks",
    "permissions": ["notebook:create", "build:trigger", "deploy:create"]
  }
]
```

### Assign Role to User

**Endpoint:** `POST /api/v1/admin/roles/assign`

**Request Body:**

```json
{
  "user_id": 2,
  "role_id": 2
}
```

### Initialize Default Roles

**Endpoint:** `POST /api/v1/admin/init-roles`

Call this once after deployment to create default roles (admin, developer, viewer).

---

## Error Handling

All errors follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**

- `200` - Success
- `201` - Resource created
- `400` - Bad request (validation error)
- `401` - Unauthorized (missing or invalid token)
- `403` - Forbidden (insufficient permissions)
- `404` - Resource not found
- `500` - Internal server error

**Example Error Response:**

```json
{
  "detail": "Notebook must be parsed first. Current status: uploaded"
}
```

---

## Complete User Flow Example

Here's how a typical user would interact with the API:

```javascript
// 1. Register
const registerResponse = await fetch("/api/v1/auth/register", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    email: "user@example.com",
    username: "johndoe",
    password: "SecurePass123!",
  }),
});

// 2. Login
const loginFormData = new FormData();
loginFormData.append("username", "johndoe");
loginFormData.append("password", "SecurePass123!");

const loginResponse = await fetch("/api/v1/auth/login", {
  method: "POST",
  body: loginFormData,
});

const { access_token } = await loginResponse.json();

// 3. Deploy notebook (one-click)
const deployFormData = new FormData();
deployFormData.append("file", notebookFile);
deployFormData.append("cpu", "1");
deployFormData.append("memory", "512Mi");

const deployResponse = await fetch("/api/v1/pipeline/deploy", {
  method: "POST",
  headers: { Authorization: `Bearer ${access_token}` },
  body: deployFormData,
});

const { pipeline_id } = await deployResponse.json();

// 4. Poll for status
async function checkStatus() {
  const statusResponse = await fetch(`/api/v1/pipeline/status/${pipeline_id}`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });

  const status = await statusResponse.json();

  if (status.status === "deployed") {
    console.log("App deployed at:", status.service_url);
    window.location.href = status.service_url;
  } else if (status.status === "failed") {
    console.error("Deployment failed:", status.error_message);
  } else {
    setTimeout(checkStatus, 5000); // Check again in 5 seconds
  }
}

checkStatus();
```

---

## Interactive API Documentation

For interactive API testing, visit:
**Swagger UI:** `http://localhost:8000/docs`

This provides:

- Interactive API explorer
- Request/response schemas
- Try-it-out functionality
- Authentication support

---

## Support

For issues or questions:

- Check logs in the response `error_message` field
- View Cloud Build logs using the `log_url` field
