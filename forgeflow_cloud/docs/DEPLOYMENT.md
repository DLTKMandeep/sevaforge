# ForgeFlow Deployment Guide

Deployment options and setup instructions for ForgeFlow.

---

## Deployment Modes Overview

ForgeFlow supports three deployment modes to fit different use cases:

| Mode | Processing | Internet Required | Best For |
|------|------------|-------------------|----------|
| **Local** | All local | No | Individual developers, offline work |
| **Hybrid** | Mixed | Partial | Teams, enhanced security scanning |
| **Cloud** | All cloud | Yes | Enterprise, centralized management |

---

## Local Mode Deployment

### Setup

```bash
# Clone repository
git clone https://github.com/forgeflow/forgeflow.git
cd forgeflow

# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Verify
forgeflow doctor
```

### Configuration

```yaml
# config/forgeflow-config.yaml
mode: local

pipeline:
  sequence:
    - discover
    - normalize
    - docs
    - generate
    - review
    - test
    - scan
```

### Usage

```bash
forgeflow discover --path ./my-repo
forgeflow audit --path ./my-repo
```

---

## Hybrid Mode Deployment

### Prerequisites

- Python 3.9+
- Internet access for cloud integrations
- API keys for services:
  - GitHub Token (`GITHUB_TOKEN`)
  - Snyk API Key (`SNYK_API_KEY`) - optional
  - Cloud provider credentials - optional

### Setup

```bash
# Standard installation
git clone https://github.com/forgeflow/forgeflow.git
cd forgeflow
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export GITHUB_TOKEN=ghp_xxx
export SNYK_API_KEY=xxx  # Optional
```

### Configuration

```yaml
# config/forgeflow-config.yaml
mode: hybrid

hybrid:
  local_mcps:
    discovery-mcp-server:
      type: local
    normalize-mcp-server:
      type: local
    deployment-mcp-server:
      type: local

  public_mcps:
    github-mcp-server:
      type: public
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]

    security-mcp-server:
      type: public
      integrations:
        snyk:
          enabled: true
          api_key_env: "SNYK_API_KEY"
```

### Usage

```bash
forgeflow --mode hybrid scan --path ./my-repo
forgeflow --mode hybrid bridge --repo owner/repo
```

---

## Cloud Mode Deployment

### Prerequisites

- ForgeFlow API key
- Internet access

### Setup

```bash
# Install CLI only (thin client)
pip install forgeflow

# Set API key
export FORGEFLOW_API_KEY=your_api_key
```

### Configuration

```yaml
# config/forgeflow-config.yaml
mode: cloud

public:
  api_base_url: "https://api.forgeflow.io/v1"

  auth:
    type: api_key
    api_key_env: "FORGEFLOW_API_KEY"

  connection:
    timeout: 60
    retries: 3
```

### Usage

```bash
forgeflow --mode cloud discover --path ./my-repo
forgeflow --mode cloud audit --path ./my-repo
```

---

## Docker Deployment

### Build Image

```bash
docker build -t forgeflow:latest .
```

### Run Container

```bash
# Mount repository for scanning
docker run -v $(pwd)/my-repo:/app/repo forgeflow:latest discover --path /app/repo

# With environment variables
docker run \
  -e GITHUB_TOKEN=$GITHUB_TOKEN \
  -v $(pwd)/my-repo:/app/repo \
  forgeflow:latest --mode hybrid scan --path /app/repo
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  forgeflow:
    build: .
    volumes:
      - ./repos:/app/repos
      - ./config:/app/config
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - FORGEFLOW_MODE=hybrid
```

---

## Kubernetes Deployment

### Deployment Manifest

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: forgeflow
spec:
  replicas: 1
  selector:
    matchLabels:
      app: forgeflow
  template:
    metadata:
      labels:
        app: forgeflow
    spec:
      containers:
      - name: forgeflow
        image: forgeflow:latest
        env:
        - name: FORGEFLOW_MODE
          value: "cloud"
        - name: FORGEFLOW_API_KEY
          valueFrom:
            secretKeyRef:
              name: forgeflow-secrets
              key: api-key
        volumeMounts:
        - name: config
          mountPath: /app/config
      volumes:
      - name: config
        configMap:
          name: forgeflow-config
```

### Secret

```bash
kubectl create secret generic forgeflow-secrets \
  --from-literal=api-key=your_api_key
```

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/forgeflow.yml
name: ForgeFlow Analysis

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install ForgeFlow
      run: |
        pip install -r requirements.txt

    - name: Run Security Scan
      run: |
        python -m cli.forgeflow scan --severity high

    - name: Run Audit
      run: |
        python -m cli.forgeflow audit
```

### GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - analyze

forgeflow-scan:
  stage: analyze
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - python -m cli.forgeflow scan --severity high
  rules:
    - if: $CI_MERGE_REQUEST_ID
```

---

## Environment Variables Reference

| Variable | Mode | Description |
|----------|------|-------------|
| `FORGEFLOW_MODE` | All | Default mode (local/hybrid/cloud) |
| `FORGEFLOW_API_KEY` | Cloud | Cloud API authentication |
| `GITHUB_TOKEN` | Hybrid | GitHub API access |
| `SNYK_API_KEY` | Hybrid | Snyk security scanning |
| `AWS_REGION` | Hybrid | AWS deployment region |
| `AWS_PROFILE` | Hybrid | AWS credentials profile |
| `GCP_PROJECT` | Hybrid | Google Cloud project |
| `AZURE_SUBSCRIPTION_ID` | Hybrid | Azure subscription |

---

## Production Recommendations

1. **Use Hybrid Mode** for security-critical projects
2. **Enable all security integrations** (Snyk, Trivy)
3. **Set severity threshold to high** for production scans
4. **Use secret management** for API keys
5. **Integrate with CI/CD** for automated scanning
6. **Review generated configs** before deployment
