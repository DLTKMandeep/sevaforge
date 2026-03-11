# ForgeFlow Agent Architecture

## Overview

ForgeFlow uses a layered architecture where all business logic is performed by specialized **Agents**, each backed by an **MCP Server** that acts as a thin protocol/communication layer.

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Command                               │
│                   (e.g., forge discover)                        │
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

## Command → Agent → MCP Server Mapping

> **v2.1** added four new specialized generation commands (iac, cd, ci, e2e) which run between `docs` and `review` in the default pipeline.

| Command     | Agent                  | MCP Server              | Pipeline Order | Description                                        |
|-------------|------------------------|-------------------------|----------------|----------------------------------------------------|
| discover    | DiscoveryAgent         | discovery_mcp           | 1              | Scans repo structure, languages, components        |
| normalize   | NormalizationAgent     | normalize_mcp           | 2              | Standardizes repo structure and best-practice files|
| docs        | DocumentationAgent     | diagram_generator_mcp   | 3              | Generates architecture diagrams and API docs       |
| **iac**     | **IACAgent**           | **iac_mcp**             | **4 (v2.1)**   | **Terraform, Dockerfile, Pulumi generation**       |
| **cd**      | **CDAgent**            | **cd_mcp**              | **5 (v2.1)**   | **ArgoCD, Kustomize, Helm CD config**              |
| **ci**      | **CIAgent**            | **ci_mcp**              | **6 (v2.1)**   | **GitHub Actions, GitLab CI, Jenkins setup**       |
| **e2e**     | **E2ETestingAgent**    | **e2e_mcp**             | **7 (v2.1)**   | **Playwright, Cypress test scaffolding**           |
| review      | CodeReviewAgent        | git_mcp                 | 8              | Git history analysis and code quality review       |
| test        | TestingAgent           | cicd_mcp                | 9              | Unit/integration test execution                    |
| scan        | SecurityAgent          | security_mcp            | 10             | Security vulnerability and secrets scanning        |
| generate    | GenerationAgent        | deployment_mcp          | (legacy)       | Generic artifact generation — prefer iac/ci/cd     |
| deploy      | DeploymentAgent        | cloud_mcp               | post-merge     | Cloud deployment — AWS, GCP, Azure                 |
| monitor     | MonitoringAgent        | observability_mcp       | post-merge     | Prometheus and Grafana configuration               |
| bridge      | BridgeAgent            | github_mcp              | approval gate  | GitHub push, PR creation, repo management          |

## Agent Classes

All agents inherit from `BaseAgent` and implement the `execute()` method:

```python
from agents import BaseAgent

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
3. **Testability**: Agents can be unit tested independently
4. **Extensibility**: Add new capabilities by creating new Agent + MCP Server pairs
5. **Lazy Loading**: MCP servers are started on-demand by the Orchestrator

## Directory Structure

```
forgeflow/
├── agents/
│   ├── __init__.py              # Exports all agents
│   ├── base_agent.py            # BaseAgent abstract class
│   ├── discovery_agent.py       # Stage 1
│   ├── normalization_agent.py   # Stage 2
│   ├── documentation_agent.py   # Stage 3
│   ├── iac_agent.py             # Stage 4 — v2.1
│   ├── cd_agent.py              # Stage 5 — v2.1
│   ├── ci_agent.py              # Stage 6 — v2.1
│   ├── e2e_agent.py             # Stage 7 — v2.1
│   ├── code_review_agent.py     # Stage 8
│   ├── testing_agent.py         # Stage 9
│   ├── security_agent.py        # Stage 10
│   ├── generation_agent.py      # Legacy
│   ├── deployment_agent.py      # Post-merge
│   ├── monitoring_agent.py      # Post-merge
│   └── bridge_agent.py          # Approval gate
├── mcp_servers/
│   ├── discovery_mcp/           # MCP protocol layer → DiscoveryAgent
│   │   └── server.py
│   ├── normalize_mcp/
│   ├── diagram_generator_mcp/
│   ├── iac_mcp/                 # v2.1
│   ├── cd_mcp/                  # v2.1
│   ├── ci_mcp/                  # v2.1
│   ├── e2e_mcp/                 # v2.1
│   ├── git_mcp/
│   ├── cicd_mcp/
│   ├── security_mcp/
│   ├── deployment_mcp/
│   ├── cloud_mcp/
│   ├── observability_mcp/
│   └── github_mcp/
├── core/
│   └── orchestrator.py          # MCPOrchestrator — lazy subprocess management
└── cli/
    ├── forgeflow.py             # CLI entry point (Click)
    └── mission_control.py       # Command routing and result display
```
