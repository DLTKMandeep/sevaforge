# Changelog

All notable changes to ForgeFlow will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-02-08

### Added

- **Initial Release** 🎉
- Agent-MCP Architecture
  - 10 specialized agents (Discovery, Normalization, Security, Generation, Deployment, Testing, Monitoring, Documentation, CodeReview, Bridge)
  - 10 corresponding MCP servers
  - BaseAgent abstract class for extensibility
- CLI Commands
  - `discover` - Repository structure scanning
  - `normalize` - Project standardization
  - `scan` - Security vulnerability detection
  - `generate` - Deployment artifact generation
  - `review` - Code review and Git analysis
  - `test` - Test execution and CI/CD detection
  - `deploy` - Cloud deployment simulation
  - `monitor` - Monitoring configuration
  - `docs` - Documentation generation
  - `bridge` - GitHub integration
  - `status` - Pipeline status check
  - `doctor` - System health check
  - `audit` - Composite audit pipeline
  - `run-all` - Full pipeline execution
- Deployment Modes
  - Local mode (full offline capability)
  - Hybrid mode (local + cloud integrations)
  - Cloud mode (thin client architecture)
- Pipeline Orchestration
  - Sequential stage execution
  - Approval gates
  - Post-merge stages
- Rich CLI Output
  - Colored console output
  - Progress indicators
  - Structured result display
- Configuration
  - YAML-based configuration
  - Environment variable support
  - Mode-specific settings
- Documentation
  - User guide
  - Architecture documentation
  - Deployment guide
  - Configuration reference
  - Contributing guidelines

### Security

- Hardcoded secret detection
- SQL injection pattern detection
- Command injection pattern detection
- Insecure configuration detection
- Severity-based filtering

### Infrastructure

- Terraform generation for AWS
  - VPC/Network modules
  - EKS cluster modules
  - S3 storage modules
  - IAM modules
- Docker configuration
  - Multi-stage Dockerfile
  - docker-compose.yml
- CI/CD
  - GitHub Actions workflow

---

## [2.1.0] - 2026-03-11

### Added

- **4 New Specialized Generation Agents** replacing the generic `generate` stage in the default pipeline:
  - `IACAgent` + `iac-mcp-server` — Infrastructure as Code generation (Terraform modules for AWS/GCP/Azure, Dockerfile, docker-compose, Pulumi)
  - `CDAgent` + `cd-mcp-server` — Continuous Deployment configuration (ArgoCD Application manifests, Kustomize overlays, Helm chart values)
  - `CIAgent` + `ci-mcp-server` — Continuous Integration pipeline setup (GitHub Actions workflows, GitLab CI, Jenkins)
  - `E2ETestingAgent` + `e2e-mcp-server` — End-to-end test scaffolding (Playwright, Cypress config and test stubs)

- **Updated pipeline sequence** — `run-all` now executes 10 stages in order:
  ```
  discover → normalize → docs → iac → cd → ci → e2e → review → test → scan → [bridge]
  ```

- **4 New MCP Servers** registered in `mcp-config.yaml` and `config/forgeflow-config.yaml`:
  - `iac-mcp-server`
  - `cd-mcp-server`
  - `ci-mcp-server`
  - `e2e-mcp-server`

### Changed

- `generate` command is now considered **legacy** — the specialized `iac`, `cd`, and `ci` commands provide finer-grained control and better output. `generate` remains available for backwards compatibility.
- Pipeline sequence in `config/forgeflow-config.yaml` updated to include new stages between `docs` and `review`.

---

## [2.2.0] - 2026-04-20

### Added

- **Pre-push deployment pipeline** — 3 new stages inserted between `scan` and `secrets`:
  - `deploy-intent` (DeployIntentAgent) — interactive deployment interview, caches answers in `.sevaforge/deployment-intent.yaml` with SHA256 integrity hash
  - `deploy-design` (DeployOrchestratorAgent) — fans out to 7 persona agents in 3 parallel layers via ThreadPoolExecutor, producing 26+ deployment artifacts
  - `deploy-validate` (DeployValidatorAgent) — 7 cross-checks (secrets inventory, cron validity, dates, SLOs, intent hash, Terraform vars, image repo); blocks push on failure

- **7 Persona agents** — specialized deployment agents running inside deploy-design:
  - Layer 1: InfraArchitectPersona (VPC/subnets/firewall Terraform), SecretsManagerPersona (secrets inventory + bootstrap)
  - Layer 2: ClusterBuilderPersona (GKE/EKS cluster Terraform), AppDeployerPersona (Dockerfile + Helm chart + HPA)
  - Layer 3: ObservabilityEngineerPersona (Prometheus/Grafana/SLOs/alerts), SecurityAuditorPersona (NetworkPolicy/PodSecurity/IAM), CostGuardianPersona (budget alerts/shutdown/teardown workflows)

- **Inventory-anchored secret validation** — validator trusts SecretsManager persona's `deploy/secrets/inventory.yaml` instead of heuristic `${VAR}` scanning. Eliminates false positives across arbitrary repos.

- **3 new CLI subcommands**: `deploy-intent`, `deploy-design`, `deploy-validate`

- **Dashboard integration** — React dashboard + SSE log streaming support all 16 stages and 7 persona loggers. Ship phase shows deploy-intent (🗣️), deploy-design (🎭), deploy-validate (🛂).

- **Full architecture diagram** — `forgeflow-architecture.mermaid` covering GCP infra, Kubernetes internals, and pipeline-to-infra mapping.

- **51+ new tests** — test_deploy_intent (11), test_deploy_orchestrator (8), test_deploy_validator (13), test_personas (20)

### Changed

- Pipeline grows from 13 to **16 stages** (4 phases: Analyse, Build, Quality, Ship)
- Default cloud provider changed from AWS to **GCP** (GKE Autopilot in us-central1)
- `secrets` and `lifecycle` are now pipeline stages 14–15 (previously 11–12)

### Removed

- `DeployReadinessAgent` — replaced by deploy-intent/deploy-design/deploy-validate pipeline
- `readiness-mcp-server` — removed from mcp-config.yaml and forgeflow-config.yaml
- `test_deploy_readiness.py` — deleted

### Deprecated

- `GenerationAgent` / `generate` command — legacy, use specialized `iac`, `cd`, `ci`, `e2e` stages instead

---

## [Unreleased]

### Planned

- MCP servers for deploy stages (intent_mcp, design_mcp, validate_mcp) for remote/hybrid mode
- Enhanced security scanning integrations (Snyk, Trivy, SonarQube)
- VS Code extension

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.2.0 | 2026-04-20 | Pre-push deploy pipeline, 7 persona agents, 16-stage pipeline, GCP default |
| 2.1.0 | 2026-03-11 | 4 new agents (iac, cd, ci, e2e), 13-stage pipeline |
| 1.0.0 | 2026-02-08 | Initial release, 10 agents, Agent-MCP architecture |

---

## Deprecation Notices

- `GenerationAgent` / `generate` command — use `iac`, `cd`, `ci`, `e2e` instead
- `DeployReadinessAgent` — removed in v2.2, replaced by deploy-intent/design/validate pipeline
