# ForgeFlow Pipeline Stages

Complete reference for all pipeline stages introduced in v2.1.

---

## Pipeline Overview

The default `run-all` pipeline executes 10 stages in sequence, followed by an optional approval gate and post-merge stages.

```
┌──────────┐  ┌───────────┐  ┌──────┐  ┌─────┐  ┌────┐  ┌────┐  ┌──────┐
│ DISCOVER │→ │ NORMALIZE │→ │ DOCS │→ │ IAC │→ │ CD │→ │ CI │→ │ E2E  │
└──────────┘  └───────────┘  └──────┘  └─────┘  └────┘  └────┘  └──────┘
                                                                      │
                ┌─────────────────────────────────────────────────────┘
                ▼
         ┌────────┐  ┌──────┐  ┌──────┐     ┌──────────────┐
         │ REVIEW │→ │ TEST │→ │ SCAN │  →  │ APPROVAL GATE│
         └────────┘  └──────┘  └──────┘     └──────┬───────┘
                                                    │
                                               ┌────▼────┐
                                               │ BRIDGE  │
                                               └────┬────┘
                                                    │
                                    ┌───────────────┴──────────────┐
                                    │        Post-Merge (optional)  │
                                    │   ┌────────┐    ┌─────────┐  │
                                    │   │ DEPLOY │ →  │ MONITOR │  │
                                    │   └────────┘    └─────────┘  │
                                    └──────────────────────────────┘
```

---

## Stage Reference

### Stage 1 — `discover`
**Agent:** DiscoveryAgent · **MCP:** discovery-mcp

Scans the repository and builds an inventory of everything in it.

**What it does:**
- Counts and categorizes all files
- Detects programming languages and their proportions
- Identifies frameworks, build tools, and package managers
- Maps the component structure (api, tests, config, etc.)

**Output:** `staging/discover_report.md`

**CLI:**
```bash
forgeflow discover --path ./my-repo
```

---

### Stage 2 — `normalize`
**Agent:** NormalizationAgent · **MCP:** normalize-mcp

Standardizes the repository structure to follow best practices.

**What it does:**
- Adds missing standard files (`.gitignore`, `README.md`, `LICENSE`)
- Enforces consistent directory naming
- Adds linting/formatting configs if absent

**Output:** `staging/normalize_report.md`, modified repo files

**CLI:**
```bash
forgeflow normalize --path ./my-repo
```

---

### Stage 3 — `docs`
**Agent:** DocumentationAgent · **MCP:** diagram-generator-mcp

Generates documentation and architecture diagrams.

**What it does:**
- Creates architecture overview documentation
- Generates component dependency diagrams
- Produces API surface documentation

**Output:** `staging/docs_report.md`, generated docs in repo

**CLI:**
```bash
forgeflow docs --path ./my-repo
```

---

### Stage 4 — `iac` *(v2.1)*
**Agent:** IACAgent · **MCP:** iac-mcp

Generates Infrastructure as Code artifacts tailored to the detected stack.

**What it does:**
- Generates Terraform modules (VPC, EKS, RDS, S3, IAM) for AWS, GCP, or Azure
- Creates multi-stage Dockerfile optimized for the detected language
- Produces `docker-compose.yml` for local development
- Optionally generates Pulumi programs

**Output:** `terraform/`, `Dockerfile`, `docker-compose.yml`

**CLI:**
```bash
forgeflow iac --path ./my-repo
# With specific provider:
forgeflow iac --path ./my-repo --provider gcp
```

> **vs `generate`:** Use `iac` instead of `generate` for infrastructure artifacts. `iac` is more targeted and produces better-structured Terraform modules.

---

### Stage 5 — `cd` *(v2.1)*
**Agent:** CDAgent · **MCP:** cd-mcp

Generates Continuous Deployment configuration for GitOps workflows.

**What it does:**
- Creates ArgoCD `Application` manifests pointing to the repo
- Generates Kustomize `base/` and `overlays/` (dev, staging, production)
- Produces Helm `values.yaml` and release configuration

**Output:** `.argocd/`, `kustomize/`, `helm/`

**CLI:**
```bash
forgeflow cd --path ./my-repo
# With specific tool:
forgeflow cd --path ./my-repo --tool kustomize
```

---

### Stage 6 — `ci` *(v2.1)*
**Agent:** CIAgent · **MCP:** ci-mcp

Generates Continuous Integration pipeline configuration.

**What it does:**
- Creates GitHub Actions workflows (build, test, lint, security scan)
- Generates GitLab CI `.gitlab-ci.yml` pipeline
- Produces Jenkinsfile for Jenkins pipelines
- Configures branch protection rules and required status checks

