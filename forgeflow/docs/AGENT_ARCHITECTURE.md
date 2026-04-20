# ForgeFlow Agent Architecture

## Overview

ForgeFlow uses a layered architecture where all business logic is performed by specialized **Agents**, each backed by an **MCP Server** that acts as a thin protocol/communication layer. In v2.2, the architecture was extended with a **persona system** — 7 specialized deployment agents that run in parallel during the deploy-design stage.

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Command                               │
│                   (e.g., forgeflow run-all)                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MCPOrchestrator                            │
│                                                                 │
│  - Loads mcp-config.yaml                                        │
│  - Maps commands to MCP servers                                 │
│  - Manages server lifecycle (lazy start)                        │
│  - Dispatches tasks to appropriate servers                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       MCP Server                                │
│                   (Protocol Layer)                              │
│                                                                 │
│  - Thin wrapper around Agent                                    │
│  - Handles MCP protocol                                         │
│  - Delegates to corresponding Agent                             │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Agent                                   │
│                   (Business Logic)                              │
│                                                                 │
│  - Contains all actual logic                                    │
│  - Performs scanning, analysis, generation                      │
│  - Returns structured results                                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Results                                  │
│                                                                 │
│  - status: success/warning/error                                │
│  - summary: Brief description                                   │
│  - data: Detailed results                                       │
│  - findings: List of findings                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Command → Agent → MCP Server Mapping (v2.2)

| Command | Agent | MCP Server | Pipeline Order | Phase | Description |
|---------|-------|-----------|----------------|-------|-------------|
| discover | DiscoveryAgent | discovery_mcp | 1 | Analyse | Scans repo structure, languages, components |
| normalize | NormalizationAgent | normalize_mcp | 2 | Analyse | Standardizes repo structure and best-practice files |
| docs | DocumentationAgent | diagram_generator_mcp | 3 | Analyse | Generates architecture diagrams and docs |
| iac | IACAgent | iac_mcp | 4 | Build | Terraform, Dockerfile generation |
| cd | CDAgent | cd_mcp | 5 | Build | GitOps delivery system (workflows, K8s, Kustomize) |
| ci | CIAgent | ci_mcp | 6 | Build | GitHub Actions CI pipeline |
| e2e | E2ETestingAgent | e2e_mcp | 7 | Build | Playwright/Cypress test scaffolding |
| review | CodeReviewAgent | git_mcp | 8 | Quality | Git history analysis, code quality review |
| test | TestingAgent | cicd_mcp | 9 | Quality | Unit/integration test execution |
| scan | SecurityAgent | security_mcp | 10 | Quality | Security vulnerability and secrets scanning |
| deploy-intent | DeployIntentAgent | intent_mcp | 11 | Ship | Interactive deployment interview + caching |
| deploy-design | DeployOrchestratorAgent | design_mcp | 12 | Ship | 7-persona parallel fan-out |
| deploy-validate | DeployValidatorAgent | validate_mcp | 13 | Ship | 7-check pre-push gate |
| secrets | SecretsAgent | secrets_mcp | 14 | Ship | Secrets bootstrap guide + IAM policies |
| lifecycle | LifecycleAgent | lifecycle_mcp | 15 | Ship | CI/CD lifecycle workflow chain |
| bridge | BridgeAgent | github_mcp | 16 | Ship | GitHub push, PR creation |

---

## The Persona System (v2.2)

The deploy-design stage introduces a **persona system** where 7 specialized agents run in 3 parallel layers inside a single pipeline stage.

### Persona Architecture

```
DeployOrchestratorAgent
    │
    ├── reads .sevaforge/deployment-intent.yaml
    │
    ├── Layer 1 (Foundation) ──── ThreadPoolExecutor ────┐
    │       InfraArchitectPersona                         │
    │       SecretsManagerPersona                         │
    │                                                     │
    ├── Layer 2 (Platform) ────── ThreadPoolExecutor ────┤  (sequential layers,
    │       ClusterBuilderPersona                         │   parallel within layer)
    │       AppDeployerPersona                            │
    │                                                     │
    └── Layer 3 (Operations) ──── ThreadPoolExecutor ────┘
            ObservabilityEngineerPersona
            SecurityAuditorPersona
            CostGuardianPersona
```

