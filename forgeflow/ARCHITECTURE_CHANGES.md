# ForgeFlow Architecture Changes

## Unified Package (Current — `unified` branch)

### What changed
The three-repo architecture (`sevaforge_local`, `sevaforge_cloud`, `sevaforge_hybrid`) has been consolidated into a single unified package named `forgeflow`.

**Before:** three separate repos, three-way sync on every change, confusing mode names
**After:** one package, two modes (`local` | `cloud`), one branch to maintain

### Mode simplification
- `local` — all MCPs run as Python modules on your machine (default, offline capable)
- `cloud` — all MCPs route via HTTP to ForgeFlow cloud endpoints (requires `FORGEFLOW_API_KEY`)
- `hybrid` — **removed.** Cloud mode now falls back to local automatically if an endpoint is unreachable, achieving the same effect without the naming confusion.

### CDAgent: workflows moved into the engine
`infra.yml` and `bootstrap.yml` were previously hand-crafted files. They are now owned by `CDAgent` as `INFRA_WORKFLOW_TEMPLATE` and `BOOTSTRAP_WORKFLOW_TEMPLATE` constants. Every project that runs `forgeflow cd` gets these files generated automatically.

### Onboarding: no more shell scripts
`forgeflow secrets bootstrap` is now a fully interactive Python wizard. It prompts for 4 values, sets GitHub secrets directly via `gh secret set`, creates environments, and configures branch protection — no `bash scripts/setup-github.sh` required.

### Secrets architecture
Secrets are now split into two clear tiers:
- **Human-managed (4):** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `GH_PAT`
- **Auto-managed by ForgeFlow workflows:** `ARGOCD_SERVER`, `ARGOCD_AUTH_TOKEN`, `EKS_CLUSTER_NAME`, `STAGING_URL`, `PROD_URL`

---

## Previous: v2.1 Specialised Agents

Introduced dedicated agents for each pipeline stage replacing the monolithic `GenerationAgent`:
- `IACAgent` — Terraform + Docker
- `CDAgent` — ArgoCD + Kustomize + GitHub Actions workflows
- `CIAgent` — GitHub Actions CI + Dependabot
- `E2ETestingAgent` — Playwright + Cypress

STAGE_MAPPING in `display.py` updated to map all 14 stages to their MCP server + agent.
