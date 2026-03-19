# ForgeFlow Deployment Guide

This guide covers deploying ForgeFlow as a containerized service.

## Table of Contents

- [Quick Start](#quick-start)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [Security](#security)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Using Docker Compose (Simplest)

```bash
# Clone the repository
git clone https://github.com/your-org/forgeflow.git
cd forgeflow

# Start the service
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Using Docker

```bash
# Build the image
docker build -t forgeflow:latest .

# Run the container
docker run -d \
  --name forgeflow \
  -p 8000:8000 \
  -e FORGEFLOW_API_KEY_REQUIRED=false \
  forgeflow:latest
```

---

## Docker Deployment

### Building the Image

```bash
# Standard build
docker build -t forgeflow:latest .

# Build with specific Python version
docker build --build-arg PYTHON_VERSION=3.11 -t forgeflow:latest .
```

### Running with Docker Compose

#### Development Mode

```bash
# Start without API key requirement
FORGEFLOW_API_KEY_REQUIRED=false docker-compose up -d
```

#### Production Mode

```bash
# Generate API key
export FORGEFLOW_API_KEY=$(openssl rand -hex 32)
echo "API Key: $FORGEFLOW_API_KEY"

# Generate GitHub token at https://github.com/settings/tokens
export GH_TOKEN="your-github-token"

# Start with all services including Redis
docker-compose --profile production up -d
```

### Docker Compose Services

| Service | Description | Port |
|---------|-------------|------|
| `forgeflow` | Main API server | 8000 |
| `redis` | Task queue (production profile) | 6379 |
| `celery-worker` | Async task worker (production profile) | - |

### Volume Mounts

```yaml
volumes:
  - ./repos:/repos:rw        # Mount local repositories
  - forgeflow-temp:/tmp/forgeflow  # Temporary storage
```

---

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (1.24+)
- kubectl configured
- Ingress controller (nginx recommended)
- cert-manager (optional, for TLS)

### Quick Deploy

```bash
# Apply all manifests using kustomize
kubectl apply -k k8s/

# Or apply individually
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

### Configure Secrets

```bash
# Generate API key
API_KEY=$(openssl rand -hex 32)
echo "API Key: $API_KEY"

# Create secret (replace placeholders)
kubectl create secret generic forgeflow-secrets \
  --namespace forgeflow \
  --from-literal=FORGEFLOW_API_KEY="$API_KEY" \
  --from-literal=GH_TOKEN="your-github-token"
```

### Update Ingress

Edit `k8s/ingress.yaml` to set your domain:

```yaml
spec:
  tls:
  - hosts:
    - forgeflow.yourdomain.com  # Your domain
    secretName: forgeflow-tls
  rules:
  - host: forgeflow.yourdomain.com  # Your domain
```

### Verify Deployment

```bash
# Check pods
kubectl get pods -n forgeflow

# Check service
kubectl get svc -n forgeflow

# Check ingress
kubectl get ingress -n forgeflow

# Port forward for local testing
kubectl port-forward svc/forgeflow 8000:80 -n forgeflow

# Test health
curl http://localhost:8000/health
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment forgeflow --replicas=5 -n forgeflow

# HPA is configured automatically - check status
kubectl get hpa -n forgeflow
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FORGEFLOW_MODE` | `local` | Deployment mode: `local` or `hybrid` |
| `FORGEFLOW_API_KEY` | - | API key for authentication |
| `FORGEFLOW_API_KEY_REQUIRED` | `true` | Whether API key is required |
| `FORGEFLOW_MAX_REPO_SIZE_MB` | `100` | Maximum repository size |
| `FORGEFLOW_TASK_TIMEOUT` | `300` | Task timeout in seconds |
| `FORGEFLOW_TEMP_DIR` | `/tmp/forgeflow` | Temporary directory |
| `GH_TOKEN` | - | GitHub token for bridge operations |

### ConfigMap (Kubernetes)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: forgeflow-config
data:
  FORGEFLOW_MODE: "local"
  FORGEFLOW_API_KEY_REQUIRED: "true"
  FORGEFLOW_MAX_REPO_SIZE_MB: "100"
```

---

## Security

### API Key Authentication

1. **Generate a strong API key:**
   ```bash
   openssl rand -hex 32
   ```

2. **Set the API key:**
   ```bash
   # Docker
   export FORGEFLOW_API_KEY=your-generated-key
   
   # Kubernetes
   kubectl create secret generic forgeflow-secrets \
     --from-literal=FORGEFLOW_API_KEY=your-generated-key \
     -n forgeflow
   ```

3. **Use in requests:**
   ```bash
   curl -H "X-API-Key: your-api-key" http://forgeflow.example.com/api/v1/status
   ```

### TLS/HTTPS

#### With cert-manager (Kubernetes)

```yaml
annotations:
  cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - forgeflow.example.com
    secretName: forgeflow-tls
```

#### With Docker (using reverse proxy)

```yaml
# docker-compose.override.yml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - forgeflow
```

### Network Policies (Kubernetes)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: forgeflow-network-policy
  namespace: forgeflow
spec:
  podSelector:
    matchLabels:
      app: forgeflow
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
```

---

## Monitoring

### Health Checks

```bash
# Liveness probe
curl http://localhost:8000/health

# Detailed status
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/status
```

### Metrics (Prometheus)

Add Prometheus annotations to your deployment:

```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

### Logging

```bash
# Docker
docker logs forgeflow-api -f

# Kubernetes
kubectl logs -f deployment/forgeflow -n forgeflow
```

---

## Troubleshooting

### Common Issues

#### Container Won't Start

```bash
# Check logs
docker logs forgeflow-api

# Check resource limits
kubectl describe pod -l app=forgeflow -n forgeflow
```

#### API Returns 401 Unauthorized

```bash
# Verify API key is set
kubectl get secret forgeflow-secrets -n forgeflow -o yaml

# Test without auth (if allowed)
curl http://localhost:8000/health
```

#### GitHub Bridge Fails

```bash
# Verify GH_TOKEN is set
docker exec forgeflow-api gh auth status

# Check token permissions
# Token needs: repo, read:org, workflow
```

#### Repository Clone Timeout

```bash
# Increase timeout
export FORGEFLOW_TASK_TIMEOUT=600

# Or use pre-cloned repositories
curl -X POST http://localhost:8000/api/v1/discover \
  -d '{"path": "/repos/my-app"}'
```

### Debug Mode

```bash
# Enable debug logging
docker run -e LOG_LEVEL=DEBUG forgeflow:latest

# Access shell
docker exec -it forgeflow-api /bin/bash
```

---

## Architecture

```
┌─────────────────┐
│   Client/CI      │
│  (REST calls)   │
└────────┬────────┘
        │
        ▼
┌─────────────────┐
│  Ingress/LB     │
└────────┬────────┘
        │
        ▼
┌─────────────────┐
│  ForgeFlow API  │ ←── FastAPI Server
│  (Port 8000)    │
└────────┬────────┘
        │
        ▼
┌─────────────────┐
│ Mission Control │ ←── Orchestrates agents
└────────┬────────┘
        │
        ▼
┌─────────────────┐
│   MCP Servers   │ ←── Protocol layer
└────────┬────────┘
        │
        ▼
┌─────────────────┐
│     Agents      │ ←── Business logic
└─────────────────┘
```

---

## Related Documentation

- [API Reference](API.md)
- [Agent Architecture](AGENT_ARCHITECTURE.md)
- [Local Setup](../LOCAL_SETUP.md)
- [README](../README.md)
