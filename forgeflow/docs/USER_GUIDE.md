# ForgeFlow User Guide

Complete guide to using ForgeFlow for platform engineering automation.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Deployment Modes](#deployment-modes)
3. [Pipeline Walkthrough](#pipeline-walkthrough)
4. [Command Deep Dive](#command-deep-dive)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- **Python 3.9+** - Required for running ForgeFlow
- **Git** - For version control operations
- **GitHub CLI (`gh`)** - Required for bridge operations

### Installation

```bash
# Clone the repository
git clone https://github.com/forgeflow/forgeflow.git
cd forgeflow

# Option 1: Use setup script
./scripts/setup_mac.sh

# Option 2: Manual installation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### First Run

```bash
# Verify installation
python3 scripts/test_installation.py

# Run doctor to check system health
forgeflow doctor

# Discover a repository
forgeflow discover --path /path/to/your/repo
```

---

## Deployment Modes

### Local Mode (Default)

All processing happens on your machine. No internet required.

```bash
forgeflow discover --path ./my-repo
# or explicitly
forgeflow --mode local discover --path ./my-repo
```

**Best for:**
- Offline development
- Full data privacy
- Testing and development

### Hybrid Mode

Combines local MCPs with cloud services for enhanced capabilities.

```bash
forgeflow --mode hybrid scan --path ./my-repo
```

**Features:**
- Local discovery and normalization
- Cloud-enhanced security scanning (Snyk, Trivy)
- GitHub Actions integration
- Cloud deployment APIs

**Configuration:**
```yaml
# config/forgeflow-config.yaml
mode: hybrid

hybrid:
  public_mcps:
    security-mcp-server:
      integrations:
        snyk:
          enabled: true
          api_key_env: "SNYK_API_KEY"
```

### Cloud Mode

Thin client mode - all processing in the cloud.

```bash
export FORGEFLOW_API_KEY=your_key
forgeflow --mode cloud discover --path ./my-repo
```

**Best for:**
- Enterprise teams
- Centralized management
- Consistent configurations

---

## Pipeline Walkthrough

### Full Pipeline Sequence

```
Analyse:  DISCOVER → NORMALIZE → DOCS
Build:    IAC → CD → CI → E2E
Quality:  REVIEW → TEST → SCAN
Ship:     DEPLOY-INTENT → DEPLOY-DESIGN → DEPLOY-VALIDATE → SECRETS → LIFECYCLE → BRIDGE
```

The **Ship** phase includes a pre-push deployment pipeline:
- **deploy-intent** — interviews you once about cloud, region, compute, SLOs, cost limits
- **deploy-design** — fans out to 7 persona agents (infra, cluster, app, secrets, observability, security, cost) in 3 parallel layers
- **deploy-validate** — cross-checks all artifacts; blocks push on failure

### Running the Full Pipeline

```bash
# Run all stages up to bridge
forgeflow run-all ./my-repo

# Include post-merge stages
forgeflow run-all ./my-repo --include-post-merge
```

### Stage-by-Stage

#### 1. Discovery
```bash
forgeflow discover --path ./my-repo
```
Scans the repository and creates an inventory in `.forgeflow/inventory.json`.

#### 2. Normalization
```bash
forgeflow normalize --path ./my-repo
```
Checks for standard files (README, LICENSE, .gitignore) and suggests improvements.

#### 3. Documentation
```bash
forgeflow docs --path ./my-repo
```
Generates architecture diagrams and documentation in `docs/`.

#### 4. Generation
```bash
forgeflow generate --path ./my-repo --stack kubernetes
```
Generates Terraform, Docker, and CI/CD configurations.

#### 5. Code Review
```bash
forgeflow review --path ./my-repo
```
Analyzes Git history and checks code quality.

#### 6. Testing
```bash
forgeflow test --path ./my-repo
```
Identifies test framework and runs available tests.

#### 7. Security Scan
```bash
forgeflow scan --path ./my-repo --severity high
```
Detects vulnerabilities, secrets, and misconfigurations.

#### 8. Bridge to GitHub
```bash
forgeflow bridge --operation push --repo owner/repo
```
Pushes code and creates pull requests.

---

## Command Deep Dive

### discover

Scans repository structure and creates inventory.

```bash
forgeflow discover --path ./my-repo
```

**Output:**
- File inventory
- Language detection
- Component categorization
- Creates `.forgeflow/inventory.json`

### scan

Security vulnerability scanning.

```bash
forgeflow scan --path ./my-repo --severity medium
```

**Severity Levels:**
- `low` - All findings
- `medium` - Medium and above (default)
- `high` - High and critical only
- `critical` - Critical only

**Detects:**
- Hardcoded secrets
- SQL injection patterns
- Command injection
- Insecure configurations

### generate

Generates deployment artifacts.

```bash
forgeflow generate --path ./my-repo --stack terraform
```

**Stack Options:**
- `auto` - Auto-detect based on project
- `docker` - Dockerfile and docker-compose
- `kubernetes` - K8s manifests
- `terraform` - Infrastructure as code
- `helm` - Helm charts

**Generated Files:**
- `terraform/` - Infrastructure configs
- `Dockerfile` - Container definition
- `.github/workflows/` - CI/CD pipelines

### bridge

GitHub integration operations.

```bash
# Initialize and push
forgeflow bridge --operation init --repo owner/repo

# Create pull request
forgeflow bridge --operation pr --repo owner/repo --branch feature-branch

# Check status
forgeflow bridge --operation status
```

---

## Best Practices

### 1. Start with Discovery

Always run `discover` first to build an inventory:

```bash
forgeflow discover --path ./my-repo
```

### 2. Use Audit for Quick Checks

The `audit` command runs discover → normalize → scan → generate:

```bash
forgeflow audit --path ./my-repo
```

### 3. Review Generated Files

Always review generated Terraform and Kubernetes configs before deployment.

### 4. Set Appropriate Severity

For production code, use higher severity thresholds:

```bash
forgeflow scan --severity high
```

### 5. Use Hybrid Mode for Enhanced Security

Hybrid mode enables cloud security scanning:

```bash
forgeflow --mode hybrid scan --path ./my-repo
```

---

## Troubleshooting

### Common Issues

#### "MCP server failed to start"

```bash
# Check Python path
which python3

# Verify dependencies
pip list | grep -E "pyyaml|click|rich"

# Run doctor
forgeflow doctor
```

#### "GitHub CLI not authenticated"

```bash
# Authenticate with GitHub
gh auth login

# Verify
gh auth status
```

#### "Permission denied"

```bash
# Check file permissions
ls -la /path/to/repo

# Ensure you have write access
chmod -R u+w /path/to/repo
```

### Debug Mode

Enable verbose output:

```bash
export FORGEFLOW_DEBUG=1
forgeflow discover --path ./my-repo
```

### Getting Help

```bash
# General help
forgeflow --help

# Command-specific help
forgeflow generate --help
```

---

## Next Steps

- [Architecture Documentation](ARCHITECTURE.md)
- [Configuration Guide](CONFIGURATION.md)
- [Deployment Options](DEPLOYMENT.md)
