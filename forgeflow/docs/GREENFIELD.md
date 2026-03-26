# ForgeFlow Greenfield Project Support

> Create new projects from scratch with intelligent scaffolding and optimal stack recommendations.

## Overview

ForgeFlow supports two project modes:

- **Greenfield**: New projects created from scratch
- **Brownfield**: Existing repositories with code

The Greenfield feature helps you bootstrap new projects with:
- Interactive wizard for project configuration
- Intelligent stack recommendations
- Complete project scaffolding
- ArgoCD/GitOps deployment manifests

## Quick Start

```bash
# Interactive wizard (recommended)
forgeflow init my-new-api

# Quick start with defaults
forgeflow init --quick my-service

# Guided mode with explanations
forgeflow init --guided my-app
```

## The Greenfield Workflow

### 1. Interactive Wizard

The wizard collects project requirements:

| Question | Options | Purpose |
|----------|---------|---------|
| Project Name | Any valid name | Directory and package naming |
| Application Type | web-app, api, microservice, cli-tool, library, fullstack | Structure template |
| Language | python, nodejs, typescript, go, java, rust | Primary language |
| Framework | Language-specific options | Framework boilerplate |
| Cloud Provider | aws, gcp, azure, on-prem, multi-cloud | Infrastructure templates |
| Kubernetes | yes/no | K8s manifests and ArgoCD |
| Database | postgresql, mysql, mongodb, redis, dynamodb, none | Database setup |
| Additional Services | auth, caching, messaging, monitoring, logging | Extra infrastructure |
| CI/CD | github-actions, gitlab-ci, jenkins, argocd | Pipeline configuration |
| Team Size | solo, small, medium, large | Scaling defaults |

### 2. Stack Suggestions

Based on your answers, ForgeFlow suggests:

- **Base Image**: Optimized container image
- **Framework Version**: Stable, well-supported version
- **Database Setup**: Driver and ORM recommendations
- **Infrastructure**: Terraform modules for your cloud
- **CI/CD Pipeline**: Complete workflow configuration
- **Monitoring Stack**: Prometheus, Grafana, etc.

Each suggestion includes reasoning to help you make informed decisions.

### 3. Project Scaffolding

ForgeFlow generates a complete project structure:

```
my-new-api/
├── src/
│   ├── main.py (or index.js, main.go, etc.)
│   └── __init__.py
├── tests/
│   └── test_main.py
├── docs/
├── config/
├── scripts/
├── infrastructure/
│   ├── argocd/
│   │   ├── appproject.yaml
│   │   ├── application-dev.yaml
│   │   ├── application-staging.yaml
│   │   └── application-prod.yaml
│   ├── k8s/
│   │   ├── base/
│   │   │   ├── kustomization.yaml
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   ├── configmap.yaml
│   │   │   └── hpa.yaml
│   │   └── overlays/
│   │       ├── dev/
│   │       ├── staging/
│   │       └── prod/
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt (or package.json)
├── .gitignore
├── .env.example
└── README.md
```

### 4. ArgoCD GitOps Deployment

For Kubernetes-enabled projects, ForgeFlow generates:

#### AppProject (`infrastructure/argocd/appproject.yaml`)
- RBAC configuration for admin and developer roles
- Namespace restrictions per environment
- Source repository whitelisting

#### Applications (`infrastructure/argocd/application-*.yaml`)
- Automated sync policies
- Self-healing enabled
- Prune and retry configurations

#### Kustomize Overlays
- Environment-specific configurations (dev, staging, prod)
- Resource limits per environment
- ConfigMap generation

## Usage Examples

### Create a Python FastAPI Service

```bash
forgeflow init my-api

# Answer wizard:
# - Type: api
# - Language: python
# - Framework: fastapi
# - Cloud: aws
# - Kubernetes: yes
# - Database: postgresql
# - Services: auth, monitoring
# - CI/CD: github-actions
# - Team: small
```

### Create a Go Microservice (Quick Mode)

```bash
forgeflow init --quick my-microservice

# Quick defaults:
# - Language: python (modify at prompt)
# - Type: api
# - Framework: based on language
# - Cloud: aws
# - Kubernetes: yes
# - Database: postgresql
```

### Create with Full Guidance

```bash
forgeflow init --guided my-app

# Provides detailed explanations at each step
# Best for learning the options
```

## Automatic Detection

When running `forgeflow run-all` on an empty directory, ForgeFlow automatically:

1. Detects it's a Greenfield project
2. Offers to run the initialization wizard
3. After scaffolding, optionally continues with the full pipeline

```bash
cd empty-folder
forgeflow run-all .

# Output:
# 📁 Empty or new directory detected!
# This looks like a Greenfield project...
# Would you like to run the Greenfield wizard now? [Y/n]
```

## Generated Files Reference

### Dockerfile
Multi-stage build optimized for your language:
- Build stage with dependencies
- Production stage with minimal image
- Health checks included
- Non-root user for security

### docker-compose.yml
Local development environment:
- Application service with hot reload
- Database service (if selected)
- Redis for caching (if selected)
- Prometheus/Grafana (if monitoring selected)

### Kubernetes Manifests
Production-ready configurations:
- Deployment with health probes
- Service with ClusterIP
- HorizontalPodAutoscaler
- ConfigMap for configuration

### CI/CD Workflows
GitHub Actions (or selected platform):
- Build and test on PR
- Security scanning
- Container image build
- Deployment to environments

## Customization

### Modifying Stack Suggestions

After reviewing suggestions, you can:
1. Accept as-is
2. Modify specific elements (base image, replicas)
3. Reject and restart the wizard

### Post-Scaffolding Modifications

All generated files are fully customizable:
```bash
# Modify dependencies
vim requirements.txt

# Adjust Terraform variables
vim infrastructure/terraform.tfvars

# Customize Kubernetes resources
vim infrastructure/k8s/base/deployment.yaml
```

## Integration with Brownfield Pipeline

After initialization, run the standard ForgeFlow pipeline:

```bash
cd my-new-api
forgeflow run-all .
```

This runs:
1. **discover** - Scan new project structure
2. **normalize** - Verify standard files
3. **docs** - Generate documentation
4. **generate** - Add any missing infrastructure
5. **review** - Code quality check
6. **test** - Run tests
7. **scan** - Security scan
8. **bridge** - Push to GitHub

## Best Practices

1. **Start with Wizard**: Even for quick projects, the wizard ensures nothing is missed
2. **Review Stack Suggestions**: Understand why each component is recommended
3. **Customize Kustomize Overlays**: Adjust resource limits per environment
4. **Version Control Immediately**: The scaffolder initializes git and creates initial commit
5. **Run Full Pipeline**: After init, run `forgeflow run-all` to validate and enhance

## Troubleshooting

### Wizard Not Starting
```bash
# Ensure rich is installed
pip install rich>=13.0
```

### Permission Errors
```bash
# Check directory permissions
chmod 755 /path/to/parent/directory
```

### Git Initialization Fails
```bash
# Git might not be installed
sudo apt install git

# Or configure git user
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

## See Also

- [Agent Architecture](./AGENT_ARCHITECTURE.md) - How agents work
- [Local Setup](../LOCAL_SETUP.md) - Development environment
- [README](../README.md) - Project overview
