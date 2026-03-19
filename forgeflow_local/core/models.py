"""
ForgeFlow Standardized Response Models

Defines the data structures for consistent responses throughout the pipeline:
    Agent → MCP → Orchestrator → Mission Control → CLI

Response Flow:
    1. AgentResult: Raw result from agent business logic
    2. MCPResponse: MCP server wraps agent result with server metadata
    3. OrchestratorResult: Adds orchestration metadata (mode, timing, mission)
    4. MissionResult: Final result with display formatting hints

All responses use these models for consistency across deployment modes.
"""
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class Status(str, Enum):
    """Standard status values."""
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PENDING = "pending"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """
    Result returned by an Agent after executing its task.
    
    This is the innermost result - contains actual business logic output.
    """
    status: str  # success, warning, error
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    findings: List[Any] = field(default_factory=list)
    agent: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentResult':
        """Create from dictionary."""
        return cls(
            status=data.get("status", "error"),
            summary=data.get("summary", ""),
            data=data.get("data", {}),
            findings=data.get("findings", []),
            agent=data.get("agent", ""),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat())
        )
    
    @classmethod
    def error(cls, message: str, agent: str = "") -> 'AgentResult':
        """Create an error result."""
        return cls(
            status=Status.ERROR.value,
            summary=message,
            agent=agent
        )


@dataclass
class MCPResponse:
    """
    Response from an MCP server after delegating to an Agent.
    
    Wraps AgentResult with MCP server metadata.
    """
    status: str
    server: str  # MCP server name (e.g., "discovery-mcp-server")
    agent: str   # Agent class name (e.g., "DiscoveryAgent")
    result: Dict[str, Any]  # The AgentResult as dict
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_agent_result(
        cls, 
        agent_result: Dict[str, Any], 
        server: str, 
        agent: str
    ) -> 'MCPResponse':
        """Create MCPResponse from agent result dictionary."""
        return cls(
            status=agent_result.get("status", "error"),
            server=server,
            agent=agent,
            result=agent_result
        )
    
    @classmethod
    def error(cls, message: str, server: str, agent: str = "") -> 'MCPResponse':
        """Create an error response."""
        return cls(
            status=Status.ERROR.value,
            server=server,
            agent=agent,
            result={
                "status": Status.ERROR.value,
                "summary": message,
                "data": {},
                "findings": []
            }
        )


@dataclass
class OrchestratorResult:
    """
    Result from the Orchestrator after dispatching to MCP server.
    
    Adds orchestration metadata (mode, timing, mission type).
    """
    mission: str  # Command name (discover, scan, etc.)
    mode: str     # Deployment mode (local, hybrid, public)
    status: str
    server: str
    server_response: Dict[str, Any]  # The MCPResponse as dict
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Convenience accessors for common fields
    @property
    def summary(self) -> str:
        """Get summary from nested response."""
        result = self.server_response.get("result", {})
        return result.get("summary", self.server_response.get("summary", ""))
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get data from nested response."""
        result = self.server_response.get("result", {})
        return result.get("data", self.server_response.get("data", {}))
    
    @property
    def findings(self) -> List[Any]:
        """Get findings from nested response."""
        result = self.server_response.get("result", {})
        return result.get("findings", self.server_response.get("findings", []))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with flattened structure for display."""
        return {
            "mission": self.mission,
            "mode": self.mode,
            "deployment_mode": self.mode,  # Alias for compatibility
            "status": self.status,
            "server": self.server,
            "summary": self.summary,
            "data": self.data,
            "findings": self.findings,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            # Keep full response for debugging
            "_server_response": self.server_response
        }
    
    @classmethod
    def from_mcp_response(
        cls,
        mcp_response: Dict[str, Any],
        mission: str,
        mode: str,
        execution_time_ms: float = 0.0
    ) -> 'OrchestratorResult':
        """Create OrchestratorResult from MCP response dictionary."""
        return cls(
            mission=mission,
            mode=mode,
            status=mcp_response.get("status", "error"),
            server=mcp_response.get("server", "unknown"),
            server_response=mcp_response,
            execution_time_ms=execution_time_ms
        )
    
    @classmethod
    def error(cls, message: str, mission: str, mode: str, server: str = "unknown") -> 'OrchestratorResult':
        """Create an error result."""
        return cls(
            mission=mission,
            mode=mode,
            status=Status.ERROR.value,
            server=server,
            server_response={
                "status": Status.ERROR.value,
                "result": {
                    "status": Status.ERROR.value,
                    "summary": message,
                    "data": {},
                    "findings": []
                }
            }
        )


@dataclass
class MissionResult:
    """
    Final result from Mission Control, ready for CLI display.
    
    This is the outermost result - contains all metadata plus display hints.
    """
    mission: str
    status: str
    deployment_mode: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)
    findings: List[Any] = field(default_factory=list)
    server: str = ""
    agent: str = ""
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    report_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for CLI consumption."""
        return {
            "mission": self.mission,
            "status": self.status,
            "deployment_mode": self.deployment_mode,
            "summary": self.summary,
            "data": self.data,
            "findings": self.findings,
            "server": self.server,
            "agent": self.agent,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            "report_path": self.report_path
        }
    
    @classmethod
    def from_orchestrator_result(
        cls,
        orch_result: Dict[str, Any],
        report_path: Optional[str] = None
    ) -> 'MissionResult':
        """Create MissionResult from orchestrator result dictionary."""
        return cls(
            mission=orch_result.get("mission", "unknown"),
            status=orch_result.get("status", "error"),
            deployment_mode=orch_result.get("deployment_mode", orch_result.get("mode", "local")),
            summary=orch_result.get("summary", ""),
            data=orch_result.get("data", {}),
            findings=orch_result.get("findings", []),
            server=orch_result.get("server", ""),
            agent=orch_result.get("agent", ""),
            execution_time_ms=orch_result.get("execution_time_ms", 0.0),
            timestamp=orch_result.get("timestamp", datetime.utcnow().isoformat()),
            report_path=report_path
        )


# === Helper Functions ===

def wrap_agent_result(agent_result: Dict[str, Any], server_name: str, agent_name: str) -> Dict[str, Any]:
    """
    Wrap an agent result in MCP response format.
    
    Use this in MCP servers to ensure consistent response structure.
    
    Args:
        agent_result: Raw result from agent.execute()
        server_name: Name of the MCP server
        agent_name: Name of the agent class
    
    Returns:
        MCPResponse as dictionary
    """
    return MCPResponse.from_agent_result(agent_result, server_name, agent_name).to_dict()


def wrap_mcp_response(
    mcp_response: Dict[str, Any], 
    mission: str, 
    mode: str, 
    execution_time_ms: float = 0.0
) -> Dict[str, Any]:
    """
    Wrap an MCP response with orchestrator metadata.
    
    Use this in the orchestrator to ensure consistent response structure.
    
    Args:
        mcp_response: Response from MCP server
        mission: Command name
        mode: Deployment mode
        execution_time_ms: Execution time in milliseconds
    
    Returns:
        OrchestratorResult as flattened dictionary
    """
    return OrchestratorResult.from_mcp_response(
        mcp_response, mission, mode, execution_time_ms
    ).to_dict()


def create_error_response(message: str, mission: str = "unknown", mode: str = "local") -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Use this anywhere in the chain when an error occurs.
    """
    return OrchestratorResult.error(message, mission, mode).to_dict()
