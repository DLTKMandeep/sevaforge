"""
ForgeFlow Agents Package

Architecture: Orchestrator → MCP Server → Agent → Results

All agents contain the actual business logic. MCP servers are thin protocol
layers that delegate to these agents.

Command → Agent → MCP Server mapping:
| Command   | Agent                | MCP Server              | Description                    |
|-----------|---------------------|-------------------------|--------------------------------|
| init      | ScaffoldingAgent    | N/A (direct)            | Greenfield project scaffolding |
| discover  | DiscoveryAgent      | discovery_mcp           | Scan repository structure      |
| normalize | NormalizationAgent  | normalize_mcp           | Standardize repository         |
| scan      | SecurityAgent       | security_mcp            | Security vulnerability scan    |
| generate  | GenerationAgent     | deployment_mcp          | Generate deployment artifacts  |
| deploy    | DeploymentAgent     | cloud_mcp               | Deploy to cloud infrastructure |
| test      | TestingAgent        | cicd_mcp                | Run tests via CI/CD            |
| monitor   | MonitoringAgent     | observability_mcp       | Setup monitoring configs       |
| docs      | DocumentationAgent  | diagram_generator_mcp   | Generate documentation         |
| review    | CodeReviewAgent     | git_mcp                 | Code quality analysis          |
| bridge    | BridgeAgent         | github_mcp              | GitHub integration             |

Greenfield Support (New in v2.0):
- ScaffoldingAgent: Creates new projects from wizard configuration
- GenerationAgent: Now includes ArgoCD/Kustomize generation
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
from .scaffolding_agent import ScaffoldingAgent

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
    'ScaffoldingAgent',
]
