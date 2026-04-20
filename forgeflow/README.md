<h1 align="center">ForgeFlow</h1>

<p align="center">
  <strong>AI-Powered Platform Engineering CLI</strong><br>
  From any codebase to production on GCP/GKE — fully automated, zero desktop tooling required.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"/></a>
</p>

---

## What is ForgeFlow?

ForgeFlow is an AI platform engineering CLI that analyses any repository and automatically generates everything needed to deploy it — Terraform infrastructure, GKE cluster specs, Helm charts, CI/CD pipelines, observability stacks, security policies, and cost controls. Seven specialized AI persona agents work in parallel to produce 26+ deployment artifacts from a single intent file.

**Core principle: nothing runs on the developer's desktop except ForgeFlow itself.** Terraform provisioning, container builds, and deploys all happen inside GitHub Actions in the cloud.

---

## Quickstart

```bash
# 1. Install
pip install -e forgeflow/

# 2. Run ForgeFlow against your repo
cd ~/your-repo
forgeflow run-all .

# 3. Push — the cloud does everything else
git push origin main
```

GitHub Actions then automatically provisions infrastructure, builds containers, runs tests, and deploys to GKE.

---

## 16-Stage Pipeline (v2.2)

ForgeFlow runs **16 stages** in 4 phases, each backed by a dedicated Agent + MCP server:

```
Analyse:  DISCOVER → NORMALIZE → DOCS
Build:    IAC → CD → CI → E2E
Quality:  REVIEW → TEST → SCAN
Ship:     DEPLOY-INTENT → DEPLOY-DESIGN → DEPLOY-VALIDATE → SECRETS → LIFECYCLE → BRIDGE
```

| Stage | What it generates |
|-------|------------------|
| `discover` | Repository inventory — languages, frameworks, entry points |
| `normalize` | Adds missing standard files (`.gitignore`, `pyproject.toml`, etc.) |
| `docs` | Architecture diagrams, component maps |
| `iac` | Terraform (VPC, networking, IAM), Dockerfile |
| `cd` | GitHub Actions CD workflows, Kustomize overlays |
| `ci` | CI pipeline (build, lint, test, security), Dependabot config |
| `e2e` | Playwright / Cypress test suite + E2E workflow |
| `review` | Code quality analysis, Git history review |
| `test` | Test coverage report |
| `scan` | Security vulnerability scan (SAST, CVEs, secrets, misconfigs) |
| `deploy-intent` | Interactive deployment interview → `.sevaforge/deployment-intent.yaml` |
| `deploy-design` | 7 persona agents in 3 parallel layers → 26+ artifacts |
| `deploy-validate` | 7 cross-checks (secrets, crons, SLOs, hash, TF vars, image repo) |
| `secrets` | Secrets bootstrap guide + IAM policies |
| `lifecycle` | CI/CD lifecycle workflow chain |
| `bridge` | GitHub push + PR creation |

---

## Command Reference

```bash
# Individual stages
forgeflow discover       --path ./my-repo
forgeflow normalize      --path ./my-repo
forgeflow iac            --path ./my-repo --cloud gcp
forgeflow cd             --path ./my-repo --repo-url https://github.com/org/repo
forgeflow ci             --path ./my-repo
forgeflow e2e            --path ./my-repo
forgeflow scan           --path ./my-repo

# Pre-push deployment pipeline
forgeflow deploy-intent  --path ./my-repo [--force] [--non-interactive]
forgeflow deploy-design  --path ./my-repo [--only infra-architect,app-deployer]
forgeflow deploy-validate --path ./my-repo

# Full 16-stage pipeline
forgeflow run-all ./my-repo

# Web dashboard
forgeflow dashboard

# Utilities
forgeflow status --path ./my-repo
forgeflow doctor
forgeflow audit  --path ./my-repo
```

---

## Deploy-Design: 7 Persona Agents

The deploy-design stage fans out to 7 specialized agents in 3 parallel layers:

| Layer | Personas | What they produce |
|-------|----------|------------------|
| 1 (Foundation) | InfraArchitect, SecretsManager | VPC/subnet Terraform, secrets inventory |
| 2 (Platform) | ClusterBuilder, AppDeployer | GKE cluster Terraform, Dockerfile + Helm chart |
| 3 (Operations) | Observability, Security, CostGuardian | Prometheus/Grafana, NetworkPolicy, shutdown workflows |

---

## Deployment Modes

| Mode | Description | When to use |
|------|-------------|-------------|
| `local` | All MCPs run as local Python modules (default) | Development, offline, full control |
| `cloud` | All MCPs run on ForgeFlow cloud endpoints | Teams, CI/CD, managed service |

---

## Architecture Diagram

See [forgeflow-architecture.mermaid](../forgeflow-architecture.mermaid) for the full physical layout:
- GCP infrastructure (VPC, GKE Autopilot, GCR, IAM)
- Kubernetes internals (pods, HPA, services, observability, security)
- Pipeline-to-infra mapping (how each stage produces artifacts)

---

## Project Structure

```
forgeflow/
├── cli/forgeflow.py               # Entry point (16 subcommands)
├── core/
│   ├── mission_control.py         # Pipeline orchestration (PIPELINE_STAGES)
│   ├── orchestrator.py            # Routes to local modules or cloud endpoints
│   ├── display.py                 # Rich console output, STAGE_MAPPING
│   └── remote_client.py           # Cloud mode HTTP/SSE client
├── agents/
│   ├── deploy_intent_agent.py     # Deployment interview + caching
│   ├── deploy_orchestrator_agent.py # 7-persona parallel fan-out
│   ├── deploy_validator_agent.py  # 7-check pre-push gate
│   └── personas/                  # 7 specialized deployment agents
├── gui/dashboard_server.py        # Web dashboard with SSE streaming
├── ui/index.html                  # React dashboard (16 stages, 4 phases)
├── mcp_servers/                   # One server.py per stage
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

**Prerequisites:** Python 3.9+ and `gh` CLI (`brew install gh`). Nothing else — Terraform, kubectl, Helm all run in GitHub Actions.

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) · License: MIT
