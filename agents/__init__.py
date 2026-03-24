"""
ForgeFlow Agents Package

Architecture: Orchestrator → MCP Server → Agent → Results

All agents contain the actual business logic. MCP servers are thin protocol
layers that delegate to these agents.

Command → Agent → MCP Server mapping (v2.1 Pipeline Order):
| #  | Command   | Agent                | MCP Server              | Description                    |
|----|-----------|---------------------|-------------------------|--------------------------------|
| 1  | discover  | DiscoveryAgent      | discovery_mcp           | Scan repository structure      |
| 2  | normalize | NormalizationAgent  | normalize_mcp           | Standardize repository         |
| 3  | docs      | DocumentationAgent  | diagram_generator_mcp   | Generate documentation         |
| 4  | iac       | IACAgent            | iac_mcp                 | Infrastructure as Code         |
| 5  | cd        | CDAgent             | cd_mcp                  | Continuous Deployment config   |
| 6  | ci        | CIAgent             | ci_mcp                  | CI pipeline config             |
| 7  | e2e       | E2ETestingAgent     | e2e_mcp                 | E2E test scaffolding           |
| 8  | review    | CodeReviewAgent     | git_mcp                 | Code quality analysis          |
| 9  | test      | TestingAgent        | cicd_mcp                | Run tests via CI/CD            |
| 10 | scan      | SecurityAgent       | security_mcp            | Security vulnerability scan    |
| 11 | bridge    | BridgeAgent         | github_mcp              | GitHub integration (pre-merge) |
| 12 | deploy    | DeploymentAgent     | cloud_mcp               | Deploy to cloud infrastructure |
| 13 | monitor   | MonitoringAgent     | observability_mcp       | Setup monitoring configs       |

Standalone commands (not in run-all pipeline):
| -  | generate  | GenerationAgent     | deployment_mcp          | Generate deployment artifacts on demand |
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
from .iac_agent import IACAgent
from .cd_agent import CDAgent
from .ci_agent import CIAgent
from .e2e_agent import E2ETestingAgent

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
    'IACAgent',
    'CDAgent',
    'CIAgent',
    'E2ETestingAgent',
]
