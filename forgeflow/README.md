<h1 align="center">ForgeFlow</h1>

<p align="center">
  <strong>AI-Powered Platform Engineering CLI</strong><br>
  From any codebase to production on AWS — fully automated, zero desktop tooling required.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"/></a>
</p>

---

## What is ForgeFlow?

ForgeFlow is an AI platform engineering CLI that analyses any repository and automatically generates everything needed to get it to production on AWS EKS — Terraform, Kubernetes manifests, ArgoCD GitOps config, CI/CD pipelines, security scans, E2E tests, and a fully automated deploy pipeline.

**Core principle: nothing runs on the developer's desktop except ForgeFlow itself.** Terraform provisioning, ArgoCD bootstrap, image builds, and deploys all happen inside GitHub Actions in the cloud.

---

## Quickstart

```bash
# 1. Install
pip install forgeflow

# 2. Run ForgeFlow against your repo
cd ~/your-repo
forgeflow run-all .

# 3. One-time secrets setup (interactive wizard — no shell scripts)
forgeflow secrets bootstrap

# 4. Push — the cloud does everything else
git push origin main
```

GitHub Actions then automatically:
- Provisions EKS + VPC + IAM via Terraform (`infra.yml`)
- Installs ArgoCD + writes credentials back as secrets (`bootstrap.yml`)
- Builds, tests, gates, and deploys staging → production (`deploy.yml`)

---

## Pipeline Stages

ForgeFlow runs 14 stages in sequence, each backed by a dedicated Agent + MCP server:

```
DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → BRIDGE
                                                                              │
                                                          (post-merge) DEPLOY → MONITOR
```

| Stage | What it generates |
|-------|------------------|
| `discover` | Repository inventory — languages, frameworks, entry points |
| `normalize` | Adds missing standard files (`.gitignore`, `pyproject.toml`, etc.) |
| `docs` | Architecture diagrams, API docs, component maps |
| `iac` | Terraform (EKS, VPC, IAM, ECR), Dockerfile, docker-compose |
| `cd` | `infra.yml` + `bootstrap.yml` + `deploy.yml` GitHub Actions workflows, ArgoCD manifests, Kustomize overlays, External Secrets Operator manifests |
| `ci` | CI pipeline (build, lint, test, security), Dependabot config |
| `e2e` | Playwright / Cypress test suite + E2E workflow |
| `review` | Code quality analysis, Git history review |
| `test` | Test coverage report |
| `scan` | Security vulnerability scan (SAST, secrets, misconfigs) |
| `bridge` | GitHub PR creation, branch management |
| `deploy` | Deploy trigger (post-merge) |
| `monitor` | Prometheus + Grafana configs |

---

## Command Reference

```bash
# Individual stages
forgeflow discover   --path ./my-repo
forgeflow normalize  --path ./my-repo
forgeflow iac        --path ./my-repo --cloud aws
forgeflow cd         --path ./my-repo --repo-url https://github.com/org/repo
forgeflow cd         --path ./my-repo --overwrite   # refresh existing files
forgeflow ci         --path ./my-repo
forgeflow e2e        --path ./my-repo
forgeflow scan       --path ./my-repo
forgeflow docs       --path ./my-repo

# Full pipeline in one command
forgeflow run-all ./my-repo

# Secrets management (interactive — no shell scripts needed)
forgeflow secrets list       # show all required secrets and their purpose
forgeflow secrets check      # verify which are set in GitHub
forgeflow secrets bootstrap  # wizard: prompts for 4 values, sets everything

# Utilities
forgeflow status --path ./my-repo   # check pipeline completion
forgeflow doctor                     # system health check
forgeflow audit  --path ./my-repo   # security + quality audit
```

---

## Deployment Modes

| Mode | Description | When to use |
|------|-------------|-------------|
| `local` | All MCPs run as local Python modules (default) | Development, offline, full control |
| `cloud` | All MCPs run on ForgeFlow cloud endpoints | Teams, CI/CD, managed service |

```bash
# Local (default)
forgeflow cd --path ./my-repo

# Cloud mode
export FORGEFLOW_API_KEY=your_key
forgeflow --mode cloud cd --path ./my-repo
```

---

## What `forgeflow cd` Generates

```
.github/workflows/
  infra.yml        ← Terraform EKS provisioning (GitHub Actions)
  bootstrap.yml    ← ArgoCD install + auto-writes secrets (GitHub Actions)
  deploy.yml       ← Build → staging → E2E gate → approval → prod

infrastructure/
  terraform/       ← EKS, VPC, IAM, ECR + S3 state bucket bootstrap
  k8s/
    base/          ← Deployment, Service, ConfigMap, HPA
    overlays/      ← dev / staging / prod Kustomize overlays
    argocd/        ← AppProject + ApplicationSet
    secrets/       ← External Secrets Operator (AWS Secrets Manager)

RUNBOOK.md         ← Complete operational guide
```

---

## One-Time Onboarding

```bash
gh auth login                   # 1. authenticate GitHub CLI
forgeflow secrets bootstrap     # 2. wizard sets 4 secrets + creates environments
git push origin main            # 3. done — cloud handles everything
```

**You provide 4 values once. ForgeFlow writes the rest automatically:**

| Set by you | Set by ForgeFlow workflows |
|------------|---------------------------|
| `AWS_ACCESS_KEY_ID` | `EKS_CLUSTER_NAME` (infra.yml) |
| `AWS_SECRET_ACCESS_KEY` | `ARGOCD_SERVER` (bootstrap.yml) |
| `AWS_REGION` | `ARGOCD_AUTH_TOKEN` (bootstrap.yml) |
| `GH_PAT` | `STAGING_URL`, `PROD_URL` (bootstrap.yml) |

---

## Project Structure

```
forgeflow/
├── cli/forgeflow.py           # Entry point
├── core/
│   ├── mission_control.py     # Command orchestration
│   ├── orchestrator.py        # Routes to local modules or cloud endpoints
│   ├── display.py             # Rich console output
│   └── remote_client.py       # Cloud mode HTTP/SSE client
├── agents/
│   ├── cd_agent.py            # Generates all 3 GitHub Actions workflows
│   ├── iac_agent.py           # Terraform + Docker
│   ├── ci_agent.py            # GitHub Actions CI
│   ├── e2e_agent.py           # Playwright / Cypress
│   └── ...
├── mcp_servers/               # One server.py per stage
├── config/forgeflow-config.yaml
├── mcp-config.yaml
└── pyproject.toml
```

---

## Installation

```bash
git clone https://github.com/DLTKMandeep/sevaforge.git
cd sevaforge && git checkout unified
pip install -e forgeflow/
```

**Prerequisites:** Python 3.9+ and `gh` CLI (`brew install gh`). Nothing else — Terraform, kubectl, Helm, ArgoCD all run in GitHub Actions.

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) · License: MIT