**Output:** `.github/workflows/`, `.gitlab-ci.yml`, or `Jenkinsfile`

**CLI:**
```bash
forgeflow ci --path ./my-repo
# With specific platform:
forgeflow ci --path ./my-repo --platform gitlab
```

---

### Stage 7 — `e2e` *(v2.1)*
**Agent:** E2ETestingAgent · **MCP:** e2e-mcp

Scaffolds end-to-end test infrastructure and generates test stubs.

**What it does:**
- Initializes Playwright or Cypress configuration
- Generates test stubs for detected API endpoints and UI routes
- Creates CI integration for E2E test runs
- Configures test environment setup/teardown

**Output:** `e2e/` or `tests/e2e/`, updated CI config

**CLI:**
```bash
forgeflow e2e --path ./my-repo
# With specific framework:
forgeflow e2e --path ./my-repo --framework cypress
```

---

### Stage 8 — `review`
**Agent:** CodeReviewAgent · **MCP:** git-mcp

Analyzes git history and code quality.

**What it does:**
- Reviews recent git commits and PR history
- Identifies code hotspots and churn patterns
- Checks code complexity metrics
- Flags style inconsistencies

**Output:** `staging/review_report.md`

**CLI:**
```bash
forgeflow review --path ./my-repo
```

---

### Stage 9 — `test`
**Agent:** TestingAgent · **MCP:** cicd-mcp

Runs the project's existing test suite.

**What it does:**
- Detects and runs existing unit/integration tests
- Identifies missing test coverage areas
- Reports test results and failures

**Output:** `staging/test_report.md`

**CLI:**
```bash
forgeflow test --path ./my-repo
```

---

### Stage 10 — `scan`
**Agent:** SecurityAgent · **MCP:** security-mcp

Scans for security vulnerabilities, misconfigurations, and secrets.

**What it does:**
- Detects hardcoded secrets, tokens, and credentials
- Identifies dependency vulnerabilities
- Flags SQL injection, command injection, and insecure config patterns
- Filters findings by severity threshold

**Output:** `staging/scan_report.md`

**CLI:**
```bash
forgeflow scan --path ./my-repo --severity high
```

---

### Approval Gate — `bridge`
**Agent:** BridgeAgent · **MCP:** github-mcp

Pushes generated artifacts to GitHub and creates a Pull Request. Requires explicit user approval before running.

**What it does:**
- Initializes git repo if needed
- Commits all generated files
- Pushes to a feature branch
- Opens a Pull Request with a summary of all pipeline findings

**CLI:**
```bash
forgeflow bridge --operation push --repo owner/repo
```

---

### Post-Merge — `deploy` + `monitor`
**Agents:** DeploymentAgent, MonitoringAgent · **MCPs:** cloud-mcp, observability-mcp

Run optionally after the bridge stage merges. Triggered by `--include-post-merge`.

**deploy** — Provisions cloud infrastructure and deploys the application to the target environment (dev / staging / production).

**monitor** — Sets up Prometheus scrape configs, Grafana dashboards, and alerting rules.

**CLI:**
```bash
forgeflow run-all ./my-repo --include-post-merge
```

---

## Choosing Between `generate` and the v2.1 Stages

| Use case | Recommended command |
|----------|-------------------|
| Terraform + Docker + CI/CD all at once (legacy) | `generate` |
| Only Terraform / IaC artifacts | `iac` |
| Only CI pipeline (GitHub Actions, GitLab) | `ci` |
| Only CD config (ArgoCD, Helm, Kustomize) | `cd` |
| Only E2E test scaffolding | `e2e` |
| Full pipeline (recommended) | `run-all` |

`generate` remains available for backwards compatibility but does not benefit from the focused, stack-aware logic of the v2.1 agents.

---

## Running Individual Stages

Any stage can be run standalone without triggering the full pipeline:

```bash
# Run just infrastructure generation
forgeflow iac --path ./my-repo --provider aws

# Run just CI setup
forgeflow ci --path ./my-repo --platform github

# Run security scan only
forgeflow scan --path ./my-repo --severity medium

# Run audit (discover + normalize + scan + generate)
forgeflow audit --path ./my-repo
```

## Customizing the Pipeline Sequence

Edit `config/forgeflow-config.yaml` to add, remove, or reorder stages:

```yaml
pipeline:
  sequence:
    - discover
    - normalize
    - docs
    - iac        # Remove this line to skip IaC generation
    - cd
    - ci
    - e2e        # Remove this line to skip E2E scaffolding
    - review
    - test
    - scan
```
