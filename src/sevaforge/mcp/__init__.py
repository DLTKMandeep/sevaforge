"""
SevaForge MCP (Model Context Protocol) Servers

JSON-RPC 2.0 compliant MCP server framework with automatic tool
registration, auth propagation, and health monitoring.

Available MCP servers:
  - GitHubMCPServer:            Repository, PR, issue, and code search operations
  - DeploymentMCPServer:        Deploy workflows, rollbacks, status monitoring
  - SecurityMCPServer:          Vulnerability scanning, secrets audit, compliance
  - ObservabilityMCPServer:     Metrics, logs, traces, and alerting
  - GitMCPServer:               Git diff, log, status, branches, blame
  - CIMCPServer:                CI build triggers, status, logs
  - CDMCPServer:                CD deploy triggers, rollback, promotion
  - CICDMCPServer:              Aggregated CI/CD pipeline management
  - CloudMCPServer:             Multi-cloud resource management
  - DiscoveryMCPServer:         Repository scanning and service discovery
  - E2EMCPServer:               E2E test execution and reporting
  - IACMCPServer:               Infrastructure as Code plan/apply
  - NormalizeMCPServer:         Repository structure normalization
  - DiagramGeneratorMCPServer:  Architecture and sequence diagram generation
  - EmbeddingMCPServer:         Text and code embedding operations
  - VectorStoreMCPServer:       Vector database search and ingestion
  - VertexAIMCPServer:          LLM model routing and completion
"""

from .base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter, MCPRequest, MCPResponse
from .github_mcp import GitHubMCPServer
from .deployment_mcp import DeploymentMCPServer
from .security_mcp import SecurityMCPServer
from .observability_mcp import ObservabilityMCPServer
from .git_mcp import GitMCPServer
from .ci_mcp import CIMCPServer
from .cd_mcp import CDMCPServer
from .cicd_mcp import CICDMCPServer
from .cloud_mcp import CloudMCPServer
from .discovery_mcp import DiscoveryMCPServer
from .e2e_mcp import E2EMCPServer
from .iac_mcp import IACMCPServer
from .normalize_mcp import NormalizeMCPServer
from .diagram_generator_mcp import DiagramGeneratorMCPServer
from .embedding_mcp import EmbeddingMCPServer
from .vector_store_mcp import VectorStoreMCPServer
from .vertex_ai_mcp import VertexAIMCPServer

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
    "GitMCPServer",
    "CIMCPServer",
    "CDMCPServer",
    "CICDMCPServer",
    "CloudMCPServer",
    "DiscoveryMCPServer",
    "E2EMCPServer",
    "IACMCPServer",
    "NormalizeMCPServer",
    "DiagramGeneratorMCPServer",
    "EmbeddingMCPServer",
    "VectorStoreMCPServer",
    "VertexAIMCPServer",
]
