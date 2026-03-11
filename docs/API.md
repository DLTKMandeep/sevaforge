# ForgeFlow REST API Documentation

ForgeFlow provides a REST API for containerized and cloud deployments, enabling programmatic access to all ForgeFlow commands.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All API endpoints (except `/health`) require authentication when `FORGEFLOW_API_KEY_REQUIRED=true`.

### API Key Authentication

Include the API key in the request header:

```bash
curl -H "X-API-Key: your-api-key" https://forgeflow.example.com/api/v1/status
```

### Generating an API Key

```bash
# Generate a secure API key
openssl rand -hex 32
```

## Endpoints

### Health Check

**GET** `/health`

Health check for container orchestration. No authentication required.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "mode": "local",
  "timestamp": "2026-02-08T12:00:00Z"
}
```

---

### Service Status

**GET** `/api/v1/status`

Get service status and configuration.

**Response:**
```json
{
  "status": "running",
  "version": "0.1.0",
  "mode": "local",
  "active_tasks": 0,
  "uptime_seconds": 3600.5,
  "config": {
    "api_key_required": true,
    "max_repo_size_mb": 100,
    "task_timeout": 300
  }
}
```

---

### Discover

**POST** `/api/v1/discover`

Run discovery on repository to analyze structure and components.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "git_url": null
}
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | No* | Local path to repository |
| `git_url` | string | No* | Git URL to clone |

*Either `path` or `git_url` must be provided.

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/discover \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"git_url": "https://github.com/user/repo.git"}'
```

**Response:**
```json
{
  "status": "success",
  "command": "discover",
  "summary": "Discovered 45 files across 3 languages",
  "data": {
    "files_count": 45,
    "languages": ["python", "javascript", "yaml"],
    "components": ["api", "tests", "config"]
  },
  "findings": [...],
  "timestamp": "2026-02-08T12:00:00Z",
  "execution_time_ms": 150
}
```

---

### Normalize

**POST** `/api/v1/normalize`

Normalize and standardize repository structure.

**Request Body:**
```json
{
  "path": "/repos/my-app"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/normalize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app"}'
```

---

### Scan

**POST** `/api/v1/scan`

Run security vulnerability scan on repository.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "severity": "medium"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `git_url` | string | - | Git URL to clone |
| `severity` | string | "medium" | Minimum severity threshold: low, medium, high, critical |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "severity": "high"}'
```

**Response:**
```json
{
  "status": "warning",
  "command": "scan",
  "summary": "Found 3 vulnerabilities (1 high, 2 medium)",
  "data": {
    "vulnerabilities_count": 3,
    "by_severity": {
      "high": 1,
      "medium": 2
    }
  },
  "findings": [
    {
      "type": "hardcoded-secret",
      "severity": "high",
      "file": "config.py",
      "line": 15,
      "message": "Possible hardcoded API key detected"
    }
  ],
  "timestamp": "2026-02-08T12:00:00Z"
}
```

---

### Docs

**POST** `/api/v1/docs`

Generate documentation and diagrams.

**Request Body:**
```json
{
  "path": "/repos/my-app"
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/docs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app"}'
```

---

### Generate

**POST** `/api/v1/generate`

Generate deployment infrastructure artifacts.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "stack": "kubernetes"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `git_url` | string | - | Git URL to clone |
| `stack` | string | "auto" | Deployment stack: auto, docker, kubernetes, terraform, helm |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "stack": "terraform"}'
```

**Response:**
```json
{
  "status": "success",
  "command": "generate",
  "summary": "Generated 12 deployment artifacts",
  "data": {
    "generated_files": [
      "Dockerfile",
      "docker-compose.yml",
      "terraform/main.tf",
      "terraform/variables.tf",
      ".github/workflows/forgeflow-ci.yml"
    ],
    "detected_language": "python"
  },
  "timestamp": "2026-02-08T12:00:00Z"
}
```

---

### Review

**POST** `/api/v1/review`

Run code review and quality analysis.

**Request Body:**
```json
{
  "path": "/repos/my-app"
}
```

---

### Test

**POST** `/api/v1/test`

Run tests via CI/CD pipeline.

**Request Body:**
```json
{
  "path": "/repos/my-app"
}
```

---

### Bridge

**POST** `/api/v1/bridge`

Bridge to GitHub (push, PR, sync).

**Request Body:**
```json
{
  "repo": "owner/repo",
  "branch": "feature-branch",
  "operation": "push",
  "message": "Update from ForgeFlow",
  "pr_title": "Feature: Add new functionality",
  "pr_body": "This PR adds..."
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `repo` | string | - | GitHub repository (owner/repo) |
| `branch` | string | - | Branch name |
| `operation` | string | "status" | Operation: init, push, pr, branch, status |
| `message` | string | "Update from ForgeFlow" | Commit message |
| `pr_title` | string | - | Pull request title |
| `pr_body` | string | - | Pull request body |

---

### IAC — Infrastructure as Code

**POST** `/api/v1/iac`

Generate Infrastructure as Code artifacts (Terraform, Dockerfile, docker-compose, Pulumi). Added in v2.1.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "provider": "aws"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `provider` | string | "aws" | Cloud provider: aws, gcp, azure |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/iac \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "provider": "aws"}'
```

---

### CD — Continuous Deployment

**POST** `/api/v1/cd`

Generate Continuous Deployment configuration (ArgoCD Application manifests, Kustomize overlays, Helm values). Added in v2.1.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "tool": "argocd"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `tool` | string | "argocd" | CD tool: argocd, kustomize, helm |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/cd \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "tool": "argocd"}'
```

---

### CI — Continuous Integration

**POST** `/api/v1/ci`

Generate Continuous Integration pipeline configuration (GitHub Actions, GitLab CI, Jenkins). Added in v2.1.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "platform": "github"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `platform` | string | "github" | CI platform: github, gitlab, jenkins |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/ci \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "platform": "github"}'
```

