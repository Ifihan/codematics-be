# NotebookDeploy - System Flow & Testing Guide

## System Overview

NotebookDeploy transforms Jupyter notebooks into production-ready APIs deployed on Google Cloud Run, powered by Gemini AI analysis.

---

## Complete System Flow

### 1. Authentication Flow

```
User → POST /api/v1/auth/register
     ↓
  Creates user account with hashed password
     ↓
User → POST /api/v1/auth/login
     ↓
  Returns JWT access token (30min) + refresh token (7 days)
     ↓
  Use token in Authorization: Bearer <token> header
```

**Key Points:**
- All subsequent requests require JWT token
- RBAC system enforces permissions
- API keys available for programmatic access

---

### 2. Notebook Upload & Parsing Flow

```
User → POST /api/v1/notebooks/upload (with .ipynb file)
     ↓
  Saves to local storage: uploads/user_{id}/notebook.ipynb
     ↓
  Creates Notebook record (status: uploaded)
     ↓
User → POST /api/v1/notebooks/{id}/parse
     ↓
  NotebookService processes notebook:
    - Extracts code cells
    - Generates main.py (without markdown/magics)
    - Extracts dependencies from imports
    - Generates requirements.txt
    - Validates Python syntax
     ↓
  Saves files to: storage/notebooks/{user_id}/{notebook_id}/
     ↓
  Updates Notebook (status: parsed)
```

**Storage Structure:**
```
storage/notebooks/{user_id}/{notebook_id}/
  ├── main.py              # Converted notebook code
  └── requirements.txt     # Python dependencies
```

---

### 3. AI Analysis Flow (Gemini Integration)

```
User → POST /api/v1/notebooks/{id}/analyze
     ↓
  Reads main.py content
     ↓
  Sends to Vertex AI (Gemini 2.0 Flash):
    - Structured prompt requesting JSON analysis
    - Analyzes: security, performance, compatibility
     ↓
  Gemini returns analysis:
    {
      "cell_classifications": [
        {"index": 0, "type": "production", "confidence": 0.95}
      ],
      "issues": [
        {
          "severity": "high",
          "category": "security",
          "description": "Hardcoded API key detected",
          "cell_index": 5,
          "suggestion": "Use environment variables"
        }
      ],
      "recommendations": ["Add error handling", ...],
      "resource_estimates": {
        "cpu": "1",
        "memory": "512Mi",
        "estimated_cold_start": "2s"
      }
    }
     ↓
  Calculates health score (0-100):
    - Start at 100
    - Deduct: critical(-20), high(-10), medium(-5), low(-2)
     ↓
  Saves to Analysis table
     ↓
  Updates Notebook (status: analyzed)
     ↓
  Logs event to Cloud Logging
```

**Key Points:**
- Requires Vertex AI API enabled
- Uses service account authentication
- Analysis cached (returns existing if already analyzed)

---

### 4. Deployment Flow (One-Click)

```
User → POST /api/v1/deployments/one-click
  Body: {
    "notebook_id": 123,
    "name": "my-notebook-api",
    "region": "us-central1"  (optional)
  }
     ↓
  Creates Deployment record (status: pending)
     ↓
  Triggers background task: process_deployment()
     ↓

BACKGROUND PROCESS:
     ↓
  1. UPDATE STATUS: building
     Log: deployment_started
     ↓
  2. PREPARE SOURCE FILES:
     - Copy main.py, requirements.txt to temp dir
     - Detect app type (streamlit/fastapi/flask/default)
     - Generate Dockerfile based on dependencies
     - Create tarball
     ↓
  3. UPLOAD TO CLOUD STORAGE:
     - Upload to gs://{bucket}/deployments/{id}/source.tar.gz
     ↓
  4. TRIGGER CLOUD BUILD:
     - Submit build job
     - Build steps:
       a) docker build -t {image_name}
       b) docker push to Artifact Registry
     - Get build_id
     - Update: build_id, image_url, build_logs_url
     - Log: build_started
     ↓
  5. POLL BUILD STATUS (max 10 min):
     - Check every 10 seconds
     - If SUCCESS: continue
     - If FAILURE/CANCELLED/TIMEOUT: fail deployment
     - Track build_duration
     - Log: build_completed
     ↓
  6. DEPLOY TO CLOUD RUN (status: deploying):
     - Create/update Cloud Run service
     - Configure: port=8080, memory=512Mi, cpu=1
     - Set auto-scaling: min=0, max=10
     - Make public (allow unauthenticated)
     ↓
  7. SUCCESS (status: deployed):
     - Get service_url
     - Set deployed_at timestamp
     - Calculate total_duration
     - Log: deployment_success
     - Save DeploymentMetric
     ↓
  8. ON ERROR:
     - Set status: failed
     - Save error_message
     - Log: deployment_failure

Returns immediately with deployment record
Client polls GET /api/v1/deployments/{id} for status
```

