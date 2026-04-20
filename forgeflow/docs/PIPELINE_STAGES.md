# ForgeFlow Pipeline Stages

ForgeFlow runs **16 stages** grouped into 4 phases. Each stage is backed by a dedicated Agent and MCP server. Stages can be run individually or in full sequence with `forgeflow run-all`.

---

## Full Pipeline (v2.2)

```
 ┌─ Analyse ──┐  ┌── Build ──────┐  ┌─ Quality ─┐  ┌──────────── Ship ─────────────┐
 │             │  │               │  │            │  │                                │
 DISCOVER      │  IAC             │  REVIEW       │  DEPLOY-INTENT                   │
    ↓          │     ↓            │     ↓         │     ↓                            │
 NORMALIZE     │  CD              │  TEST         │  DEPLOY-DESIGN (7 personas)      │
    ↓          │     ↓            │     ↓         │     ↓                            │
 DOCS          │  CI              │  SCAN         │  DEPLOY-VALIDATE (blocks push)   │
               │     ↓            │               │     ↓                            │
               │  E2E             │               │  SECRETS                         │
               │                  │               │     ↓                            │
               │                  │               │  LIFECYCLE                       │
               │                  │               │     ↓                            │
               │                  │               │  BRIDGE (git push)               │
               └──────────────────┘               └────────────────────────────────── ┘
```

---

## Stage Reference

### Phase 1: Analyse

#### `discover` — Stage 1
Scans the repository and produces an inventory used by all downstream stages.

**Agent:** DiscoveryAgent · **MCP:** discovery-mcp-server
**Generates:** `.forgeflow/inventory.json`
**Detects:** languages, frameworks, entry points, Docker/K8s presence, CI/CD configs, test frameworks

```bash
forgeflow discover --path ./my-repo
```

---

#### `normalize` — Stage 2
Adds missing standard files so the repo meets baseline engineering standards.

**Agent:** NormalizationAgent · **MCP:** normalize-mcp-server
**Generates:** `.gitignore`, `pyproject.toml`, `README.md` (if missing), `.editorconfig`

```bash
forgeflow normalize --path ./my-repo
```

---

#### `docs` — Stage 3
Generates architecture diagrams and documentation from the discovered inventory.

**Agent:** DocumentationAgent · **MCP:** diagram-generator-mcp-server
**Generates:** `docs/ARCHITECTURE.md`, Mermaid component diagram

```bash
forgeflow docs --path ./my-repo
```

---

### Phase 2: Build

#### `iac` — Stage 4
Generates Infrastructure as Code for the target cloud provider.

**Agent:** IACAgent · **MCP:** iac-mcp-server
**Generates:**
- `infrastructure/{cloud}/main.tf` — VPC, networking, IAM
- `infrastructure/{cloud}/variables.tf`, `outputs.tf`, `providers.tf`, `backend.tf`
- `Dockerfile` (language-aware, preserves existing)
- `docker-compose.yml`

```bash
forgeflow iac --path ./my-repo --cloud gcp
```

---

#### `cd` — Stage 5
Generates the GitOps delivery system.

**Agent:** CDAgent · **MCP:** cd-mcp-server
**Generates:**
- `.github/workflows/infra.yml` — Terraform provisioning
- `.github/workflows/deploy.yml` — Build → staging → E2E gate → approval → prod
- `infrastructure/k8s/base/` — Deployment, Service, ConfigMap, HPA
- `infrastructure/k8s/overlays/` — dev / staging / prod Kustomize overlays

```bash
forgeflow cd --path ./my-repo --repo-url https://github.com/org/repo
```

---

#### `ci` — Stage 6
Generates CI pipeline and dependency management.

**Agent:** CIAgent · **MCP:** ci-mcp-server
**Generates:**
- `.github/workflows/ci.yml` — build, lint, test, coverage
- `.github/workflows/security.yml` — SAST, secret scanning
- `.github/dependabot.yml` — automated dependency updates

```bash
forgeflow ci --path ./my-repo
```

---

#### `e2e` — Stage 7
Generates end-to-end test suite and CI workflow.

**Agent:** E2ETestingAgent · **MCP:** e2e-mcp-server
**Generates:**
- `playwright.config.ts` or `cypress.config.ts`
- `tests/e2e/` — auth, navigation, forms, API test specs
- `.github/workflows/e2e.yml`

```bash
forgeflow e2e --path ./my-repo --framework playwright
```

---

### Phase 3: Quality

#### `review` — Stage 8
Analyses Git history and code quality patterns.

**Agent:** CodeReviewAgent · **MCP:** git-mcp-server
**Output:** findings on commit frequency, PR size, code churn, tech debt indicators

```bash
forgeflow review --path ./my-repo
```

---

#### `test` — Stage 9
Runs test suite and reports coverage.

**Agent:** TestingAgent · **MCP:** cicd-mcp-server
**Output:** test results, coverage report, CI test config recommendations

```bash
forgeflow test --path ./my-repo
```

---

#### `scan` — Stage 10
Security vulnerability scan — SAST, dependency CVEs, hardcoded secrets, misconfigurations.

