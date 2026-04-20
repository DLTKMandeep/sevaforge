# ForgeFlow Architecture

## Overview

ForgeFlow is a CLI tool that drives a pipeline of 16 specialized AI agents. Each agent analyses the target repository and generates production-ready infrastructure, CI/CD, and deployment artifacts. The v2.2 architecture introduces a pre-push deployment pipeline with 7 persona agents running in 3 parallel layers.

---

## Component Layers

```
┌─────────────────────────────────────────────────────────────────────┐
│  CLI  (forgeflow/cli/forgeflow.py)                                  │
│  16 subcommands + dashboard, parses args, calls MissionControl      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  MissionControl  (core/mission_control.py)                          │
│  Orchestrates 16 pipeline stages, saves reports, handles run-all    │
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

## Pipeline Sequence (v2.2 — 16 Stages, 4 Phases)

```
forgeflow run-all ./repo
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: Analyse                                                    │
│    DISCOVER → NORMALIZE → DOCS                                       │
│                                                                      │
│  Phase 2: Build                                                      │
│    IAC → CD → CI → E2E                                               │
│                                                                      │
│  Phase 3: Quality                                                    │
│    REVIEW → TEST → SCAN                                              │
│                                                                      │
│  Phase 4: Ship (Pre-Push Deployment Pipeline)                        │
│    DEPLOY-INTENT ──→ DEPLOY-DESIGN ──→ DEPLOY-VALIDATE              │
│         │                  │                   │                      │
│         │           ┌──────┴──────┐      7 checks:                   │
│         │           │ 7 Personas  │      secrets, crons,             │
│         │           │ 3 Layers    │      SLOs, hash, TF vars,        │
│         │           │ 26 Artifacts│      image repo, dates           │
│         │           └─────────────┘            │                     │
│         ▼                                      ▼                     │
│    .sevaforge/                          BLOCKS push on               │
│    deployment-intent.yaml               any failure                  │
│                                                │                     │
│    SECRETS → LIFECYCLE → BRIDGE (git push)     │                     │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼ (generated .github/workflows/ committed to repo)
┌─────────────────────────────────────────────────────────────────────┐
│  GitHub Actions — runs entirely in the cloud                         │
│                                                                      │
│  ci.yml         Lint, test (Python 3.10–3.12), security scan        │
│  cd.yml         Build Docker multi-arch → deploy to GKE              │
│  cost-shutdown  Scale to 0 at 4AM, restore at 2PM UTC                │
│  cost-teardown  One-shot terraform destroy                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Deploy-Design: 7 Persona Agents

The deploy-design stage fans out to 7 specialized agents running in 3 parallel layers:

```
Layer 1 (Foundation):    InfraArchitect ────────── SecretsManager
                              │
Layer 2 (Platform):      ClusterBuilder ────────── AppDeployer
                              │
Layer 3 (Operations):    ObservabilityEngineer ─── SecurityAuditor ─── CostGuardian
```

Each persona reads `.sevaforge/deployment-intent.yaml` and produces artifacts under well-known paths:

| Persona | Output Directory | Key Files |
|---------|-----------------|-----------|
| InfraArchitect | `forgeflow/infrastructure/{cloud}/` | `network.tf`, `variables.tf`, `providers.tf`, `backend.tf` |
| SecretsManager | `deploy/secrets/` | `inventory.yaml`, `bootstrap.sh`, `DEPLOYMENT_SECRETS_GUIDE.md` |
| ClusterBuilder | `forgeflow/infrastructure/{cloud}/` | `cluster.tf` |
| AppDeployer | `deploy/helm/{app}/` + `Dockerfile` | `Chart.yaml`, `values.yaml`, `templates/` |
| ObservabilityEngineer | `deploy/observability/` | `prometheus-values.yaml`, `servicemonitor.yaml`, `slo.yaml`, `alerts.yaml` |
| SecurityAuditor | `deploy/security/` | `networkpolicy.yaml`, `pod-security.yaml`, `iam-minimization.md` |
| CostGuardian | `deploy/cost/` + `.github/workflows/` | `budget-alert.tf`, `cost-shutdown.yml`, `cost-teardown.yml` |

---

## Agent-MCP Mapping (v2.2 — 16 Stages)