**Deployment States:**
- `pending` → Initial state
- `building` → Docker image building
- `deploying` → Pushing to Cloud Run
- `deployed` → Live and accessible
- `failed` → Error occurred (check error_message)

---

### 5. Code Export Flow

```
User → GET /api/v1/notebooks/{id}/export
     ↓
  ExportService creates complete package:
     ↓
  1. Copy main.py, requirements.txt
     ↓
  2. Generate app.py wrapper:
     - FastAPI: Creates /predict endpoint for ML models
     - Streamlit: Creates streamlit wrapper
     ↓
  3. Generate Dockerfile (based on app type)
     ↓
  4. Generate README.md:
     - Setup instructions
     - Local development guide
     - Deployment commands
     - Service URL (if deployed)
     ↓
  5. Generate docker-compose.yml (local dev)
     ↓
  6. Generate deploy.sh (GCP deployment script)
     ↓
  7. Generate .gitignore
     ↓
  8. Generate test_app.py (basic tests)
     ↓
  Creates ZIP: {notebook_name}.zip
     ↓
  Returns ZIP file for download
```

**ZIP Structure:**
```
notebook-name/
  ├── main.py
  ├── requirements.txt
  ├── app.py
  ├── Dockerfile
  ├── docker-compose.yml
  ├── deploy.sh
  ├── README.md
  ├── .gitignore
  └── test_app.py
```

---

## Observability & Monitoring

### Rate Limiting
- **Free tier**: 100 requests/minute per IP
- Returns HTTP 429 when exceeded
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`

### Cloud Logging Events
All events logged to Cloud Logging with structured data:

**API Requests:**
```json
{
  "event": "api_request",
  "method": "POST",
  "path": "/api/v1/notebooks/123/analyze",
  "user_id": 1,
  "status_code": 200,
  "duration_ms": 1250.5
}
```

**Deployments:**
```json
{
  "event": "deployment_started",
  "deployment_id": 45,
  "notebook_id": 123,
  "user_id": 1
}
```

**Build Events:**
```json
{
  "event": "build_completed",
  "build_id": "abc-123",
  "status": "SUCCESS",
  "duration_seconds": 120.5
}
```

**Errors:**
```json
{
  "event": "error",
  "error_type": "ValueError",
  "error_message": "Invalid notebook format",
  "context": {
    "path": "/api/v1/notebooks/123/parse",
    "method": "POST",
    "trace": "..."
  }
}
```

### Deployment Metrics
Stored in `deployment_metrics` table:
```json
{
  "deployment_id": 45,
  "metric_type": "deployment_success",
  "value": {
    "total_duration": 180.5,
    "build_duration": 120.0,
    "deploy_duration": 60.5
  },
  "recorded_at": "2025-01-21T10:30:00Z"
}
```

### Error Handling
- Global error handler catches all exceptions
- Returns structured JSON errors
- Logs to Cloud Logging with full trace
- Continues serving other requests

---

## Testing Guide

### Prerequisites
1. **GCP Setup:**
   - Vertex AI API enabled
   - Cloud Build API enabled
   - Cloud Run API enabled
   - Cloud Logging API enabled
   - Service account with roles:
     - `roles/logging.logWriter`
     - `roles/aiplatform.user`
     - `roles/cloudbuild.builds.editor`
     - `roles/run.admin`
     - `roles/storage.admin`

2. **Environment Variables:**
   ```bash
   # .env file
   SECRET_KEY=your-secret-key
   DATABASE_URL=postgresql://...
   GCP_PROJECT_ID=codematics-477316
   GCP_REGION=us-central1
   GCP_ARTIFACT_REGISTRY=us-central1-docker.pkg.dev/codematics-477316/notebooks
   GCP_SERVICE_ACCOUNT_KEY=./gcp-key.json
   GCP_BUCKET_NAME=codematics-notebooks-source
   GOOGLE_APPLICATION_CREDENTIALS=./gcp-key.json
   ```

3. **Database Migration:**
   ```bash
   alembic upgrade head
   ```

---

### Test 1: Authentication

```bash
# Register user
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "SecurePass123!"
  }'

# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "SecurePass123!"
  }'

# Save access_token from response
export TOKEN="eyJhbGc..."
```

**Expected:**
- Register: 201 Created
- Login: 200 OK with `access_token` and `refresh_token`

---

### Test 2: Notebook Upload & Parse

```bash
# Upload notebook
curl -X POST http://localhost:8080/api/v1/notebooks/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@examples/sample_streamlit_app.ipynb"

# Save notebook_id from response
export NOTEBOOK_ID=1

# Parse notebook
curl -X POST http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID/parse \
  -H "Authorization: Bearer $TOKEN"

# Check status
curl http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:**
- Upload: 201 Created, `status: "uploaded"`
- Parse: 200 OK, `status: "parsed"`, `dependencies` array populated
- Files created in `storage/notebooks/{user_id}/{notebook_id}/`

**Verify Files:**
```bash
ls -la storage/notebooks/1/$NOTEBOOK_ID/
# Should see: main.py, requirements.txt
```

---

### Test 3: AI Analysis

```bash
# Analyze notebook
curl -X POST http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID/analyze \
  -H "Authorization: Bearer $TOKEN"

# View analysis
curl http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID \
  -H "Authorization: Bearer $TOKEN"
```

**Expected:**
- 200 OK with analysis:
  ```json
  {
    "health_score": 85,
    "cell_classifications": [...],
    "issues": [...],
    "recommendations": [...],
    "resource_estimates": {...}
  }
  ```
- Notebook `status: "analyzed"`

**Check Cloud Logging:**
```bash
# GCP Console → Logging → Logs Explorer
# Filter: resource.type="global" AND jsonPayload.event="analysis_completed"
```

---

### Test 4: One-Click Deployment

```bash
# Deploy notebook
curl -X POST http://localhost:8080/api/v1/deployments/one-click \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "notebook_id": '$NOTEBOOK_ID',
    "name": "test-notebook-api",
    "region": "us-central1"
  }'

# Save deployment_id
export DEPLOYMENT_ID=1

# Poll status (repeat every 10s)
curl http://localhost:8080/api/v1/deployments/$DEPLOYMENT_ID \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Flow:**
1. Initial response: `status: "pending"`
2. After ~10s: `status: "building"`
3. After ~2-3 min: `status: "deploying"`
4. After ~3-5 min: `status: "deployed"`, `service_url` populated

**Test Deployed Service:**
```bash
# Get service URL from deployment response
export SERVICE_URL="https://test-notebook-api-xyz.run.app"

# Test endpoint
curl $SERVICE_URL
```

**Check Cloud Logging:**
```bash
# Deployment events
# Filter: jsonPayload.event=("deployment_started" OR "build_started" OR "deployment_success")

# Build logs
# Click build_logs_url from deployment response
```

**Check Metrics:**
```bash
# View deployment metrics
curl http://localhost:8080/api/v1/deployments/$DEPLOYMENT_ID \
  -H "Authorization: Bearer $TOKEN" | jq

# Check build_duration, deployed_at fields
```

---

### Test 5: Code Export

```bash
# Export notebook
curl http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID/export \
  -H "Authorization: Bearer $TOKEN" \
  -o notebook-export.zip

# Extract and verify
unzip notebook-export.zip
cd exploratory-data-analysis-of-titanic-dataset/
ls -la
```

**Expected Files:**
```
main.py
requirements.txt
app.py              # FastAPI/Streamlit wrapper
Dockerfile
docker-compose.yml
deploy.sh           # Executable
README.md
.gitignore
test_app.py
```

**Test Locally:**
```bash
# Using Docker Compose
docker-compose up

# Or using Python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py  # or uvicorn app:app
```

---

### Test 6: Rate Limiting

```bash
# Spam requests (>100 in 1 minute)
for i in {1..110}; do
  curl http://localhost:8080/api/v1/notebooks \
    -H "Authorization: Bearer $TOKEN" \
    -w "\n%{http_code}\n"