**Agent:** SecurityAgent · **MCP:** security-mcp-server
**Output:** SARIF report, CVE list, severity-classified findings

```bash
forgeflow scan --path ./my-repo --severity high
```

---

### Phase 4: Ship (Pre-Push Deployment Pipeline)

#### `deploy-intent` — Stage 11
Interactive deployment interview. Asks about cloud provider, region, compute model, SLOs, cost controls, and caches the answers in `.sevaforge/deployment-intent.yaml` so it never asks again.

**Agent:** DeployIntentAgent · **MCP:** intent-mcp-server
**Generates:** `.sevaforge/deployment-intent.yaml` with SHA256 integrity hash
**Derives from source:** app name, language, port, healthcheck path

```bash
forgeflow deploy-intent --path ./my-repo
forgeflow deploy-intent --path ./my-repo --force           # re-interview even if cached
forgeflow deploy-intent --path ./my-repo --non-interactive # use defaults
```

---

#### `deploy-design` — Stage 12
Fans out to **7 persona agents** running in **3 parallel layers** via ThreadPoolExecutor:

| Layer | Personas | What they produce |
|-------|----------|------------------|
| 1 (Foundation) | InfraArchitect, SecretsManager | VPC/subnets/firewall Terraform, secrets inventory + bootstrap script |
| 2 (Platform) | ClusterBuilder, AppDeployer | GKE/EKS cluster Terraform, Dockerfile + Helm chart + HPA |
| 3 (Operations) | ObservabilityEngineer, SecurityAuditor, CostGuardian | Prometheus/Grafana/SLOs, NetworkPolicy/PodSecurity, budget alerts/shutdown workflows |

Layer ordering is enforced: InfraArchitect must complete before ClusterBuilder (which references its network outputs).

**Agent:** DeployOrchestratorAgent · **MCP:** design-mcp-server
**Generates:** 26+ artifacts across `forgeflow/infrastructure/`, `deploy/helm/`, `deploy/secrets/`, `deploy/observability/`, `deploy/security/`, `deploy/cost/`, `.github/workflows/`

```bash
forgeflow deploy-design --path ./my-repo
forgeflow deploy-design --path ./my-repo --only infra-architect,app-deployer
forgeflow deploy-design --path ./my-repo --skip cost-guardian
```

---

#### `deploy-validate` — Stage 13
Cross-checks all persona artifacts for consistency. **Blocks the push if any check fails.**

**Agent:** DeployValidatorAgent · **MCP:** validate-mcp-server
**7 validation checks:**

1. `secrets_referenced_are_inventoried` — every inventoried secret is referenced in code
2. `cron_schedules_valid` — shutdown/teardown crons parse correctly
3. `dates_are_future` — teardown date hasn't passed
4. `slo_realistic` — availability target is between 90–99.999%
5. `intent_hash_matches` — intent file hasn't been tampered with since design phase
6. `terraform_vars_declared` — every `var.X` reference has a corresponding variable declaration
7. `image_repo_matches_cloud` — container registry prefix matches target cloud (gcr.io for GCP, ECR for AWS)

```bash
forgeflow deploy-validate --path ./my-repo
```

---

#### `secrets` — Stage 14
Generates secrets bootstrap guide, IAM policy files for all service accounts, and an interactive bootstrap script.

**Agent:** SecretsAgent · **MCP:** secrets-mcp-server
**Generates:** `scripts/bootstrap-secrets.sh`, IAM policy files, tool-specific setup guides

```bash
forgeflow secrets --path ./my-repo
```

---

#### `lifecycle` — Stage 15
Generates CI/CD lifecycle workflows that chain together: CI → Test → CD.

**Agent:** LifecycleAgent · **MCP:** lifecycle-mcp-server
**Generates:** `.github/workflows/` lifecycle chain

```bash
forgeflow lifecycle --path ./my-repo
```

---

#### `bridge` — Stage 16
Commits all generated files and pushes to GitHub, optionally creating a PR.

**Agent:** BridgeAgent · **MCP:** github-mcp-server

```bash
forgeflow bridge --path ./my-repo --repo your-org/your-repo
```

---

## Run All Stages

```bash
# Run full 16-stage pre-merge pipeline
forgeflow run-all ./my-repo

# Launch the web dashboard to monitor progress
forgeflow dashboard
```

---

## Deployment Intent — The Canonical Spec

The deploy-intent interview creates `.sevaforge/deployment-intent.yaml`, which all 7 personas read. Example:

```yaml
app:
  name: my-app
  language: python
  port: 8000
  healthcheck: /health

cloud:
  provider: gcp
  region: us-central1
  compute_model: kubernetes
  flavour: gke-autopilot

environments:
  - name: dev
    auto_promote: true
  - name: prod
    auto_promote: false

observability:
  stack: prometheus-grafana
  slo_availability: "99.5"
  slo_latency_p99_ms: 500

cost_controls:
  auto_shutdown:
    enabled: true
    schedule_down: "0 4 * * *"
    schedule_up: "0 14 * * *"

_meta:
  intent_hash: sha256:abc123...
  last_validated: "2026-04-20T12:00:00Z"
```
