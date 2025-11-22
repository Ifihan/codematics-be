# NotebookDeploy v4.0 - Complete System Flow

## Overview
End-to-end bidirectional flow from notebook upload to zero-downtime model updates with GitHub integration and automated webhook deployments.

---

## Flow 1: Initial Deployment (First Time)

### Step 1: User Authentication
```
POST /api/v1/auth/register
  → Create user account
  → Store hashed password (bcrypt)
  → Return user_id

POST /api/v1/auth/login
  → Validate credentials
  → Generate JWT tokens (access: 30min, refresh: 7 days)
  → Return tokens
```

### Step 2: Notebook & Model Upload (Single Request)
```
POST /api/v1/notebooks/upload
  Body: notebook_file (required), model_file (optional)

  → Upload notebook.ipynb (max 50MB)
  → Validate file type
  → Upload to GCS: gs://bucket/notebooks/{user_id}/{notebook_id}/notebook.ipynb
  → Store path in DB (status: "uploaded")

  If model_file provided:
    → Validate magic bytes (security check)
    → Auto-increment version (v1)
    → Upload to GCS: gs://bucket/models/{user_id}/{notebook_id}/v1/model.pkl
    → Create model_versions record (version=1, is_active=true)
    → Create GCS pointer: latest/version.txt → "1"

  → Return notebook_id with model_version if uploaded
```

### Step 3: Notebook Parsing
```
POST /api/v1/notebooks/{notebook_id}/parse
  → Download notebook from GCS
  → Extract code cells (skip markdown)
  → Concatenate code → main.py
  → AST parse for dependencies → requirements.txt
  → Detect FastAPI app instantiation
  → Upload main.py and requirements.txt to GCS
  → Update notebook (status: "parsed")
```

### Step 4: AI Analysis
```
POST /api/v1/notebooks/{notebook_id}/analyze
  → Send code to Gemini 2.5 Flash
  → Classify cells (exploration, training, production, testing)
  → Detect security issues:
    - Hardcoded secrets
    - Insecure deserialization
    - Command injection
    - SQL injection
  → Check Cloud Run compatibility
  → Calculate health score (0-100)
  → Estimate resources (CPU, memory, cold start)
  → Store analysis in DB
  → Update notebook (status: "analyzed")
```

### Step 5: One-Click Deployment
```
POST /api/v1/deployments/one-click
  Body: { notebook_id, name, region }

Background Process:
  1. Download main.py + requirements.txt from GCS
  2. Detect app type (fastapi/streamlit/flask)
  3. Check for active model version
  4. Generate app.py wrapper:
     - If model exists: Include GCS model loading + hot-reload endpoint
     - If no model: Standard API wrapper
  5. Generate multi-stage Dockerfile
  6. Generate admin API key (32-byte token)
  7. Create source.tar.gz
  8. Upload to GCS: deployments/{deployment_id}/source.tar.gz

  9. Cloud Build:
     → Submit build with source URI
     → Docker build (2 stages: builder + runtime)
     → Push to Artifact Registry
     → Poll status every 10s (max 600s)

  10. Cloud Run Deploy:
      → Create service with image
      → Inject environment variables (if model exists):
        - GCS_BUCKET=bucket-name
        - MODEL_GCS_PATH=models/{user}/{notebook}/v{version}/model.pkl
        - ADMIN_API_KEY={generated-key}
        - GCP_PROJECT_ID=project-id
      → Set IAM policy (allUsers as invoker)
      → Get service URL

  11. Store deployment:
      → service_url
      → admin_api_key (encrypted)
      → github_repo_url (null initially)
      → status="deployed"

  → Return deployment with service_url
```

---

## Flow 2: Zero-Downtime Model Update (v4.0 Feature!)

### Timeline: ~10 seconds, no downtime

### Option A: Version Upload & Activate (Multi-step)
```
1. Upload New Version
   POST /api/v1/notebooks/{notebook_id}/models
     Body: model.pkl (v2), accuracy=0.95

   → Validate file (magic bytes)
   → Auto-increment version (v2)
   → Upload to GCS: models/{user}/{notebook}/v2/model.pkl
   → Create model_versions record (v2, is_active=false)

2. Activate New Version
   POST /api/v1/notebooks/{notebook_id}/models/2/activate

   → Set v2 is_active=true, v1 is_active=false
   → Update GCS pointer: latest/version.txt → "2"
   → MODEL_GCS_PATH environment now points to v2

3. Hot Reload Deployed Service
   POST /api/v1/deployments/{deployment_id}/reload-model

   → Verify deployment status=deployed
   → Get active model version (v2)
   → HTTP POST to {service_url}/admin/reload-model
     Headers: { X-API-Key: {deployment.admin_api_key} }
   → Deployed container:
     - Calls load_model()
     - Downloads models/{user}/{notebook}/v2/model.pkl from GCS
     - Replaces global _model variable
     - Returns success
   → 3 retry attempts with 2s delay
   → Total time: ~10 seconds
   → Zero downtime!
```