done
```

**Expected:**
- First 100 requests: 200 OK
- Request 101+: 429 Too Many Requests
- Response headers: `X-RateLimit-Limit: 100`, `X-RateLimit-Remaining: 0`

---

### Test 7: Error Handling

```bash
# Invalid notebook ID
curl http://localhost:8080/api/v1/notebooks/99999 \
  -H "Authorization: Bearer $TOKEN"

# Parse non-existent notebook
curl -X POST http://localhost:8080/api/v1/notebooks/99999/parse \
  -H "Authorization: Bearer $TOKEN"

# Invalid file upload
curl -X POST http://localhost:8080/api/v1/notebooks/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@README.md"
```

**Expected:**
- 404 Not Found for missing resources
- 400 Bad Request for invalid operations
- Structured JSON error responses
- Errors logged to Cloud Logging

---

### Test 8: List & Manage Resources

```bash
# List all notebooks
curl http://localhost:8080/api/v1/notebooks \
  -H "Authorization: Bearer $TOKEN"

# List deployments
curl http://localhost:8080/api/v1/deployments \
  -H "Authorization: Bearer $TOKEN"

# Delete deployment
curl -X DELETE http://localhost:8080/api/v1/deployments/$DEPLOYMENT_ID \
  -H "Authorization: Bearer $TOKEN"

# Delete notebook
curl -X DELETE http://localhost:8080/api/v1/notebooks/$NOTEBOOK_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## Common Issues & Troubleshooting

### Issue 1: Vertex AI Permission Denied
**Error:** `403 Permission denied on Vertex AI`
**Fix:** Enable Vertex AI API and add `roles/aiplatform.user` to service account

### Issue 2: Cloud Build Fails
**Error:** `Build failed with status: FAILURE`
**Fix:**
- Check build logs URL
- Verify Artifact Registry exists
- Check Dockerfile syntax
- Ensure dependencies are valid

### Issue 3: Cloud Run Deploy Fails
**Error:** `Failed to deploy service`
**Fix:**
- Enable Cloud Run API
- Add `roles/run.admin` to service account
- Check service name (lowercase, hyphens only)
- Verify image pushed to Artifact Registry

### Issue 4: Rate Limit Hit
**Error:** `429 Too Many Requests`
**Fix:** Wait 60 seconds or increase limit in `main.py`:
```python
app.add_middleware(RateLimitMiddleware, requests_per_minute=1000)
```

### Issue 5: Logging Permission Denied
**Error:** `403 Permission 'logging.logEntries.create' denied`
**Fix:** Add `roles/logging.logWriter` to service account

---

## API Documentation

Full interactive API docs available at:
- Swagger UI: http://localhost:8080/docs
- ReDoc: http://localhost:8080/redoc

---

## Performance Benchmarks

**Typical Timings:**
- Upload: <1s
- Parse: 1-3s (depends on notebook size)
- Analysis: 5-15s (Gemini API call)
- Build: 1-3 min (Docker build)
- Deploy: 30-60s (Cloud Run deployment)
- **Total one-click deployment: 2-5 minutes**

**Resource Usage:**
- Default Cloud Run: 512Mi memory, 1 CPU
- Auto-scaling: 0-10 instances
- Cold start: 1-3s (depends on dependencies)

---

## Production Checklist

- [ ] All GCP APIs enabled
- [ ] Service account roles configured
- [ ] Environment variables set
- [ ] Database migrated
- [ ] Cloud Storage bucket created
- [ ] Artifact Registry created
- [ ] Rate limiting configured
- [ ] Cloud Logging verified
- [ ] Error tracking tested
- [ ] Deployment tested end-to-end
- [ ] Backup strategy implemented
- [ ] Monitoring dashboards created
- [ ] SSL/TLS configured (Cloud Run auto-provisions)
- [ ] Custom domain configured (optional)

---

## Next Steps

1. **Frontend Development** (Phase 5)
   - Next.js UI
   - Drag-and-drop upload
   - Live deployment dashboard
   - Log streaming

2. **Advanced Features**
   - Multi-region deployments
   - A/B testing support
   - Rollback functionality
   - Custom environment variables
   - GitHub integration

3. **Tier System**
   - Free: 3 notebooks, 5 deployments
   - Pro: Unlimited notebooks/deployments
   - Team: Shared workspaces
   - Enterprise: Custom quotas