# NotebookDeploy v4.0 - Frontend Implementation Guide

## Overview

NotebookDeploy is an AI-powered platform that converts Jupyter Notebooks into production-ready APIs deployed on Google Cloud Run. Users upload notebooks containing ML models, and the system automatically generates FastAPI backends with intelligent endpoints based on the model type.

**Key Features:**
- Jupyter notebook → FastAPI conversion with AI analysis
- Zero-downtime model updates (hot-reload in ~10s)
- GitHub bidirectional sync with webhooks
- Model versioning with rollback capability
- Real-time deployment monitoring via WebSocket
- Multi-stage Docker builds for optimized images

---

## System Architecture

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Frontend (React/Vue)            │
│  - Upload notebooks + models            │
│  - Real-time deployment status          │
│  - Model version management             │
│  - GitHub integration                   │
└──────┬──────────────────────────────────┘
       │ REST API + WebSocket
       ▼
┌─────────────────────────────────────────┐
│      Backend (FastAPI - Port 8080)      │
│  - Authentication (JWT)                 │
│  - Notebook parsing & validation        │
│  - Gemini AI analysis                   │
│  - Code generation                      │
│  - GitHub sync                          │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│         Google Cloud Platform           │
│  - Cloud Storage (notebooks, models)    │
│  - Cloud Build (Docker images)          │
│  - Cloud Run (deployed APIs)            │
│  - Artifact Registry (image storage)    │
└─────────────────────────────────────────┘
```

---

## Authentication Flow

### 1. User Registration
```
POST /api/v1/auth/register
{
  "email": "user@example.com",
  "password": "securepass123",
  "full_name": "John Doe"
}

Response:
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "created_at": "2025-11-22T10:00:00Z"
}
```

### 2. Login
```
POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "securepass123"
}

Response:
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Using Access Token
All subsequent requests require the token in headers:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Core Workflows

### Workflow 1: Upload & Deploy Notebook

**Steps:**
1. User uploads `.ipynb` file + trained model (`.pkl`, `.h5`, `.pt`, etc.)
2. Backend validates notebook and model file
3. Gemini AI analyzes notebook to extract model metadata
4. System generates FastAPI wrapper with intelligent endpoints
5. Cloud Build creates Docker image
6. Cloud Run deploys the API
7. User receives deployment URL

**API Flow:**

```javascript
// Step 1: Upload Notebook
const formData = new FormData();
formData.append('file', notebookFile); // .ipynb file

const uploadResponse = await fetch('/api/v1/notebooks/upload', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});

const notebook = await uploadResponse.json();
// { id: 42, name: "ml_classification_api", status: "uploaded", ... }

// Step 2: Upload Model
const modelFormData = new FormData();
modelFormData.append('file', modelFile); // .pkl, .h5, .pt, etc.

await fetch(`/api/v1/model-versions/${notebook.id}/upload`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: modelFormData
});

// Step 3: Deploy (triggers analysis + build + deployment)
const deployResponse = await fetch(`/api/v1/deployments/${notebook.id}`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    app_type: "fastapi"
  })
});

const deployment = await deployResponse.json();
// { id: 30, status: "building", build_id: "abc-123", ... }
```

**WebSocket Monitoring:**

```javascript
const ws = new WebSocket(`ws://localhost:8080/api/v1/deployments/${deployment.id}/logs`);

ws.onmessage = (event) => {
  const log = JSON.parse(event.data);
  console.log(log.message);
  // "Building Docker image..."
  // "Pushing to Artifact Registry..."
  // "Deploying to Cloud Run..."
  // "Deployment complete! URL: https://api-xxx.run.app"
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Deployment monitoring ended');
};
```

---

### Workflow 2: Model Versioning & Hot-Reload

**Upload New Model Version:**

```javascript
// Upload new model version
const formData = new FormData();
formData.append('file', newModelFile);

const versionResponse = await fetch(`/api/v1/model-versions/${notebookId}/upload`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  },
  body: formData
});

const version = await versionResponse.json();
// { id: 5, version: 2, notebook_id: 42, is_active: true, ... }
```

**Model updates trigger:**
1. Upload to GCS at `models/{userId}/{notebookId}/v{version}/model.pkl`
2. Automatic hot-reload API call to deployed service (zero-downtime)
3. Version tracking in database

**List Model Versions:**

```javascript
const versionsResponse = await fetch(`/api/v1/model-versions/${notebookId}`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});

