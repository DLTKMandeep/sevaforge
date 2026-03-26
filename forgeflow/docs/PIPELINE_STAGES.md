# ForgeFlow Pipeline Stages

ForgeFlow runs 14 stages. Each stage is backed by a dedicated Agent and MCP server. Stages can be run individually or in full sequence with `forgeflow run-all`.

---

## Full Pipeline

```
DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → BRIDGE
                                                                              │
                                                          (post-merge) DEPLOY → MONITOR
```

---

## Stage Reference

### `discover`
Scans the repository and produces an inventory used by all downstream stages.

**Generates:** `.forgeflow/inventory.json`
**Detects:** languages, frameworks, entry points, Docker/K8s presence, CI/CD configs, test frameworks

```bash
forgeflow discover --path ./my-repo
```

---

### `normalize`
Adds missing standard files so the repo meets baseline engineering standards.

**Generates:** `.gitignore`, `pyproject.toml`, `README.md` (if missing), `.editorconfig`

```bash
forgeflow normalize --path ./my-repo
```

---

### `docs`
Generates architecture diagrams and documentation from the discovered inventory.

**Generates:** `docs/ARCHITECTURE.md`, `docs/API.md`, Mermaid component diagram

```bash
forgeflow docs --path ./my-repo
```

---

### `iac`
Generates Infrastructure as Code for AWS (or GCP/Azure).

**Generates:**
- `infrastructure/terraform/main.tf` — EKS, VPC, IAM, ECR modules
- `infrastructure/terraform/variables.tf`, `outputs.tf`
- `Dockerfile` (language-aware)
- `docker-compose.yml`

```bash
forgeflow iac --path ./my-repo --cloud aws
```

---

### `cd` ← Core Stage
Generates the complete GitOps delivery system. This is the stage that makes everything run in the cloud.

**Generates:**
- `.github/workflows/infra.yml` — Terraform provisioning in GitHub Actions
- `.github/workflows/bootstrap.yml` — ArgoCD bootstrap + auto-write secrets
- `.github/workflows/deploy.yml` — Build → staging → E2E gate → approval → prod
- `infrastructure/k8s/base/` — Deployment, Service, ConfigMap, HPA
- `infrastructure/k8s/overlays/` — dev / staging / prod Kustomize overlays
- `infrastructure/k8s/argocd/` — AppProject + ApplicationSet
- `infrastructure/k8s/secrets/` — External Secrets Operator manifests
- `RUNBOOK.md` — Complete operational guide

```bash
forgeflow cd --path ./my-repo --repo-url https://github.com/org/repo
forgeflow cd --path ./my-repo --overwrite   # refresh existing files
```

---

### `ci`
Generates GitHub Actions CI pipeline and dependency management.

**Generates:**
- `.github/workflows/ci.yml` — build, lint, test, coverage
- `.github/workflows/security.yml` — SAST, secret scanning
- `.github/workflows/release.yml` — semantic versioning + GHCR publish
- `.github/dependabot.yml` — automated dependency updates

```bash
forgeflow ci --path ./my-repo
```

---

### `e2e`
Generates end-to-end test suite and CI workflow.

**Generates:**
- `playwright.config.ts` or `cypress.config.ts`
- `tests/e2e/` — auth, navigation, forms, API test specs
- `.github/workflows/e2e.yml`

```bash
forgeflow e2e --path ./my-repo
forgeflow e2e --path ./my-repo --framework cypress
```

---

### `review`
Analyses Git history and code quality patterns.

**Output:** findings on commit frequency, PR size, code churn, tech debt indicators

```bash
forgeflow review --path ./my-repo
```

---

### `test`
Runs test suite and reports coverage.

**Output:** test results, coverage report, CI test config recommendations

```bash
forgeflow test --path ./my-repo
```

---

### `scan`
Security vulnerability scan — SAST, dependency CVEs, hardcoded secrets, misconfigurations.

```bash
forgeflow scan --path ./my-repo
forgeflow scan --path ./my-repo --severity high   # only show high/critical
```

---

### `bridge`
GitHub integration — creates PRs, pushes branches, manages repository settings.

```bash
forgeflow bridge --path ./my-repo
```

---

### `deploy` *(post-merge)*
Triggers deployment after the bridge stage merges the PR.

```bash
forgeflow deploy --path ./my-repo --target staging
forgeflow deploy --path ./my-repo --target production
```

---

### `monitor` *(post-merge)*
Generates monitoring configuration.

**Generates:** `monitoring/prometheus.yml`, `monitoring/grafana/` dashboards

```bash
forgeflow monitor --path ./my-repo
```

---

## Run All Stages

```bash
# Run full pre-merge pipeline
forgeflow run-all ./my-repo

# Include post-merge stages
forgeflow run-all ./my-repo --include-post-merge
```

---

## secrets (CLI command, not a stage)

The `secrets` command manages GitHub Actions secrets for the deploy pipeline. It is not a pipeline stage but runs independently.

```bash
forgeflow secrets list       # show all required secrets, their purpose, and source
forgeflow secrets check      # query GitHub to see which are set
forgeflow secrets bootstrap  # interactive wizard: prompts for 4 values, sets everything
```

The wizard collects: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `GH_PAT`.
Everything else (`ARGOCD_SERVER`, `ARGOCD_AUTH_TOKEN`, `EKS_CLUSTER_NAME`) is written automatically by ForgeFlow's GitHub Actions after the cluster is provisioned.
