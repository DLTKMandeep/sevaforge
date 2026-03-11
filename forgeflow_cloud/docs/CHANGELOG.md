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

## [Unreleased]

### Planned

- Azure and GCP Terraform modules (extended coverage)
- Helm chart generation improvements
- Enhanced security scanning integrations (Snyk, Trivy, SonarQube)
- Parallel stage execution (`features.parallel_execution: true`)
- Web UI dashboard
- VS Code extension

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.1.0 | 2026-03-11 | 4 new agents (iac, cd, ci, e2e), updated 10-stage pipeline |
| 1.0.0 | 2026-02-08 | Initial release |

---

## Migration Guides

### From Pre-release to 1.0.0

No migration needed - this is the first stable release.

---

## Deprecation Notices

None at this time.
