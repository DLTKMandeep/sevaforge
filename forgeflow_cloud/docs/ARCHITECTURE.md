# ForgeFlow Architecture

Technical architecture documentation for ForgeFlow.

---

## Overview

ForgeFlow uses a layered **Agent-MCP (Model Context Protocol)** architecture that separates concerns between command parsing, orchestration, protocol handling, and business logic.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ForgeFlow Architecture                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐                                                       │
│   │    CLI Layer     │  forgeflow.py - Argument parsing, user interface      │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │  Mission Control │  mission_control.py - Command routing, result display │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │   Orchestrator   │  orchestrator.py - MCP lifecycle, subprocess mgmt     │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │   MCP Servers    │  Protocol bridge - Thin wrapper around agents         │
│   └────────┬─────────┘                                                       │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────┐                                                       │
│   │     Agents       │  Business logic - All functionality lives here        │
│   └──────────────────┘                                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Details

### 1. CLI Layer (`cli/forgeflow.py`)

**Responsibility:** Parse command-line arguments and delegate to Mission Control.

```python
# CLI does ONLY argument parsing
def main():
    parser = create_parser()
    args = parser.parse_args()
    
    mc = MissionControl(mode=args.mode)
    result = mc.discover(args.path)  # Delegate to Mission Control
    mc.print_result(result)
```

**Key Principles:**
- No business logic
- No direct MCP interaction
- Clean separation from core functionality

### 2. Mission Control (`core/mission_control.py`)

**Responsibility:** Route commands, manage orchestrator, format results.

```python
class MissionControl:
    def __init__(self, mode="local"):
        self.orchestrator = MCPOrchestrator(mode)
    
    def discover(self, path: str) -> Dict:
        return self.orchestrator.call_mcp(
            "discovery-mcp-server",
            {"action": "discover", "repo_path": path}
        )
```

**Features:**
- Unified command interface
- Result formatting with Rich console
- Composite command orchestration (audit, run-all)

### 3. Orchestrator (`core/orchestrator.py`)

**Responsibility:** MCP server lifecycle management.

```python
class MCPOrchestrator:
    def __init__(self, mode="local"):
        self.running_servers = {}  # Lazy-started servers
    
    def ensure_server(self, server_name: str):
        """Start server if not running (lazy initialization)"""
        if server_name not in self.running_servers:
            self._start_server(server_name)
```

**Features:**
- Lazy server startup
- Subprocess management
- Mode-aware routing (local/hybrid/cloud)
- Graceful shutdown

### 4. MCP Servers (`mcp_servers/*/server.py`)

**Responsibility:** Protocol bridge between Orchestrator and Agents.

```python
# MCP Server is a THIN wrapper
from agents import DiscoveryAgent

agent = DiscoveryAgent()

def run(params: dict) -> dict:
    return agent.execute(params)  # Delegate to Agent
```

**Key Principles:**
- No business logic
- Single responsibility: protocol translation
- Stateless (agent maintains state)

### 5. Agents (`agents/*.py`)

**Responsibility:** ALL business logic lives in agents.

```python
class DiscoveryAgent(BaseAgent):
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get("repo_path", "."))
        
        # Business logic here
        files = self._scan_directory(repo_path)
        languages = self._detect_languages(files)
        
        return self.create_result(
            status="success",
            summary=f"Discovered {len(files)} files",
            data={"files": files, "languages": languages}
        )
```

---

## Agent Architecture

### Base Agent

