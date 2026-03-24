"""
ForgeFlow Base Agent
All agents inherit from this base class.

Architecture: Orchestrator → MCP Server → Agent → Results
- Orchestrator dispatches to MCP server
- MCP server delegates to Agent
- Agent executes business logic
- Results flow back up the chain
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s] %(levelname)s: %(message)s'
)


class BaseAgent(ABC):
    """
    Base class for all ForgeFlow agents.
    
    Agents contain the actual business logic that was previously in MCP servers.
    MCP servers are now thin protocol/communication layers that delegate to agents.
    """
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(name)
        self.state: Dict[str, Any] = {}
        self.results: List[Dict[str, Any]] = []
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's main task.
        
        Args:
            params: Task parameters (path, options, etc.)
            
        Returns:
            Result dictionary with status, summary, data, findings
        """
        pass
    
    def log(self, message: str, level: str = "info"):
        """Log agent activity."""
        log_func = getattr(self.logger, level, self.logger.info)
        log_func(message)
    
    def save_result(self, result: Dict[str, Any]):
        """Save result to agent state."""
        self.results.append({
            "timestamp": datetime.utcnow().isoformat(),
            "result": result
        })
    
    def get_results(self) -> List[Dict[str, Any]]:
        """Get all agent results."""
        return self.results
    
    def create_result(
        self,
        status: str,
        summary: str,
        data: Dict[str, Any] = None,
        findings: List[str] = None,
        actions: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a standardized result dictionary.

        Args:
            status: "success", "warning", or "error"
            summary: Brief summary of the result
            data: Detailed result data
            findings: List of finding strings
            actions: List of action dicts (used by IAC, CD, CI, E2E agents)

        Returns:
            Standardized result dictionary
        """
        result = {
            "status": status,
            "summary": summary,
            "data": data or {},
            "findings": findings or [],
            "agent": self.name,
            "timestamp": datetime.utcnow().isoformat()
        }
        if actions is not None:
            result["actions"] = actions
        return result
    
    def _safe_write(self, path, content: str, overwrite: bool = False) -> Dict[str, Any]:
        """Write a file with greenfield/brownfield mode awareness.

        Greenfield (overwrite=True): Always write, replacing any existing file.
        Brownfield (overwrite=False, default): Skip files that already exist —
        only generate files that are missing, preserving hand-crafted configs.

        Returns an action dict compatible with the agent actions list format:
            {"action": "created" | "updated" | "exists", "file": <filename>}
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and not overwrite:
            return {"action": "exists", "file": p.name}
        existed = p.exists()
        p.write_text(content)
        return {"action": "updated" if existed else "created", "file": p.name}

    def __repr__(self):
        return f"<Agent: {self.name}>"
