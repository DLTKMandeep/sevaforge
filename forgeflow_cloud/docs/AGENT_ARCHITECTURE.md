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

| Command   | Agent                | MCP Server              | Description                      |
|-----------|---------------------|-------------------------|----------------------------------|
| discover  | DiscoveryAgent      | discovery_mcp           | Scans repo structure             |
| normalize | NormalizationAgent  | normalize_mcp           | Standardizes repo structure      |
| scan      | SecurityAgent       | security_mcp            | Security vulnerability scanning  |
| generate  | GenerationAgent     | deployment_mcp          | Generates deployment artifacts   |
| deploy    | DeploymentAgent     | cloud_mcp               | Cloud infrastructure deployment  |
| test      | TestingAgent        | cicd_mcp                | Runs tests, CI/CD operations     |
| monitor   | MonitoringAgent     | observability_mcp       | Sets up monitoring               |
| docs      | DocumentationAgent  | diagram_generator_mcp   | Generates documentation          |
| review    | CodeReviewAgent     | git_mcp                 | Code review, git analysis        |
| bridge    | BridgeAgent         | github_mcp              | GitHub integration               |

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
│   ├── __init__.py           # Exports all agents
│   ├── base_agent.py         # BaseAgent class
│   ├── discovery_agent.py    # DiscoveryAgent
│   ├── normalization_agent.py
│   ├── security_agent.py
│   ├── generation_agent.py
│   ├── deployment_agent.py
│   ├── testing_agent.py
│   ├── monitoring_agent.py
│   ├── documentation_agent.py
│   ├── code_review_agent.py
│   └── bridge_agent.py
├── mcp_servers/
│   ├── discovery_mcp/        # MCP protocol layer
│   │   └── server.py         # Delegates to DiscoveryAgent
│   ├── normalize_mcp/
│   ├── security_mcp/
│   ├── deployment_mcp/
│   ├── cloud_mcp/
│   ├── cicd_mcp/
│   ├── observability_mcp/
│   ├── diagram_generator_mcp/
│   ├── git_mcp/
│   └── github_mcp/
├── core/
│   └── orchestrator.py       # MCPOrchestrator
└── cli/
    └── mission_control.py    # CLI entry point
```
