# ForgeFlow Data Flow Architecture

## Overview

ForgeFlow implements a clean, layered data flow pattern where data flows through the stack and back:

```
REQUEST:  CLI → Mission Control → Orchestrator → MCP Server → Agent
RESPONSE: CLI ← Mission Control ← Orchestrator ← MCP Server ← Agent
```

This design ensures:
- **Separation of concerns**: Each layer has a single responsibility
- **Consistent response format**: All layers use standardized models
- **No direct output**: Only CLI produces console output; all other layers use logging
- **Testability**: Each layer can be tested in isolation

## Response Models

Located in `core/models.py`:

### 1. AgentResult
The innermost result - raw business logic output from an Agent.

```python
@dataclass
class AgentResult:
    status: str        # success, warning, error
    summary: str       # Brief description
    data: Dict         # Detailed result data
    findings: List     # List of findings
    agent: str         # Agent class name
    timestamp: str     # ISO timestamp
```

### 2. MCPResponse
MCP server wraps AgentResult with server metadata.

```python
@dataclass
class MCPResponse:
    status: str        # Inherited from agent
    server: str        # MCP server name
    agent: str         # Agent class name
    result: Dict       # The AgentResult as dict
    timestamp: str     # ISO timestamp
```

### 3. OrchestratorResult
Orchestrator adds execution metadata.

```python
@dataclass
class OrchestratorResult:
    mission: str       # Command name (discover, scan, etc.)
    mode: str          # Deployment mode (local, hybrid, public)
    status: str        # Inherited from MCP
    server: str        # MCP server name
    server_response: Dict  # Full MCP response
    execution_time_ms: float
    timestamp: str
```

### 4. MissionResult
Final result with display hints for CLI.

```python
@dataclass
class MissionResult:
    mission: str
    status: str
    deployment_mode: str
    summary: str
    data: Dict
    findings: List
    server: str
    agent: str
    execution_time_ms: float
    timestamp: str
    report_path: Optional[str]
```

## Data Flow Example

### Request Flow (discover command)

```
1. CLI (forgeflow.py)
   └── Parses: forgeflow discover --path ./myrepo
   └── Creates: params = {"path": "./myrepo"}
   └── Calls: MissionControl.discover(path)

2. MissionControl (mission_control.py)
   └── Receives: path string
   └── Creates: params = {"path": path}
   └── Calls: orchestrator.run_mission("discover", params)

3. Orchestrator (orchestrator.py)
   └── Receives: mission_type="discover", params
   └── Looks up: server_name = "discovery-mcp-server"
   └── Calls: self.dispatch(server_name, params)
   └── Loads: mcp_servers/discovery_mcp/server.py
   └── Calls: module.run(params)

4. MCP Server (discovery_mcp/server.py)
   └── Receives: params dict
   └── Creates: DiscoveryAgent instance
   └── Calls: agent.execute(params)

5. Agent (discovery_agent.py)
   └── Receives: params dict
   └── Executes: business logic (scan files, etc.)
   └── Returns: AgentResult dict
```

### Response Flow

```
5. Agent returns AgentResult:
   {
     "status": "success",
     "summary": "Discovered 50 files",
     "data": {"files": [...], "languages": {...}},
     "findings": ["Found Python", "Found tests"],
     "agent": "DiscoveryAgent"
   }

4. MCP Server wraps in MCPResponse:
   {
     "status": "success",
     "server": "discovery-mcp-server",
     "agent": "DiscoveryAgent",
     "result": <AgentResult above>,
     "timestamp": "2024-01-01T00:00:00"
   }

3. Orchestrator wraps in OrchestratorResult:
   {
     "mission": "discover",
     "mode": "local",
     "deployment_mode": "local",
     "status": "success",
     "server": "discovery-mcp-server",
     "summary": "Discovered 50 files",  # Flattened from result
     "data": {...},                      # Flattened from result
     "findings": [...],                  # Flattened from result
     "execution_time_ms": 150.5,
     "timestamp": "..."
   }

2. MissionControl receives OrchestratorResult:
   └── Saves report to staging/
   └── Calls: display.print_stage_result()
   └── Returns: result dict to CLI

1. CLI receives final result:
   └── Prints formatted output via Rich
   └── Sets exit code based on status
```

## Helper Functions

### wrap_agent_result()
Used by MCP servers to wrap agent results:

```python
from core.models import wrap_agent_result

def run(params: dict) -> dict:
    agent_result = _agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)
```

### wrap_mcp_response()
Used by orchestrator to add metadata:

```python
from core.models import wrap_mcp_response

mcp_response = self.dispatch(server_name, params)
result = wrap_mcp_response(mcp_response, mission_type, mode, execution_time_ms)
```

## Logging vs Printing

| Layer | Console Output | Logging |
|-------|---------------|---------|
| CLI | ✅ Rich display | - |
| Mission Control | ✅ Via display module | - |
| Orchestrator | ❌ | ✅ logger.info/debug |
| MCP Server | ❌ | ✅ logger.info/debug |
| Agent | ❌ | ✅ self.log() |

## Deployment Mode Handling

The data flow is consistent across all deployment modes:

### Local Mode
```
CLI → Mission Control → Orchestrator → [Local MCP] → Agent
```

### Hybrid Mode
```
CLI → Mission Control → Orchestrator → [Local/Remote MCP] → Agent
```

### Public Mode
```
CLI → Mission Control → Orchestrator → [Remote Client] → Remote MCP → Agent
```

The Orchestrator handles mode-specific routing internally, and all responses follow the same format.

## Testing the Flow

```bash
# Test imports and data flow
python3 -c "
from core.models import wrap_agent_result, wrap_mcp_response
from core.orchestrator import MCPOrchestrator
from core.mission_control import MissionControl
print('All imports successful!')
"

# Test a command
python3 cli/forgeflow.py discover --path .
```