---

### E2E — End-to-End Testing

**POST** `/api/v1/e2e`

Scaffold end-to-end test configuration and test stubs (Playwright, Cypress). Added in v2.1.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "framework": "playwright"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `framework` | string | "playwright" | E2E framework: playwright, cypress |

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/e2e \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"path": "/repos/my-app", "framework": "playwright"}'
```

---

### Run All (Full Pipeline)

**POST** `/api/v1/run-all`

Run full pipeline (v2.1): discover → normalize → docs → iac → cd → ci → e2e → review → test → scan → bridge.

**Request Body:**
```json
{
  "path": "/repos/my-app",
  "include_post_merge": false,
  "async_execution": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | - | Local path to repository |
| `git_url` | string | - | Git URL to clone |
| `include_post_merge` | bool | false | Include post-merge stages (deploy, monitor) |
| `async_execution` | bool | false | Run asynchronously and return task ID |

**Async Response:**
```json
{
  "status": "accepted",
  "command": "run-all",
  "summary": "Pipeline started with task ID: abc123",
  "data": {
    "task_id": "abc123"
  },
  "timestamp": "2026-02-08T12:00:00Z"
}
```

---

### Get Task Status

**GET** `/api/v1/tasks/{task_id}`

Get status of an async task.

**Example:**
```bash
curl http://localhost:8000/api/v1/tasks/abc123 \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "status": "completed",
  "started_at": "2026-02-08T12:00:00Z",
  "result": {
    "status": "success",
    "summary": "Pipeline completed successfully"
  }
}
```

---

### Upload Repository

**POST** `/api/v1/upload`

Upload a repository as a zip/tar archive.

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@my-repo.zip"
```

**Response:**
```json
{
  "status": "uploaded",
  "path": "/tmp/forgeflow/abc123/repo",
  "message": "Repository uploaded successfully. Use this path in subsequent API calls."
}
```

---

## Error Responses

All errors follow a consistent format:

```json
{
  "status": "error",
  "error": "Error message description",
  "timestamp": "2026-02-08T12:00:00Z"
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid or missing API key |
| 404 | Not Found - Resource not found |
| 408 | Request Timeout - Operation timed out |
| 500 | Internal Server Error |

---

## Rate Limiting

Default rate limits (configurable via environment variables):

| Endpoint | Limit |
|----------|-------|
| `/health` | Unlimited |
| `/api/v1/status` | 100/minute |
| All other endpoints | 30/minute |

---

## Interactive Documentation

When the API server is running, access interactive documentation at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

## SDK Examples

### Python

```python
import requests

API_URL = "http://localhost:8000/api/v1"
API_KEY = "your-api-key"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# Run discovery
response = requests.post(
    f"{API_URL}/discover",
    headers=HEADERS,
    json={"git_url": "https://github.com/user/repo.git"}
)
print(response.json())

# Run full pipeline asynchronously
response = requests.post(
    f"{API_URL}/run-all",
    headers=HEADERS,
    json={
        "path": "/repos/my-app",
        "async_execution": True
    }
)
task_id = response.json()["data"]["task_id"]

# Check task status
status = requests.get(
    f"{API_URL}/tasks/{task_id}",
    headers=HEADERS
).json()
print(status)
```

### cURL

```bash
#!/bin/bash
API_URL="http://localhost:8000/api/v1"
API_KEY="your-api-key"

# Discover
curl -X POST "$API_URL/discover" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"git_url": "https://github.com/user/repo.git"}'

# Security scan with high severity
curl -X POST "$API_URL/scan" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"path": "/repos/my-app", "severity": "high"}'

# Generate Kubernetes artifacts
curl -X POST "$API_URL/generate" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"path": "/repos/my-app", "stack": "kubernetes"}'
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FORGEFLOW_API_KEY` | - | API key for authentication |
| `FORGEFLOW_API_KEY_REQUIRED` | `true` | Whether API key is required |
| `FORGEFLOW_MODE` | `local` | Deployment mode: local, hybrid |
| `FORGEFLOW_MAX_REPO_SIZE_MB` | `100` | Maximum repository size in MB |
| `FORGEFLOW_TASK_TIMEOUT` | `300` | Task timeout in seconds |
| `FORGEFLOW_TEMP_DIR` | `/tmp/forgeflow` | Temporary directory for cloned repos |
| `GH_TOKEN` | - | GitHub token for bridge functionality |