### Option B: Quick Model Replacement (Single Request)
```
PUT /api/v1/notebooks/{notebook_id}/models/replace
  Body: model.pkl (auto v2), accuracy=0.96

  → Validates file
  → Auto-increments version
  → Uploads to GCS
  → Automatically sets as active
  → Updates latest pointer
  → Returns new version

Then call reload endpoint:
  POST /api/v1/deployments/{deployment_id}/reload-model
```

---

## Flow 3: GitHub Integration (Bidirectional Sync)

### Step 1: Connect GitHub
```
GET /api/v1/github/oauth/authorize
  → Returns GitHub OAuth URL with scopes: repo, workflow
  → User authorizes app

GET /api/v1/github/oauth/callback?code={code}
  → Exchange code for access token
  → Fetch GitHub user info
  → Store github_token & github_username in users table
  → Return { github_username, connected: true }
```

### Step 2: Push to GitHub (Platform → GitHub)
```
POST /api/v1/github/create-repo
  Body: { notebook_id, repo_name, description, private }

  Process:
  1. Verify user has github_token
  2. Query active model version (if exists)
  3. Create GitHub repository
  4. Generate and upload files:
     - main.py (from GCS)
     - requirements.txt (from GCS)
     - app.py (with GCS model loading if model exists)
     - Dockerfile (multi-stage build)
     - .gitignore
     - .github/workflows/deploy.yml (CI/CD)

  5. Register GitHub Webhook:
     - URL: https://yourdomain.com/api/v1/webhooks/github
     - Events: [push]
     - Secret: GITHUB_WEBHOOK_SECRET

  6. Update deployment.github_repo_url
  7. Return { repo_url, repo_name, owner }
```

### Step 3: Auto-Deploy from GitHub (GitHub → Platform)
```
When user pushes to GitHub repo (main branch):

1. GitHub sends webhook:
   POST /api/v1/webhooks/github
   Headers:
     - X-Hub-Signature-256: sha256=...
     - X-GitHub-Event: push
   Body:
     {
       "ref": "refs/heads/main",
       "repository": { "full_name": "user/repo" },
       "commits": [...]
     }

2. Platform verifies HMAC signature
3. Finds deployment by github_repo_url
4. Triggers Cloud Run rebuild:
   → deployment.status = "building"
   → Redeploy with updated code from GitHub
   → deployment.status = "deployed"
   → Updates service_url if changed

5. Total time: ~90 seconds (full rebuild)
6. User sees updated app at service_url
```

---

## Flow 4: Real-Time Monitoring

### WebSocket Logs
```
WS /api/v1/deployments/{deployment_id}/logs/stream

→ Polls build status every 2s
→ Sends JSON: { type: "status", status: "building" }
→ Auto-closes on completion
```

---

## Complete Bidirectional Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER ACTIONS                          │
└──────────────────┬──────────────────────────────────────┘
                   │
   ┌───────────────┼──────────────────┐
   │               │                  │
   v               v                  v
Upload          Analyze            Deploy         Push to
Notebook        (Gemini)           (Cloud Run)    GitHub
+ Model v1                         + Hot Reload   + Webhook
   │               │                  │              │
   v               v                  v              v
┌──────────────────────────────────────────────────────────┐
│              BACKEND API (FastAPI)                        │
│  Auth │ Notebooks │ Models │ Deployments │ GitHub │ WH   │
└──────────────────┬───────────────────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
      v            v            v
 PostgreSQL    GCS Storage   Cloud Services
   Users       Notebooks     ├─ Build
   Notebooks   Models        ├─ Run
   Models      Deploys       ├─ Logging
   Deploys     Code          └─ Gemini
   + github_repo_url
                              ┌──────────────┐
                              │   GitHub     │
                              │  Repository  │
                              │   Webhook    │
                              │   [push] ──┐ │
                              └────────────┼─┘
                                           │
                    Triggers auto-deploy ──┘