All agents inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(name)
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute agent logic - must be implemented"""
        pass
    
    def create_result(self, status, summary, data=None, findings=None):
        """Standardized result format"""
        return {
            "status": status,
            "summary": summary,
            "data": data or {},
            "findings": findings or [],
            "timestamp": datetime.now().isoformat()
        }
```

### Agent Catalog

> **v2.1:** Four new specialized generation agents were added (IACAgent, CDAgent, CIAgent, E2ETestingAgent), expanding the pipeline from 10 to 14 agents.

| Agent | MCP Server | CLI Command | Purpose |
|-------|------------|-------------|---------|
| DiscoveryAgent | discovery-mcp | `discover` | Repository scanning and component inventory |
| NormalizationAgent | normalize-mcp | `normalize` | Structure standardization and best-practice scaffolding |
| DocumentationAgent | diagram-generator-mcp | `docs` | Architecture diagrams and API documentation |
| **IACAgent** *(v2.1)* | **iac-mcp** | **`iac`** | **Infrastructure as Code — Terraform, Docker, Pulumi** |
| **CDAgent** *(v2.1)* | **cd-mcp** | **`cd`** | **Continuous Deployment — ArgoCD, Kustomize, Helm** |
| **CIAgent** *(v2.1)* | **ci-mcp** | **`ci`** | **Continuous Integration — GitHub Actions, GitLab CI** |
| **E2ETestingAgent** *(v2.1)* | **e2e-mcp** | **`e2e`** | **End-to-end testing — Playwright, Cypress** |
| CodeReviewAgent | git-mcp | `review` | Git history analysis and code quality review |
| TestingAgent | cicd-mcp | `test` | Unit/integration test execution |
| SecurityAgent | security-mcp | `scan` | Vulnerability detection and secrets scanning |
| GenerationAgent | deployment-mcp | `generate` | Generic artifact generation (legacy, prefer `iac`/`ci`/`cd`) |
| DeploymentAgent | cloud-mcp | `deploy` | Cloud deployment — AWS, GCP, Azure |
| MonitoringAgent | observability-mcp | `monitor` | Prometheus and Grafana configuration |
| BridgeAgent | github-mcp | `bridge` | GitHub push, PR creation, repo management |

---

## Data Flow

### Single Command Flow

```
User: forgeflow discover --path ./repo
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ CLI: Parse args, create MissionControl                          │
│      mc = MissionControl(mode="local")                          │
│      result = mc.discover("./repo")                             │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ MissionControl: Route to orchestrator                           │
│      self.orchestrator.call_mcp("discovery-mcp-server", params) │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Orchestrator: Ensure server running, send request               │
│      self.ensure_server("discovery-mcp-server")                 │
│      response = server.run(params)                              │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ MCP Server: Delegate to agent                                   │
│      agent = DiscoveryAgent()                                   │
│      return agent.execute(params)                               │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Agent: Execute business logic                                   │
│      files = scan_directory(repo_path)                          │
│      return create_result(status="success", data={...})         │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Result flows back through layers to CLI                         │
│      CLI displays formatted result                              │
└─────────────────────────────────────────────────────────────────┘
```

### Pipeline Flow (run-all)

```
forgeflow run-all ./repo
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ MissionControl.run_all():                                       │
│                                                                 │
│   for stage in [discover, normalize, docs,                      │
│                 iac, cd, ci, e2e,          # v2.1 stages        │
│                 review, test, scan]:                            │
│       result = self.{stage}(path)                               │
│       if result.status != "success":                            │
│           return failure                                        │
│                                                                 │
│   # Approval gate                                               │
│   if user_approves:                                             │
│       self.bridge(repo)                                         │
│                                                                 │
│   # Post-merge (optional)                                       │
│   if include_post_merge:                                        │
│       self.deploy(path)                                         │
│       self.monitor(path)                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Mode Architecture

### Local Mode

```
┌────────────────────────────────────────┐
│            User Machine                │
│                                        │
│  ┌──────┐  ┌─────────────┐  ┌───────┐  │
│  │ CLI  │→ │ Orchestrator│→ │ MCP   │  │
│  └──────┘  └─────────────┘  │Server │  │
│                             └───┬───┘  │
│                                 ▼      │
│                             ┌───────┐  │
│                             │ Agent │  │
│                             └───────┘  │
└────────────────────────────────────────┘
```

### Hybrid Mode

```
┌────────────────────────────────────────┐    ┌──────────────────┐
│            User Machine                │    │     Cloud        │
│                                        │    │                  │
│  ┌──────┐  ┌─────────────┐             │    │  ┌────────────┐  │
│  │ CLI  │→ │ Orchestrator│─────────────┼────┼→ │ Snyk API   │  │
│  └──────┘  └──────┬──────┘             │    │  └────────────┘  │
│                   │                    │    │                  │
│                   ▼                    │    │  ┌────────────┐  │
│            ┌─────────────┐             │    │  │ GitHub API │  │
│            │ Local MCPs  │             │    │  └────────────┘  │
│            └─────────────┘             │    │                  │
└────────────────────────────────────────┘    └──────────────────┘
```

### Cloud Mode

```
┌──────────────────┐         ┌─────────────────────────────────────┐
│   User Machine   │         │           ForgeFlow Cloud           │
│                  │         │                                     │
│  ┌──────┐        │         │  ┌─────────────┐  ┌─────────────┐   │
│  │ CLI  │────────┼─────────┼→ │ API Gateway │→ │ Orchestrator│   │
│  └──────┘        │   API   │  └─────────────┘  └──────┬──────┘   │
│  (Thin Client)   │         │                         │          │
│                  │         │                         ▼          │
│                  │         │  ┌────────┐  ┌────────┐  ┌───────┐ │
│                  │         │  │MCP 1   │  │MCP 2   │  │MCP N  │ │
│                  │         │  └────────┘  └────────┘  └───────┘ │
└──────────────────┘         └─────────────────────────────────────┘
```

---

## File Structure

```
forgeflow/
├── cli/
│   ├── __init__.py
│   └── forgeflow.py           # CLI entry point
├── core/
│   ├── __init__.py
│   ├── mission_control.py     # Command router
│   ├── orchestrator.py        # MCP lifecycle manager
│   ├── display.py             # Rich console output
│   └── remote_client.py       # Cloud mode HTTP client
├── agents/
│   ├── __init__.py            # Agent exports
│   ├── base_agent.py          # Abstract base class
│   ├── discovery_agent.py
│   ├── normalization_agent.py
│   ├── documentation_agent.py
│   ├── iac_agent.py           # v2.1 — Infrastructure as Code
│   ├── cd_agent.py            # v2.1 — Continuous Deployment
│   ├── ci_agent.py            # v2.1 — Continuous Integration
│   ├── e2e_agent.py           # v2.1 — End-to-end testing
│   ├── code_review_agent.py
│   ├── testing_agent.py
│   ├── security_agent.py
│   ├── generation_agent.py    # Legacy — prefer iac/ci/cd
│   ├── deployment_agent.py
│   ├── monitoring_agent.py
│   └── bridge_agent.py
├── mcp_servers/
│   ├── __init__.py
│   ├── discovery_mcp/
│   │   ├── __init__.py
│   │   └── server.py
│   ├── normalize_mcp/
│   ├── diagram_generator_mcp/
│   ├── iac_mcp/               # v2.1
│   ├── cd_mcp/                # v2.1
│   ├── ci_mcp/                # v2.1
│   ├── e2e_mcp/               # v2.1
│   ├── git_mcp/
│   ├── cicd_mcp/
│   ├── security_mcp/
│   ├── deployment_mcp/
│   ├── cloud_mcp/
│   ├── observability_mcp/
│   └── github_mcp/
├── config/
│   └── forgeflow-config.yaml  # Deployment configuration
├── mcp-config.yaml            # MCP server definitions
├── requirements.txt
└── pyproject.toml
```

---

## Design Principles

1. **Separation of Concerns** - Each layer has one responsibility
2. **Single Responsibility** - Agents do one thing well
3. **Lazy Loading** - MCP servers start only when needed
4. **Mode Flexibility** - Same interface, different backends
5. **Testability** - Agents can be tested in isolation
6. **Extensibility** - Easy to add new agents/commands
