# SevaForge Unified — ForgeFlow

**AI-Powered Platform Engineering CLI** — from any codebase to production-ready GCP/GKE infrastructure in a single command.

## What ForgeFlow Does

ForgeFlow analyses your repository and generates everything needed to deploy it: Terraform infrastructure, GKE cluster specs, Helm charts, CI/CD pipelines, observability stacks, security policies, and cost controls. Seven specialized AI agents work in parallel to produce 26+ deployment artifacts from a single intent file.

## 16-Stage Pipeline

```
Analyse:  DISCOVER → NORMALIZE → DOCS
Build:    IAC → CD → CI → E2E
Quality:  REVIEW → TEST → SCAN
Ship:     DEPLOY-INTENT → DEPLOY-DESIGN → DEPLOY-VALIDATE → SECRETS → LIFECYCLE → BRIDGE
```

The **Ship** phase includes a pre-push deployment pipeline where:
- **Deploy-Intent** interviews you once (cloud, region, compute model, SLOs, cost limits) and caches the answers
- **Deploy-Design** fans out to 7 persona agents in 3 parallel layers producing all deployment artifacts
- **Deploy-Validate** cross-checks every artifact for consistency before allowing the push

## 7 Persona Agents

| Layer | Persona | What it produces |
|-------|---------|-----------------|
| 1 | InfraArchitect | VPC, subnets, firewall rules (Terraform) |
| 1 | SecretsManager | Secrets inventory, bootstrap script, deployment guide |
| 2 | ClusterBuilder | GKE/EKS cluster spec (Terraform) |
| 2 | AppDeployer | Dockerfile, Helm chart, HPA, Kustomize overlays |
| 3 | ObservabilityEngineer | Prometheus, Grafana, SLOs, alert rules |
| 3 | SecurityAuditor | NetworkPolicy, Pod Security, IAM minimization |
| 3 | CostGuardian | Budget alerts, nightly shutdown, auto-teardown |

## Quickstart

```bash
# Install
pip install -e forgeflow/

# Run full pipeline
forgeflow run-all ./my-repo

# Or run individual deploy stages
forgeflow deploy-intent --path ./my-repo
forgeflow deploy-design --path ./my-repo
forgeflow deploy-validate --path ./my-repo
```

## Architecture Diagram

See [forgeflow-architecture.mermaid](forgeflow-architecture.mermaid) for the full physical layout covering GCP infrastructure, Kubernetes internals, and the pipeline-to-infra mapping.

## Project Structure

```
sevaforge_unified/
├── forgeflow/
│   ├── cli/forgeflow.py              # CLI entry point (16 subcommands)
│   ├── core/
│   │   ├── mission_control.py        # Pipeline orchestration
│   │   ├── display.py                # Rich console output + stage mapping
│   │   └── orchestrator.py           # Local/cloud MCP routing
│   ├── agents/
│   │   ├── deploy_intent_agent.py    # Deployment interview + caching
│   │   ├── deploy_orchestrator_agent.py  # 7-persona parallel fan-out
│   │   ├── deploy_validator_agent.py # 7-check pre-push gate
│   │   └── personas/                 # 7 specialized deployment agents
│   ├── gui/dashboard_server.py       # Web dashboard with SSE streaming
│   ├── ui/index.html                 # React dashboard frontend
│   └── mcp_servers/                  # One server.py per stage
├── deploy/                           # Generated deployment artifacts
│   ├── helm/                         # Helm charts
│   ├── secrets/                      # Secrets inventory
│   ├── observability/                # Prometheus, Grafana, alerts
│   ├── security/                     # NetworkPolicy, pod security
│   └── cost/                         # Budget alerts, shutdown workflows
├── infrastructure/                   # Generated Terraform + K8s manifests
├── .sevaforge/deployment-intent.yaml # Cached deployment configuration
├── .github/workflows/                # Generated CI/CD workflows
└── forgeflow-architecture.mermaid    # Full architecture diagram
```

## Documentation

- [Pipeline Stages](forgeflow/docs/PIPELINE_STAGES.md) — All 16 stages explained
- [Architecture](forgeflow/docs/ARCHITECTURE.md) — System design and component layers
- [Agent Architecture](forgeflow/docs/AGENT_ARCHITECTURE.md) — Agent-MCP mapping and persona system
- [User Guide](forgeflow/docs/USER_GUIDE.md) — Complete usage guide
- [Configuration](forgeflow/docs/CONFIGURATION.md) — Config reference
- [Deployment](forgeflow/docs/DEPLOYMENT.md) — Container and Kubernetes deployment
- [Local Setup](forgeflow/LOCAL_SETUP.md) — Prerequisites and installation

## Target Infrastructure

Default target: **GCP** with GKE Autopilot in `us-central1`. Configurable via the deploy-intent interview for AWS (EKS), OCI (OKE), or other providers.

## License

MIT
