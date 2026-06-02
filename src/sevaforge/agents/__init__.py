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
"""

from .base_agent import BaseAgent, AgentCapability, AgentConfig, AgentExecutionContext, AgentResult
from .code_review_agent import CodeReviewAgent
from .security_agent import SecurityAgent
from .documentation_agent import DocumentationAgent
from .deploy_orchestrator_agent import DeployOrchestratorAgent
from .discovery_agent import DiscoveryAgent

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
]