| Stage | MCP Server | Agent | Phase |
|-------|-----------|-------|-------|
| discover | discovery-mcp-server | DiscoveryAgent | Analyse |
| normalize | normalize-mcp-server | NormalizationAgent | Analyse |
| docs | diagram-generator-mcp-server | DocumentationAgent | Analyse |
| iac | iac-mcp-server | IACAgent | Build |
| cd | cd-mcp-server | CDAgent | Build |
| ci | ci-mcp-server | CIAgent | Build |
| e2e | e2e-mcp-server | E2ETestingAgent | Build |
| review | git-mcp-server | CodeReviewAgent | Quality |
| test | cicd-mcp-server | TestingAgent | Quality |
| scan | security-mcp-server | SecurityAgent | Quality |
| deploy-intent | intent-mcp-server | DeployIntentAgent | Ship |
| deploy-design | design-mcp-server | DeployOrchestratorAgent | Ship |
| deploy-validate | validate-mcp-server | DeployValidatorAgent | Ship |
| secrets | secrets-mcp-server | SecretsAgent | Ship |
| lifecycle | lifecycle-mcp-server | LifecycleAgent | Ship |
| bridge | github-mcp-server | BridgeAgent | Ship |

---

## Physical Architecture Diagram

See [forgeflow-architecture.mermaid](../../forgeflow-architecture.mermaid) for the full physical layout covering:

- **GCP Infrastructure** — VPC (`sevaforge-unified-vpc`), subnet (10.10.0.0/20), firewall rules, GKE Autopilot cluster, GCS state backend, GCR container registry, 5 IAM service accounts
- **Kubernetes Internals** — application namespace with pods/HPA/services, observability namespace with Prometheus/Grafana/AlertManager, NetworkPolicies, Pod Security Standards
- **Pipeline → Infra Mapping** — how each pipeline stage produces artifacts that compose into the deployment

---

## Secrets Architecture

Secrets are split into tiers based on who provides them:

```
Tier 1 — Cloud Credentials (set once via forgeflow secrets bootstrap)
  GH_TOKEN, GCP_SA_KEY, GCP_PROJECT_ID, GCP_REGION

Tier 2 — Application Secrets (from deploy/secrets/inventory.yaml)
  DATABASE_URL, JWT_SECRET, REDIS_URL, SESSION_SECRET,
  STRIPE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
  SENDGRID_API_KEY, SMTP_PASSWORD

Tier 3 — CI Service Tokens (repo-level, not inventoried)
  CODECOV_TOKEN, SONAR_TOKEN, etc.
```

The deploy-validate stage uses an **inventory-anchored** approach: it checks that every secret in `deploy/secrets/inventory.yaml` is actually referenced somewhere in the project source code, without trying to enumerate CI/config variables.

---

## Deployment Modes

The Orchestrator routes each MCP dispatch based on `--mode`:

| Mode | Description | Routing |
|------|-------------|---------|
| `local` (default) | All MCPs run as local Python modules | `importlib` dynamic import |
| `cloud` | All MCPs run on ForgeFlow cloud endpoints | HTTP/SSE via `RemoteClient` |

---

## File Layout

```
forgeflow/
├── cli/
│   └── forgeflow.py               # argparse + 16 subcommands
├── core/
│   ├── mission_control.py          # Pipeline coordination, PIPELINE_STAGES
│   ├── orchestrator.py             # MCP routing, mode handling
│   ├── display.py                  # Rich tables, STAGE_MAPPING, STAGE_COLORS
│   ├── models.py                   # wrap_mcp_response, create_error_response
│   ├── stack_suggester.py          # Detects stack from repo contents
│   ├── wizard.py                   # Greenfield init wizard
│   └── remote_client.py            # HTTP/SSE client for cloud mode
├── agents/
│   ├── base_agent.py               # BaseAgent abstract class
│   ├── deploy_intent_agent.py      # Stage 11 — deployment interview
│   ├── deploy_orchestrator_agent.py # Stage 12 — 7-persona fan-out
│   ├── deploy_validator_agent.py   # Stage 13 — pre-push gate
│   └── personas/
│       ├── base_persona.py         # BasePersona (extends BaseAgent)
│       ├── infra_architect_persona.py
│       ├── cluster_builder_persona.py
│       ├── app_deployer_persona.py
│       ├── secrets_manager_persona.py
│       ├── observability_engineer_persona.py
│       ├── security_auditor_persona.py
│       └── cost_guardian_persona.py
├── gui/
│   └── dashboard_server.py         # Web dashboard with SSE log streaming
├── ui/
│   └── index.html                  # React dashboard (16 stages, 4 phases)
├── mcp_servers/                    # One server.py per stage
├── config/
│   └── forgeflow-config.yaml       # mode, cloud endpoints, pipeline sequence
├── mcp-config.yaml                 # MCP server command + script definitions
├── tests/                          # pytest test suite (51+ tests for deploy pipeline)
├── pyproject.toml
└── requirements.txt
```
