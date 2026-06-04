"""
SevaForge API v1 — Agent Intelligence Routes (Week 5)

Endpoints for agent management, execution, and introspection.
These routes use the new BaseAgent framework with full 9-layer integration.

Endpoints:
  GET  /agents/v2/                         List all registered agents
  GET  /agents/v2/{agent_id}               Get agent info
  GET  /agents/v2/{agent_id}/stats         Get agent statistics
  POST /agents/v2/{agent_id}/execute       Execute an agent
  POST /agents/v2/{agent_id}/capabilities  Get agent capabilities
  GET  /agents/v2/registry/stats           Registry-wide statistics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.agents import (
    AgentExecutionContext,
    CodeReviewAgent,
    DeployOrchestratorAgent,
    DiscoveryAgent,
    DocumentationAgent,
    SecurityAgent,
    SecretsAnalyzerAgent,
    NormalizationAgent,
    ScaffoldingAgent,
    LifecycleAgent,
    BridgeAgent,
    DeploymentRunnerAgent,
    GenerationAgent,
    CIAgent,
    CDAgent,
    TestingAgent,
    MonitoringAgent,
    IACAgent,
    IAMAgent,
    E2ETestingAgent,
    DeployIntentAgent,
    DeployValidatorAgent,
    DiagramAgent,
)
from sevaforge.agents.personas import (
    AppDeployerPersona,
    ClusterBuilderPersona,
    CostGuardianPersona,
    InfraArchitectPersona,
    ObservabilityEngineerPersona,
    SecretsManagerPersona,
    SecurityAuditorPersona,
)
from sevaforge.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Agent Registry ───────────────────────────────────────────────────

_agent_registry: dict[str, BaseAgent] = {}


def _ensure_registry() -> dict[str, BaseAgent]:
    """Lazy-initialize the agent registry."""
    if not _agent_registry:
        agents = [
            # Week 5 core agents
            CodeReviewAgent(),
            SecurityAgent(),
            DocumentationAgent(),
            DeployOrchestratorAgent(),
            DiscoveryAgent(),
            # Ported agents
            SecretsAnalyzerAgent(),
            NormalizationAgent(),
            ScaffoldingAgent(),
            LifecycleAgent(),
            BridgeAgent(),
            DeploymentRunnerAgent(),
            GenerationAgent(),
            CIAgent(),
            CDAgent(),
            TestingAgent(),
            MonitoringAgent(),
            IACAgent(),
            IAMAgent(),
            E2ETestingAgent(),
            DeployIntentAgent(),
            DeployValidatorAgent(),
            DiagramAgent(),
            # Personas
            AppDeployerPersona(),
            ClusterBuilderPersona(),
            CostGuardianPersona(),
            InfraArchitectPersona(),
            ObservabilityEngineerPersona(),
            SecretsManagerPersona(),
            SecurityAuditorPersona(),
        ]
        for agent in agents:
            _agent_registry[agent.agent_id] = agent
        logger.info("Agent registry initialized: %d agents", len(_agent_registry))
    return _agent_registry


def _get_agent(agent_id: str) -> BaseAgent:
    registry = _ensure_registry()
    agent = registry.get(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Available: {list(registry.keys())}",
        )
    return agent


# ── Request / Response Models ────────────────────────────────────────


class AgentExecuteRequestBody(BaseModel):
    input: str = Field(..., min_length=1, max_length=50000, description="Input text for the agent")
    params: dict[str, Any] = Field(default_factory=dict, description="Agent-specific parameters")
    model: str | None = Field(None, description="Override default model")
    session_id: str = Field("", description="Session ID for context memory")
    tenant_id: str = Field("default", description="Tenant identifier")


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/agents/v2/")
async def list_agents() -> dict[str, Any]:
    """List all registered agents with their info."""
    registry = _ensure_registry()
    return {
        "total_agents": len(registry),
        "agents": [agent.info() for agent in registry.values()],
    }


@router.get("/agents/v2/registry/stats")
async def registry_stats() -> dict[str, Any]:
    """Get statistics across all registered agents."""
    registry = _ensure_registry()
    total_executions = 0
    total_cost = 0.0
    agent_stats = []

    for agent in registry.values():
        stats = agent.stats()
        total_executions += stats["total_executions"]
        total_cost += stats["total_cost_usd"]
        agent_stats.append({
            "agent_id": agent.agent_id,
            "executions": stats["total_executions"],
            "success_rate": (
                stats["successful_executions"] / max(1, stats["total_executions"])
            ),
            "cost_usd": stats["total_cost_usd"],
        })

    return {
        "total_agents": len(registry),
        "total_executions": total_executions,
        "total_cost_usd": round(total_cost, 6),
        "agents": agent_stats,
    }


@router.get("/agents/v2/{agent_id}")
async def get_agent_info(agent_id: str) -> dict[str, Any]:
    """Get detailed information about a specific agent."""
    agent = _get_agent(agent_id)
    return agent.info()


@router.get("/agents/v2/{agent_id}/stats")
async def get_agent_stats(agent_id: str) -> dict[str, Any]:
    """Get runtime statistics for a specific agent."""
    agent = _get_agent(agent_id)
    return agent.stats()


@router.post("/agents/v2/{agent_id}/execute")
async def execute_agent(agent_id: str, body: AgentExecuteRequestBody) -> dict[str, Any]:
    """
    Execute an agent with full 9-layer integration.

    The agent runs through:
    1. Input guardrails (L6)
    2. Audit logging (L6)
    3. OTel tracing (L6)
    4. Context restoration (L3)
    5. Agent-specific logic
    6. Output guardrails (L6)
    7. Cost tracking (L9)
    8. Context save (L3)
    """
    agent = _get_agent(agent_id)

    ctx = AgentExecutionContext(
        input=body.input,
        params=body.params,
        model_override=body.model,
        session_id=body.session_id,
        tenant_id=body.tenant_id,
    )

    result = await agent.run(ctx)
    return result.to_dict()


@router.get("/agents/v2/{agent_id}/capabilities")
async def get_agent_capabilities(agent_id: str) -> dict[str, Any]:
    """Get the capabilities advertised by an agent."""
    agent = _get_agent(agent_id)
    return {
        "agent_id": agent.agent_id,
        "capabilities": [
            {
                "name": c.name,
                "description": c.description,
                "input_schema": c.input_schema,
                "output_schema": c.output_schema,
            }
            for c in agent.capabilities
        ],
    }
