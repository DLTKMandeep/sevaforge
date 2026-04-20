# ForgeFlow Architecture Changes

## v2.2 — Pre-Push Deployment Pipeline (Current)

### What changed
The post-push `DeployReadinessAgent` has been replaced with a 3-stage pre-push deployment pipeline. Pipeline grows from 13 to **16 stages**.

**Before:** DeployReadinessAgent ran after push, producing a readiness report too late to fix anything.
**After:** Three new stages run before bridge (push): deploy-intent → deploy-design → deploy-validate.

### New stages (inserted between scan and secrets)
- **deploy-intent** — Interactive interview captures cloud/region/compute/SLOs/cost. Cached in `.sevaforge/deployment-intent.yaml`.
- **deploy-design** — 7 persona agents run in 3 parallel layers via ThreadPoolExecutor, producing 26+ artifacts.
- **deploy-validate** — 7 cross-checks (secrets, crons, SLOs, hash integrity, Terraform vars, image repo, dates). Blocks push on failure.

### 7 Persona Agents
Layer 1 (Foundation): InfraArchitect, SecretsManager
Layer 2 (Platform): ClusterBuilder, AppDeployer
Layer 3 (Operations): ObservabilityEngineer, SecurityAuditor, CostGuardian

### Inventory-anchored validation
The validator no longer scans `${VAR}` patterns heuristically. It trusts the SecretsManager persona's `deploy/secrets/inventory.yaml` and verifies that every inventoried secret is referenced in code.

### Dashboard integration
The React dashboard, SSE log streaming, and CLI all support 16 stages with the 3 new deploy stages in the Ship phase.

### Removed
- `DeployReadinessAgent` — deleted (`agents/deploy_readiness_agent.py`)
- `readiness-mcp-server` — removed from `mcp-config.yaml` and `forgeflow-config.yaml`
- `test_deploy_readiness.py` — deleted

### Files added
- `agents/deploy_intent_agent.py`, `deploy_orchestrator_agent.py`, `deploy_validator_agent.py`
- `agents/personas/` — 7 persona modules + `base_persona.py`
- `tests/test_deploy_intent.py` (11 tests), `test_deploy_orchestrator.py` (8 tests), `test_deploy_validator.py` (13 tests), `test_personas.py` (20 tests)

---

## v2.1 — Specialized Build Agents

Introduced dedicated agents for each pipeline stage replacing the monolithic `GenerationAgent`:
- `IACAgent` — Terraform + Docker
- `CDAgent` — ArgoCD + Kustomize + GitHub Actions workflows
- `CIAgent` — GitHub Actions CI + Dependabot
- `E2ETestingAgent` — Playwright + Cypress

STAGE_MAPPING in `display.py` updated to map all stages to their MCP server + agent.

---

## v2.0 — Unified Package

### What changed
The three-repo architecture (`sevaforge_local`, `sevaforge_cloud`, `sevaforge_hybrid`) has been consolidated into a single unified package named `forgeflow`.

**Before:** three separate repos, three-way sync on every change, confusing mode names
**After:** one package, two modes (`local` | `cloud`), one branch to maintain

### Mode simplification
- `local` — all MCPs run as Python modules on your machine (default, offline capable)
- `cloud` — all MCPs route via HTTP to ForgeFlow cloud endpoints (requires `FORGEFLOW_API_KEY`)
- `hybrid` — **removed.** Cloud mode now falls back to local automatically if an endpoint is unreachable.

### CDAgent: workflows moved into the engine
`infra.yml` and `bootstrap.yml` are now owned by `CDAgent` as template constants. Every project that runs `forgeflow cd` gets these files generated automatically.

### Onboarding: no more shell scripts
`forgeflow secrets bootstrap` is now a fully interactive Python wizard. It prompts for values, sets GitHub secrets via `gh secret set`, creates environments, and configures branch protection.
