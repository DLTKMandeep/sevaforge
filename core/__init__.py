"""
ForgeFlow Core Module

Exports:
    - MCPOrchestrator: Manages MCP server lifecycle and task dispatching
    - MissionControl: CLI backend that delegates to orchestrator
    - Display utilities: Rich-based display functions
    - Response models: Standardized response structures
"""

from .orchestrator import MCPOrchestrator
from .mission_control import MissionControl
from .models import (
    Status,
    AgentResult,
    MCPResponse,
    OrchestratorResult,
    MissionResult,
    wrap_agent_result,
    wrap_mcp_response,
    create_error_response
)

__all__ = [
    'MCPOrchestrator',
    'MissionControl',
    'Status',
    'AgentResult',
    'MCPResponse',
    'OrchestratorResult',
    'MissionResult',
    'wrap_agent_result',
    'wrap_mcp_response',
    'create_error_response'
]