┌─────────────────────────────────────────────────────────┐
│           DEPLOYED SERVICE (Cloud Run)                   │
│                                                           │
│  FastAPI App (generated)                                 │
│  ├─ GET  /health                                         │
│  ├─ POST /predict      → Uses _model from GCS            │
│  └─ POST /admin/reload-model → Hot swap _model           │
│                                                           │
│  _model = load_model() from GCS on startup               │
│  Env vars: GCS_BUCKET, MODEL_GCS_PATH, ADMIN_API_KEY    │
└─────────────────────────────────────────────────────────┘
```

---

## Performance Metrics

| Operation | v3.0 (Old) | v4.0 (New) | Improvement |
|-----------|------------|------------|-------------|
| Model Update | 7 min | 10s | 42x faster |
| Downtime | Yes (rebuild) | Zero | 100% uptime |
| Image Size | 500MB | 150MB | 70% smaller |
| Model Rollback | Manual rebuild | 10s | Instant |
| Code Update (GitHub) | Manual | Auto-webhook | Automated |
| Initial Upload | Notebook only | Notebook + Model | Single request |

---

## Key Innovations

1. **GCS-Based Hot Reload**: Models stored in GCS, loaded on demand
2. **Multi-Stage Docker**: Smaller images, faster deploys
3. **Independent Versioning**: Update models without code changes
4. **Magic-Byte Validation**: Security beyond file extensions
5. **WebSocket Monitoring**: Real-time deployment feedback
6. **GitHub Bidirectional Sync**: Platform ↔ GitHub with webhooks
7. **Admin API Key**: Secure hot-reload authentication
8. **Single Upload Flow**: Notebook + Model in one request
9. **Auto-Code Generation**: GCS-aware wrappers based on model presence
10. **Webhook Auto-Deploy**: GitHub push triggers Cloud Run rebuild

---

## Testing Examples

### Example 1: Complete Flow (Notebook + Model Upload)
```bash
# 1. Upload notebook with model in single request
curl -X POST /api/v1/notebooks/upload \
  -F "notebook_file=@notebook.ipynb" \
  -F "model_file=@model_v1.pkl" \
  -H "Authorization: Bearer {token}"
# → { notebook_id: 1, model_version: { version: 1, is_active: true } }

# 2. Parse notebook
curl -X POST /api/v1/notebooks/1/parse \
  -H "Authorization: Bearer {token}"

# 3. Analyze with Gemini
curl -X POST /api/v1/notebooks/1/analyze \
  -H "Authorization: Bearer {token}"

# 4. Deploy to Cloud Run
curl -X POST /api/v1/deployments/one-click \
  -d '{"notebook_id":1,"name":"ml-api","region":"us-central1"}' \
  -H "Authorization: Bearer {token}"
# → { service_url: "https://ml-api-xyz.run.app", deployment_id: 1 }

# 5. Test prediction
curl -X POST https://ml-api-xyz.run.app/predict \
  -d '{"features":[1,2,3]}'
# → {"prediction": [0.89]}
```

### Example 2: Model Update (Hot Reload)
```bash
# 1. Replace model (auto-increments to v2, sets active)
curl -X PUT /api/v1/notebooks/1/models/replace \
  -F "file=@model_v2.pkl" \
  -F "accuracy=0.96" \
  -H "Authorization: Bearer {token}"
# → { version: 2, is_active: true }

# 2. Hot reload deployed service (10 seconds, zero downtime!)
curl -X POST /api/v1/deployments/1/reload-model \
  -H "Authorization: Bearer {token}"
# → { status: "reloaded", timestamp: "2025-11-22T..." }

# 3. Test v2 immediately
curl -X POST https://ml-api-xyz.run.app/predict \
  -d '{"features":[1,2,3]}'
# → {"prediction": [0.96]}  # New model!
```

### Example 3: GitHub Integration
```bash
# 1. Connect GitHub
curl /api/v1/github/oauth/authorize
# → { url: "https://github.com/login/oauth/authorize?..." }
# User authorizes, redirects to callback

# 2. Push to GitHub with webhook
curl -X POST /api/v1/github/create-repo \
  -d '{"notebook_id":1,"repo_name":"ml-deployment"}' \
  -H "Authorization: Bearer {token}"
# → {
#     repo_url: "https://github.com/user/ml-deployment",
#     repo_name: "ml-deployment"
#   }

# 3. User updates code on GitHub (e.g., git push)
# → GitHub webhook automatically triggers
# → Platform rebuilds and redeploys to Cloud Run
# → ~90 seconds later: updated app live

# 4. Check deployment status
curl /api/v1/deployments/1 \
  -H "Authorization: Bearer {token}"
# → { status: "deployed", github_repo_url: "https://github.com/user/ml-deployment" }
```
