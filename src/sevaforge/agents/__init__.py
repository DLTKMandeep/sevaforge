"""
SevaForge Agents — Intelligent agents with full 9-layer integration.

Every agent inherits from BaseAgent and gets automatic:
  - JWT auth context propagation
  - Input/output guardrails
  - Per-execution cost tracking
  - Circuit breaker protection on LLM calls
  - Immutable audit trail
  - A2A delegation to other agents
  - Context memory across turns
  - Tool registry access
  - OpenTelemetry tracing

Available agents:
  - CodeReviewAgent:          Code quality, bugs, security, style analysis
  - SecurityAgent:            Vulnerability scanning, secrets detection, compliance
  - DocumentationAgent:       API docs, READMEs, docstrings, changelogs
  - DeployOrchestratorAgent:  Deployment planning, validation, rollout, rollback
  - DiscoveryAgent:           Service discovery, dependency mapping, API cataloging
  - SecretsAnalyzerAgent:     Secrets scanning, bootstrap scripts, deployment guides
  - NormalizationAgent:       Repo structure standards, gitignore, editorconfig
  - ScaffoldingAgent:         Greenfield project structure generation
  - LifecycleAgent:           CI/Test/CD workflow lifecycle generation
  - BridgeAgent:              Git-to-GitHub bridge — repos, PRs, branches
  - DeploymentRunnerAgent:    Terraform, Docker, ArgoCD execution runner
  - GenerationAgent:          Orchestrator facade for full-stack generation
  - CIAgent:                  CI pipeline generation (GitHub Actions, GitLab CI)
  - CDAgent:                  CD pipeline generation (ArgoCD, Kustomize, deploy workflows)
  - TestingAgent:             Test framework detection, coverage analysis, test plans
  - MonitoringAgent:          Prometheus configs, alert rules, Grafana dashboards
  - IACAgent:                 Terraform, Dockerfiles, Docker Compose generation
  - IAMAgent:                 IAM policies and service accounts for AWS/GCP/Azure
  - E2ETestingAgent:          Playwright and Cypress E2E test setup generation
  - DeployIntentAgent:        Deployment intent analysis and planning
  - DeployValidatorAgent:     Pre-deploy config validation (K8s, Helm, Terraform)
  - DiagramAgent:             Architecture and flow diagram generation
"""

from .base_agent import BaseAgent, AgentCapability, AgentConfig, AgentExecutionContext, AgentResult
from .code_review_agent import CodeReviewAgent
from .security_agent import SecurityAgent
from .documentation_agent import DocumentationAgent
from .deploy_orchestrator_agent import DeployOrchestratorAgent
from .discovery_agent import DiscoveryAgent
from .secrets_agent import SecretsAnalyzerAgent
from .normalization_agent import NormalizationAgent
from .scaffolding_agent import ScaffoldingAgent
from .lifecycle_agent import LifecycleAgent
from .bridge_agent import BridgeAgent
from .deployment_agent import DeploymentRunnerAgent
from .generation_agent import GenerationAgent
from .ci_agent import CIAgent
from .cd_agent import CDAgent
from .testing_agent import TestingAgent
from .monitoring_agent import MonitoringAgent
from .iac_agent import IACAgent
from .iam_agent import IAMAgent
from .e2e_agent import E2ETestingAgent
from .deploy_intent_agent import DeployIntentAgent
from .deploy_validator_agent import DeployValidatorAgent
from .diagram_agent import DiagramAgent

__all__ = [
    # Base
    "BaseAgent",
    "AgentCapability",
    "AgentConfig",
    "AgentExecutionContext",
    "AgentResult",
    # Agents
    "CodeReviewAgent",
    "SecurityAgent",
    "DocumentationAgent",
    "DeployOrchestratorAgent",
    "DiscoveryAgent",
    "SecretsAnalyzerAgent",
    "NormalizationAgent",
    "ScaffoldingAgent",
    "LifecycleAgent",
    "BridgeAgent",
    "DeploymentRunnerAgent",
    "GenerationAgent",
    "CIAgent",
    "CDAgent",
    "TestingAgent",
    "MonitoringAgent",
    "IACAgent",
    "IAMAgent",
    "E2ETestingAgent",
    "DeployIntentAgent",
    "DeployValidatorAgent",
    "DiagramAgent",
]