const versions = await versionsResponse.json();
// [
//   { id: 5, version: 2, is_active: true, uploaded_at: "...", file_size: 180000 },
//   { id: 4, version: 1, is_active: false, uploaded_at: "...", file_size: 177000 }
// ]
```

**Rollback to Previous Version:**

```javascript
await fetch(`/api/v1/model-versions/${versionId}/activate`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`
  }
});
```

---

### Workflow 3: GitHub Integration

**Connect GitHub:**

```javascript
// Step 1: Redirect user to GitHub OAuth
window.location.href = '/api/v1/github/oauth/authorize';

// Step 2: After OAuth, user is redirected back with token
// Backend automatically stores refresh token for auto-renewal

// Step 3: Push notebook to GitHub
const pushResponse = await fetch(`/api/v1/github/push/${notebookId}`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    repo_name: "my-ml-api",
    is_private: true
  })
});

const repo = await pushResponse.json();
// {
//   repo_url: "https://github.com/username/my-ml-api",
//   default_branch: "main"
// }
```

**Bidirectional Sync:**
- **Platform → GitHub**: Auto-push on every deployment
- **GitHub → Platform**: Webhook triggers re-deployment on push to `main`

**GitHub Webhook Setup:**
1. Backend automatically creates webhook when connecting GitHub
2. Webhook URL: `https://your-backend.run.app/api/v1/webhooks/github`
3. Events: `push`
4. Secret: Auto-generated and verified via HMAC

---

## API Endpoints Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login and get JWT token |
| GET | `/api/v1/auth/me` | Get current user info |

### Notebooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/notebooks` | List user's notebooks |
| POST | `/api/v1/notebooks/upload` | Upload new notebook |
| GET | `/api/v1/notebooks/{id}` | Get notebook details |
| DELETE | `/api/v1/notebooks/{id}` | Delete notebook |
| GET | `/api/v1/notebooks/{id}/download` | Download generated code package |

### Deployments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/deployments/{notebook_id}` | Deploy notebook |
| GET | `/api/v1/deployments/{notebook_id}` | List deployments for notebook |
| GET | `/api/v1/deployments/{id}/status` | Get deployment status |
| WS | `/api/v1/deployments/{id}/logs` | Real-time deployment logs |
| DELETE | `/api/v1/deployments/{id}` | Delete deployment (tears down Cloud Run service) |

### Model Versions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/model-versions/{notebook_id}/upload` | Upload new model version |
| GET | `/api/v1/model-versions/{notebook_id}` | List model versions |
| POST | `/api/v1/model-versions/{id}/activate` | Activate specific version (hot-reload) |
| DELETE | `/api/v1/model-versions/{id}` | Delete model version |

### GitHub

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/github/oauth/authorize` | Redirect to GitHub OAuth |
| GET | `/api/v1/github/oauth/callback` | OAuth callback (auto-handled) |
| POST | `/api/v1/github/push/{notebook_id}` | Push notebook to GitHub |
| GET | `/api/v1/github/repos` | List user's GitHub repos |
| POST | `/api/v1/github/disconnect` | Disconnect GitHub account |

---

## Data Models

### Notebook
```typescript
interface Notebook {
  id: number;
  user_id: number;
  name: string;
  original_filename: string;
  notebook_path: string; // GCS path
  main_py_path: string; // Generated Python script
  requirements_txt_path: string;
  dependencies: string[]; // ["fastapi", "scikit-learn", "numpy"]
  github_repo_url: string | null;
  created_at: string;
  updated_at: string;
}
```

### Deployment
```typescript
interface Deployment {
  id: number;
  notebook_id: number;
  user_id: number;
  name: string;
  status: "pending" | "building" | "deploying" | "deployed" | "failed";
  build_id: string;
  image_url: string;
  service_url: string | null; // Deployed API URL
  region: string;
  error_message: string | null;
  build_logs_url: string;
  created_at: string;
  updated_at: string;
  deployed_at: string | null;
}
```

### ModelVersion
```typescript
interface ModelVersion {
  id: number;
  notebook_id: number;
  version: number;
  gcs_path: string;
  file_size: number;
  file_extension: string; // ".pkl", ".h5", ".pt"
  is_active: boolean;
  uploaded_at: string;
}
```

### Analysis
```typescript
interface Analysis {
  id: number;
  notebook_id: number;
  health_score: number; // 0-100
  issues: Issue[];
  recommendations: string[];
  cell_classifications: CellClassification[];
  model_info: ModelInfo;
  resource_estimates: {
    cpu: string;
    memory: string;
    estimated_cold_start_ms: number;
  };
}

interface Issue {
  severity: "critical" | "high" | "medium" | "low";
  category: "security" | "performance" | "compatibility" | "style";
  description: string;
  cell_index: number;
  suggestion: string;
}

interface ModelInfo {
  has_model: boolean;
  model_variable: string;
  model_type: string; // "sklearn.RandomForestClassifier"
  n_features: number;
  feature_names: string[];
  output_type: "classification" | "regression" | "clustering" | "other";
  n_classes: number | null;
  class_names: string[];
  prediction_method: string; // "predict", "predict_proba", etc.
  input_shape: number[];
  preprocessing_steps: string[];
}
```

---

## UI/UX Recommendations

### Dashboard Page
**Components:**
- List of notebooks with status badges
- Quick stats: Total notebooks, Active deployments, GitHub connected
- Recent activity timeline

**Notebook Card:**
```
┌─────────────────────────────────────┐
│ 📓 ml_classification_api            │
├─────────────────────────────────────┤
│ Status: ✅ Deployed                 │
│ URL: https://api-xxx.run.app       │
│ Model: v2 (scikit-learn)           │
│ GitHub: ✓ Synced                   │
│                                     │
│ [View] [Deploy] [Models] [Delete]  │
└─────────────────────────────────────┘
```

### Upload Flow
1. **Step 1: Upload Notebook**
   - Drag-and-drop or file picker for `.ipynb`
   - Show file validation (magic bytes check)
   - Preview notebook metadata

2. **Step 2: Upload Model**
   - Drag-and-drop for model file (`.pkl`, `.h5`, `.pt`, `.joblib`)
   - Show file size and type
   - Optional: Model description

3. **Step 3: Configure**
   - App type: FastAPI (default) or Streamlit
   - GitHub sync: Yes/No
   - Cloud Run settings: CPU, Memory

4. **Step 4: Deploy**
   - Real-time log streaming via WebSocket
   - Progress indicator: Building → Pushing → Deploying
   - Success: Show API URL with "Copy" button

### Deployment Monitoring
**Real-time Log Panel:**
```
┌─────────────────────────────────────┐
│ Deployment Logs                     │
├─────────────────────────────────────┤
│ ⏳ Analyzing notebook...            │
│ ✓ Health score: 95/100              │
│ ⏳ Building Docker image...         │
│ ✓ Build complete (2m 15s)           │
│ ⏳ Deploying to Cloud Run...        │
│ ✓ Deployed successfully!            │
│                                     │
│ 🚀 API URL:                         │
│ https://ml-api-xxx.run.app [Copy]  │
└─────────────────────────────────────┘
```

### Model Versions Page
**Version Timeline:**
```
v2 (Active) ────●────────────────
               │
               │ 180 KB, uploaded 2 hours ago
               │ [Rollback] [Download] [Delete]
               │
v1 ────────────●────────────────
               │
               │ 177 KB, uploaded 1 day ago
               │ [Activate] [Download] [Delete]
```

### GitHub Integration
**Connection Flow:**
1. Show "Connect GitHub" button if not connected
2. After OAuth: Show connected username with avatar
3. "Push to GitHub" creates new repo or updates existing
4. Show sync status: "Last synced 5 minutes ago"

---

## Error Handling

### Common Error Responses

**401 Unauthorized:**
```json
{
  "detail": "Invalid authentication credentials"
}
```
→ Redirect to login, clear stored token

**400 Bad Request:**
```json
{
  "detail": "Invalid file format. Expected .ipynb"
}
```
→ Show user-friendly error message

**500 Internal Server Error:**
```json
{
  "detail": "Deployment failed: Cloud Build error"
}
```
→ Show error with "Retry" button

### WebSocket Reconnection
```javascript
let reconnectAttempts = 0;
const maxReconnects = 5;

function connectWebSocket() {
  const ws = new WebSocket(wsUrl);

  ws.onclose = () => {
    if (reconnectAttempts < maxReconnects) {
      setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket();
      }, 2000 * reconnectAttempts);
    }
  };

  ws.onopen = () => {
    reconnectAttempts = 0;
  };
}
```

---

## Environment Variables (Frontend)

```env
VITE_API_BASE_URL=http://localhost:8080
VITE_WS_BASE_URL=ws://localhost:8080
VITE_GITHUB_ENABLED=true
```

---

## Testing Checklist

### Authentication
- [ ] Register new user
- [ ] Login with valid credentials
- [ ] Login with invalid credentials (show error)
- [ ] Token refresh on 401 response
- [ ] Logout clears token

### Notebook Upload
- [ ] Upload valid `.ipynb` file
- [ ] Reject non-notebook files
- [ ] Show upload progress
- [ ] Handle large files (>10MB)

### Model Upload
- [ ] Upload `.pkl` file
- [ ] Upload `.h5` file (Keras)
- [ ] Upload `.pt` file (PyTorch)
- [ ] Show file validation errors

### Deployment
- [ ] Deploy notebook (watch logs in real-time)
- [ ] Deployment succeeds and shows URL
- [ ] Deployment fails and shows error
- [ ] WebSocket reconnects on disconnect
- [ ] Cancel deployment (if still building)

### Model Versioning
- [ ] Upload new model version
- [ ] List all versions
- [ ] Activate previous version (rollback)
- [ ] Delete old version

### GitHub Integration
- [ ] Connect GitHub account
- [ ] Push notebook to new repo
- [ ] Show repo URL and link
- [ ] Webhook triggers re-deployment on push
- [ ] Disconnect GitHub account

---

## Advanced Features to Implement

### 1. Live API Testing
Add "Test API" panel after deployment:
```javascript
// Example: Test deployed model prediction
const testPrediction = async () => {
  const response = await fetch(`${deploymentUrl}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sepal_length: 5.1,
      sepal_width: 3.5,
      petal_length: 1.4,
      petal_width: 0.2
    })
  });

  const result = await response.json();
  // { prediction: "setosa", confidence: 0.98, probabilities: {...} }
};
```

### 2. Deployment Analytics
- Request count per day
- Average response time
- Error rate
- Model version performance comparison

### 3. Collaborative Features
- Share notebooks with other users (read/write permissions)
- Team workspaces
- Deployment approvals for production

### 4. Cost Estimation
Show estimated GCP costs based on:
- Container CPU/Memory allocation
- Expected request volume
- Storage usage

---

## API Client Example (React)

```typescript
// api/client.ts
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

// Add auth token to all requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const notebookApi = {
  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/v1/notebooks/upload', formData);
  },

  list: () => api.get('/api/v1/notebooks'),

  deploy: (notebookId: number) =>
    api.post(`/api/v1/deployments/${notebookId}`, { app_type: 'fastapi' }),

  getDeploymentLogs: (deploymentId: number) => {
    const wsUrl = `${import.meta.env.VITE_WS_BASE_URL}/api/v1/deployments/${deploymentId}/logs`;
    return new WebSocket(wsUrl);
  },
};

export const modelApi = {
  upload: (notebookId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/api/v1/model-versions/${notebookId}/upload`, formData);
  },

  list: (notebookId: number) =>
    api.get(`/api/v1/model-versions/${notebookId}`),

  activate: (versionId: number) =>
    api.post(`/api/v1/model-versions/${versionId}/activate`),
};

