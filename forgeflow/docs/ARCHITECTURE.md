# ForgeFlow Architecture

## Overview

ForgeFlow is a CLI tool that drives a pipeline of specialised AI agents. Each agent analyses the target repository and generates production-ready infrastructure, CI/CD, and deployment artifacts. The key design principle is that generated GitHub Actions workflows run everything in the cloud — no local tooling (Terraform, kubectl, Helm) is needed beyond ForgeFlow itself.

---

## Component Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLI  (forgeflow/cli/forgeflow.py)                                  │
│  Parses commands, calls MissionControl, renders rich output         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  MissionControl  (core/mission_control.py)                          │
│  Orchestrates pipeline stages, saves reports, handles run-all       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  Orchestrator  (core/orchestrator.py)                               │
│  Routes to LOCAL (Python module) or CLOUD (HTTP via RemoteClient)   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
          ┌────────────────┴─────────────────┐
          │                                  │
┌─────────▼──────────┐            ┌──────────▼───────────────────────┐
│  MCP Server        │            │  RemoteClient (remote_client.py) │
│  (local module)    │            │  HTTP/SSE to api.forgeflow.io    │
│  server.run(params)│            └──────────────────────────────────┘
└─────────┬──────────┘
          │
┌─────────▼──────────┐
│  Agent             │
│  execute(params)   │
│  _safe_write(...)  │
└────────────────────┘
```

---

## Pipeline Sequence

```
git push
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  forgeflow run-all ./repo                                        │
│                                                                  │
│  DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E             │
│       → REVIEW → TEST → SCAN → BRIDGE (approval gate)          │
│                                                                  │
│  (post-merge) DEPLOY → MONITOR                                   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼ (generated .github/workflows/ committed to repo)
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Actions — runs entirely in the cloud                     │
│                                                                  │
│  infra.yml      Terraform → EKS + VPC + IAM                     │
│       └─ triggers ──▶  bootstrap.yml                            │
│                          ArgoCD install + secrets write-back     │
│                                                                  │
│  deploy.yml     Build → staging → E2E gate → approval → prod    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent-MCP Mapping

Each ForgeFlow stage is a pair: one Agent (business logic) + one MCP server (protocol bridge).

| Stage | MCP Server | Agent |
|-------|-----------|-------|
| discover | discovery-mcp-server | DiscoveryAgent |
| normalize | normalize-mcp-server | NormalizationAgent |
| docs | diagram-generator-mcp-server | DocumentationAgent |
| iac | iac-mcp-server | IACAgent |
| cd | cd-mcp-server | CDAgent |
| ci | ci-mcp-server | CIAgent |
| e2e | e2e-mcp-server | E2ETestingAgent |
| review | git-mcp-server | CodeReviewAgent |
| test | cicd-mcp-server | TestingAgent |
| scan | security-mcp-server | SecurityAgent |
| bridge | github-mcp-server | BridgeAgent |
| deploy | cloud-mcp-server | DeploymentAgent |
| monitor | observability-mcp-server | MonitoringAgent |

---

## CDAgent — The Heart of GitOps Automation

`CDAgent` (`agents/cd_agent.py`) is the most significant agent. It generates the complete cloud delivery system for any consumer project:

**GitHub Actions Workflows (owned by CDAgent as Python template constants):**
- `INFRA_WORKFLOW_TEMPLATE` → `.github/workflows/infra.yml`
  - Bootstraps S3 Terraform state bucket (idempotent)
  - Runs `terraform apply` to provision EKS + VPC + IAM
  - Captures outputs, stores as GitHub variables
  - Auto-triggers `bootstrap.yml`
- `BOOTSTRAP_WORKFLOW_TEMPLATE` → `.github/workflows/bootstrap.yml`
  - Installs ArgoCD via Helm on EKS
  - Waits for LoadBalancer hostname
  - Generates ArgoCD API token
  - **Writes `ARGOCD_SERVER` + `ARGOCD_AUTH_TOKEN` back as GitHub secrets** (using `GH_PAT`)
  - Installs External Secrets Operator
  - Applies ArgoCD ApplicationSet
- `DEPLOY_WORKFLOW_TEMPLATE` → `.github/workflows/deploy.yml`
  - Builds Docker image → pushes to GHCR
  - Deploys to staging via `kustomize edit set image` + ArgoCD sync
  - E2E gate (Playwright) + DAST gate (OWASP ZAP)
  - Manual approval gate (production environment)
  - Deploys to production + health check + auto-rollback

**Kubernetes Manifests:**
- Kustomize base + dev/staging/prod overlays
- ArgoCD AppProject + ApplicationSet
- External Secrets Operator ClusterSecretStore + ExternalSecret per environment
- IRSA service account

---

## Secrets Architecture

Secrets are split into three tiers:

```
Tier 1 — Human (set ONCE via forgeflow secrets bootstrap)
  AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, GH_PAT

Tier 2 — Auto-managed (written by ForgeFlow GitHub Actions)
  EKS_CLUSTER_NAME  ← infra.yml after terraform apply
  ARGOCD_SERVER     ← bootstrap.yml after ArgoCD LoadBalancer ready
  ARGOCD_AUTH_TOKEN ← bootstrap.yml after token generation
  STAGING_URL       ← bootstrap.yml after namespace creation
  PROD_URL          ← bootstrap.yml after namespace creation

Tier 3 — App secrets (AWS Secrets Manager → External Secrets Operator → K8s)
  DATABASE_URL, SECRET_KEY, etc. — managed per environment
```

---

## Deployment Modes

The Orchestrator routes each MCP dispatch based on `--mode`:

```python
# local mode
_dispatch_local(server_name, params)
  → importlib.util.spec_from_file_location(server_name, server_script)
  → module.run(params)
  → agent.execute(params)

# cloud mode
_dispatch_remote(server_name, params)
  → RemoteClient.dispatch(command, params)
  → POST https://api.forgeflow.io/v1/<command>
  → streams SSE response
```

---

## File Layout

```
forgeflow/
├── cli/
│   └── forgeflow.py           # argparse + MissionControl delegation
├── core/
│   ├── mission_control.py     # Pipeline coordination, report saving
│   ├── orchestrator.py        # MCP routing, mode handling
│   ├── display.py             # Rich tables, progress, banners
│   ├── models.py              # wrap_mcp_response, create_error_response
│   ├── stack_suggester.py     # Detects stack from repo contents
│   ├── wizard.py              # Greenfield init wizard
│   └── remote_client.py       # HTTP/SSE client for cloud mode
├── agents/                    # One agent per stage
├── mcp_servers/               # One server.py per stage
├── config/
│   └── forgeflow-config.yaml  # mode, cloud endpoints, pipeline sequence
├── mcp-config.yaml            # MCP server command + script definitions
├── pyproject.toml
└── requirements.txt
```