Layer ordering is enforced because later layers depend on earlier outputs (e.g., ClusterBuilder references InfraArchitect's network topology).

### Persona Base Class

All personas inherit from `BasePersona` which extends `BaseAgent`:

```python
from agents.personas.base_persona import BasePersona

class MyPersona(BasePersona):
    def __init__(self):
        super().__init__(
            name="my_persona",
            description="Does something specialized"
        )

    def execute(self, params: dict) -> dict:
        intent = self.load_intent(params["path"])
        # Generate artifacts based on intent
        self.write_artifact(path, content)
        return self.create_result(
            status='success',
            summary='Artifacts generated',
            data={'artifacts': [...]},
            findings=['Finding 1']
        )
```

### Persona Output Map

| Persona | Output Path | Key Artifacts |
|---------|------------|---------------|
| InfraArchitectPersona | `forgeflow/infrastructure/{cloud}/` | `network.tf`, `variables.tf`, `providers.tf`, `backend.tf` |
| SecretsManagerPersona | `deploy/secrets/` | `inventory.yaml`, `bootstrap.sh`, `DEPLOYMENT_SECRETS_GUIDE.md` |
| ClusterBuilderPersona | `forgeflow/infrastructure/{cloud}/` | `cluster.tf` (GKE Autopilot / EKS / AKS / OKE) |
| AppDeployerPersona | `deploy/helm/{app}/`, root | `Chart.yaml`, `values.yaml`, `templates/`, `Dockerfile` |
| ObservabilityEngineerPersona | `deploy/observability/` | `prometheus-values.yaml`, `servicemonitor.yaml`, `slo.yaml`, `alerts.yaml` |
| SecurityAuditorPersona | `deploy/security/` | `networkpolicy.yaml`, `pod-security.yaml`, `iam-minimization.md` |
| CostGuardianPersona | `deploy/cost/`, `.github/workflows/` | `budget-alert.tf`, `cost-shutdown.yml`, `cost-teardown.yml` |

---

## Agent Classes

All agents inherit from `BaseAgent` and implement the `execute()` method:

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="my_agent",
            description="Does something useful"
        )

    def execute(self, params: dict) -> dict:
        # Business logic here
        return self.create_result(
            status='success',
            summary='Task completed',
            data={'key': 'value'},
            findings=['Finding 1', 'Finding 2']
        )
```

## MCP Server Structure

MCP servers are thin protocol layers that delegate to agents:

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import MyAgent

_agent = MyAgent()

def run(params: dict) -> dict:
    """Delegate to agent for business logic."""
    return _agent.execute(params)
```

## Key Principles

1. **Separation of Concerns**: MCP servers handle protocol, Agents handle logic
2. **Single Responsibility**: Each Agent handles one domain
3. **Testability**: Agents can be unit tested independently (51+ deploy pipeline tests)
4. **Extensibility**: Add new capabilities by creating new Agent + MCP Server pairs
5. **Lazy Loading**: MCP servers are started on-demand by the Orchestrator
6. **Parallel Execution**: Persona agents within a layer run concurrently via ThreadPoolExecutor
7. **Inventory-Anchored Validation**: The validator trusts the SecretsManager's inventory rather than scanning for secrets heuristically

## Directory Structure

```
forgeflow/
├── agents/
│   ├── __init__.py                        # Exports all agents
│   ├── base_agent.py                      # BaseAgent abstract class
│   ├── discovery_agent.py                 # Stage 1 — Analyse
│   ├── normalization_agent.py             # Stage 2 — Analyse
│   ├── documentation_agent.py             # Stage 3 — Analyse
│   ├── iac_agent.py                       # Stage 4 — Build
│   ├── cd_agent.py                        # Stage 5 — Build
│   ├── ci_agent.py                        # Stage 6 — Build
│   ├── e2e_agent.py                       # Stage 7 — Build
│   ├── code_review_agent.py              # Stage 8 — Quality
│   ├── testing_agent.py                   # Stage 9 — Quality
│   ├── security_agent.py                  # Stage 10 — Quality
│   ├── deploy_intent_agent.py             # Stage 11 — Ship (v2.2)
│   ├── deploy_orchestrator_agent.py       # Stage 12 — Ship (v2.2)
│   ├── deploy_validator_agent.py          # Stage 13 — Ship (v2.2)
│   ├── secrets_agent.py                   # Stage 14 — Ship
│   ├── lifecycle_agent.py                 # Stage 15 — Ship
│   ├── bridge_agent.py                    # Stage 16 — Ship
│   ├── deployment_agent.py                # Post-merge
│   ├── monitoring_agent.py                # Post-merge
│   └── personas/                          # v2.2 persona system
│       ├── __init__.py                    # Exports all 7 personas
│       ├── base_persona.py                # BasePersona (extends BaseAgent)
│       ├── infra_architect_persona.py     # Layer 1
│       ├── secrets_manager_persona.py     # Layer 1
│       ├── cluster_builder_persona.py     # Layer 2
│       ├── app_deployer_persona.py        # Layer 2
│       ├── observability_engineer_persona.py  # Layer 3
│       ├── security_auditor_persona.py    # Layer 3
│       └── cost_guardian_persona.py       # Layer 3
├── mcp_servers/
│   ├── discovery_mcp/server.py
│   ├── normalize_mcp/server.py
│   ├── diagram_generator_mcp/server.py
│   ├── iac_mcp/server.py
│   ├── cd_mcp/server.py
│   ├── ci_mcp/server.py
│   ├── e2e_mcp/server.py
│   ├── git_mcp/server.py
│   ├── cicd_mcp/server.py
│   ├── security_mcp/server.py
│   ├── github_mcp/server.py
│   ├── cloud_mcp/server.py
│   └── observability_mcp/server.py
├── core/
│   ├── mission_control.py                 # PIPELINE_STAGES, run_all orchestration
│   ├── orchestrator.py                    # MCPOrchestrator — lazy subprocess management
│   └── display.py                         # STAGE_MAPPING, STAGE_COLORS
├── gui/
│   └── dashboard_server.py                # SSE log streaming to React dashboard
├── ui/
│   └── index.html                         # React dashboard (16 stages, 4 phases)
├── cli/
│   └── forgeflow.py                       # CLI entry point (argparse + 16 subcommands)
└── tests/
    ├── test_deploy_intent.py              # 11 tests
    ├── test_deploy_orchestrator.py         # 8 tests
    ├── test_deploy_validator.py            # 13 tests
    └── test_personas.py                    # 20 tests
```
