"""
SevaForge MCP (Model Context Protocol) Servers

JSON-RPC 2.0 compliant MCP server framework with automatic tool
registration, auth propagation, and health monitoring.

Available MCP servers:
  - GitHubMCPServer:        Repository, PR, issue, and code search operations
  - DeploymentMCPServer:    Deploy workflows, rollbacks, status monitoring
  - SecurityMCPServer:      Vulnerability scanning, secrets audit, compliance
  - ObservabilityMCPServer: Metrics, logs, traces, and alerting
"""

from .base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter, MCPRequest, MCPResponse
from .github_mcp import GitHubMCPServer
from .deployment_mcp import DeploymentMCPServer
from .security_mcp import SecurityMCPServer
from .observability_mcp import ObservabilityMCPServer

__all__ = [
    # Base
    "BaseMCPServer",
    "MCPTool",
    "MCPToolParameter",
    "MCPRequest",
    "MCPResponse",
    # Servers
    "GitHubMCPServer",
    "DeploymentMCPServer",
    "SecurityMCPServer",
    "ObservabilityMCPServer",
]
