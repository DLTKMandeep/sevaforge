# ForgeFlow Release Notes

## Release v2.2.0

**Release Date:** April 20, 2026

---

## Overview

ForgeFlow v2.2 introduces the **pre-push deployment pipeline** — a 3-stage system (deploy-intent, deploy-design, deploy-validate) that replaces the deprecated post-push DeployReadinessAgent. Seven specialized persona agents now generate all deployment artifacts in parallel before any code is pushed to GitHub.

---

## What's New in v2.2

### Pre-Push Deployment Pipeline (3 New Stages)

The pipeline grows from 13 to **16 stages** with three new stages inserted between `scan` and `secrets` in the Ship phase:

- **deploy-intent** (Stage 11) — Interactive interview that captures cloud provider, region, compute model, SLOs, and cost controls. Answers are cached in `.sevaforge/deployment-intent.yaml` with a SHA256 integrity hash.
- **deploy-design** (Stage 12) — Fans out to 7 persona agents running in 3 parallel layers via ThreadPoolExecutor, producing 26+ deployment artifacts.
- **deploy-validate** (Stage 13) — Cross-checks all persona outputs with 7 validation checks. Blocks the push if any check fails.

### 7 Persona Agents

| Layer | Persona | Artifacts |
|-------|---------|-----------|
| 1 | InfraArchitect | VPC, subnets, firewall (Terraform) |
| 1 | SecretsManager | Secrets inventory, bootstrap script |
| 2 | ClusterBuilder | GKE/EKS cluster spec (Terraform) |
| 2 | AppDeployer | Dockerfile, Helm chart, HPA |
| 3 | ObservabilityEngineer | Prometheus, Grafana, SLOs, alerts |
| 3 | SecurityAuditor | NetworkPolicy, Pod Security, IAM |
| 3 | CostGuardian | Budget alerts, shutdown/teardown workflows |

### Inventory-Anchored Secret Validation

The validator no longer scans for `${VAR}` patterns heuristically. Instead it trusts the SecretsManager persona's inventory and verifies that every inventoried secret is actually referenced in the project source. This eliminates false positives across any repo.

### Dashboard Integration

The React dashboard and SSE log streaming now support all 16 stages including the 3 new deploy stages and all 7 persona loggers. The Ship phase card shows deploy-intent, deploy-design, and deploy-validate with animated step tickers.

### CLI Subcommands

Three new CLI subcommands for running deploy stages individually:

```bash
forgeflow deploy-intent --path ./my-repo [--force] [--non-interactive]
forgeflow deploy-design --path ./my-repo [--only persona1,persona2] [--skip persona3]
forgeflow deploy-validate --path ./my-repo
```

---

## Breaking Changes

- **DeployReadinessAgent removed** — replaced by the deploy-intent/deploy-design/deploy-validate pipeline. The `readiness-mcp-server` config entry has been removed from `mcp-config.yaml` and `forgeflow-config.yaml`.
- **Pipeline stage count** — changed from 13 to 16. Any tooling that hardcodes stage counts will need updating.

---

## Previous Releases

### v2.1.0 (March 2026)
- Added `iac`, `cd`, `ci`, `e2e` stages (pipeline grew from 10 to 13 stages)
- Full GitOps delivery system generation (ArgoCD, Kustomize, External Secrets)
- GCP and OCI cloud provider support alongside AWS

### v2.0.0 (February 2026)
- Unified architecture — consolidated `sevaforge_local`, `sevaforge_cloud`, and `sevaforge_hybrid` into a single `forgeflow` package
- Single config file (`forgeflow-config.yaml`) replaces three branch-specific configs
- Web dashboard with real-time SSE log streaming

### v1.0.0 (February 8, 2026)
- Initial stable release
- 10 specialized agents for platform engineering tasks
- Three deployment modes (local, hybrid, cloud)
- Agent-MCP architecture for modularity
- Rich CLI output with progress indicators

---

## Installation

```bash
git clone https://github.com/DLTKMandeep/sevaforge.git
cd sevaforge && git checkout unified
pip install -e forgeflow/
```

**Prerequisites:** Python 3.9+ and `gh` CLI (`brew install gh`).

---

## Support

- **Issues:** https://github.com/DLTKMandeep/sevaforge/issues
- **Documentation:** See `forgeflow/docs/`

---

## License

MIT License