export const githubApi = {
  authorize: () => {
    window.location.href = `${import.meta.env.VITE_API_BASE_URL}/api/v1/github/oauth/authorize`;
  },

  push: (notebookId: number, repoName: string, isPrivate: boolean) =>
    api.post(`/api/v1/github/push/${notebookId}`, {
      repo_name: repoName,
      is_private: isPrivate,
    }),

  listRepos: () => api.get('/api/v1/github/repos'),
};
```

---

## Security Considerations

1. **JWT Token Storage**: Use `httpOnly` cookies or secure localStorage
2. **File Upload Validation**: Check file types and sizes on frontend before upload
3. **CORS**: Backend already configured with `ALLOWED_ORIGINS`
4. **Rate Limiting**: Show user-friendly message if rate-limited
5. **HTTPS Only**: Ensure production uses HTTPS for API calls

---

## Support & Troubleshooting

### Common Issues

**1. Deployment stuck at "Building"**
- Check build logs URL for errors
- Common cause: Missing dependencies in notebook

**2. WebSocket connection fails**
- Check CORS settings
- Verify WebSocket URL uses `ws://` (dev) or `wss://` (prod)

**3. GitHub OAuth fails**
- Verify callback URL in GitHub App settings
- Check webhook secret is set correctly

**4. Model upload fails**
- Ensure file size < 100MB
- Check file extension is supported

---

## Production Deployment

### Frontend
```bash
# Build
npm run build

# Deploy to Vercel/Netlify/Cloud Storage
vercel deploy

# Environment Variables (Production)
VITE_API_BASE_URL=https://codematics-be-xxx.run.app
VITE_WS_BASE_URL=wss://codematics-be-xxx.run.app
```

### Backend
Already deployed on Cloud Run at: `https://codematics-be-860155021919.us-central1.run.app`

---

## API Base URL

**Development:** `http://localhost:8080`
**Production:** `https://codematics-be-860155021919.us-central1.run.app`

---

## Questions?

Contact the backend team or refer to:
- Backend Swagger docs: `https://api-url/docs`
- Repository README: `/README.md`
- PRD: `/new_prd.pdf`