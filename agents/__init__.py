"""
ForgeFlow Agents Package

Architecture: Orchestrator → MCP Server → Agent → Results

All agents contain the actual business logic. MCP servers are thin protocol
layers that delegate to these agents.

Command → Agent → MCP Server mapping:
| Command   | Agent                | MCP Server              |
|-----------|---------------------|-------------------------|
| discover  | DiscoveryAgent      | discovery_mcp           |
| normalize | NormalizationAgent  | normalize_mcp           |
| scan      | SecurityAgent       | security_mcp            |
| generate  | GenerationAgent     | deployment_mcp          |
| deploy    | DeploymentAgent     | cloud_mcp               |
| test      | TestingAgent        | cicd_mcp                |
| monitor   | MonitoringAgent     | observability_mcp       |
| docs      | DocumentationAgent  | diagram_generator_mcp   |
| review    | CodeReviewAgent     | git_mcp                 |
| bridge    | BridgeAgent         | github_mcp              |
"""

from .base_agent import BaseAgent
from .discovery_agent import DiscoveryAgent
from .normalization_agent import NormalizationAgent
from .security_agent import SecurityAgent
from .generation_agent import GenerationAgent
from .deployment_agent import DeploymentAgent
from .testing_agent import TestingAgent
from .monitoring_agent import MonitoringAgent
from .documentation_agent import DocumentationAgent
from .code_review_agent import CodeReviewAgent
from .bridge_agent import BridgeAgent

__all__ = [
    'BaseAgent',
    'DiscoveryAgent',
    'NormalizationAgent',
    'SecurityAgent',
    'GenerationAgent',
    'DeploymentAgent',
    'TestingAgent',
    'MonitoringAgent',
    'DocumentationAgent',
    'CodeReviewAgent',
    'BridgeAgent',
]
