"""
SevaForge API — Agent Endpoints
CRUD for agents + execute (sync and streaming).
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from sevaforge.api.app import get_gateway
from sevaforge.models.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentInfo,
    AgentStatus,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── In-Memory Agent Registry (Week 1) ────────────────────────────────
# Will be backed by database in Week 2.

_AGENTS: dict[str, AgentInfo] = {
    "code-review": AgentInfo(
        agent_id="code-review",
        name="Code Review Agent",
        description="Reviews code for quality, security, and best practices.",
        status=AgentStatus.IDLE,
        capabilities=["code-analysis", "security-scan", "best-practices"],
        default_model="claude-sonnet-4-20250514",
    ),
    "doc-writer": AgentInfo(
        agent_id="doc-writer",
        name="Documentation Writer",
        description="Generates technical documentation from code and specs.",
        status=AgentStatus.IDLE,
        capabilities=["doc-generation", "api-docs", "readme"],
        default_model="claude-sonnet-4-20250514",
    ),
    "test-gen": AgentInfo(
        agent_id="test-gen",
        name="Test Generator",
        description="Generates unit and integration tests from source code.",
        status=AgentStatus.IDLE,
        capabilities=["unit-tests", "integration-tests", "test-coverage"],
        default_model="claude-sonnet-4-20250514",
    ),
    "security-scan": AgentInfo(
        agent_id="security-scan",
        name="Security Scanner",
        description="Scans code for vulnerabilities and compliance issues.",
        status=AgentStatus.IDLE,
        capabilities=["vulnerability-scan", "sast", "compliance"],
        default_model="claude-sonnet-4-20250514",
    ),
}


# ── Agent CRUD ────────────────────────────────────────────────────────


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents() -> list[AgentInfo]:
    """List all registered agents."""
    return list(_AGENTS.values())


@router.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str) -> AgentInfo:
    """Get details for a specific agent."""
    if agent_id not in _AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return _AGENTS[agent_id]


@router.post("/agents", response_model=AgentInfo, status_code=201)
async def register_agent(agent: AgentInfo) -> AgentInfo:
    """Register a new agent."""
    if agent.agent_id in _AGENTS:
        raise HTTPException(status_code=409, detail=f"Agent already exists: {agent.agent_id}")
    _AGENTS[agent.agent_id] = agent
    logger.info("Agent registered: %s", agent.agent_id)
    return agent


@router.delete("/agents/{agent_id}", status_code=204)
async def unregister_agent(agent_id: str) -> None:
    """Unregister an agent."""
    if agent_id not in _AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    del _AGENTS[agent_id]
    logger.info("Agent unregistered: %s", agent_id)


# ── Agent Execution ──────────────────────────────────────────────────


@router.post(
    "/agents/{agent_id}/execute",
    response_model=AgentExecuteResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def execute_agent(agent_id: str, request: AgentExecuteRequest) -> AgentExecuteResponse:
    """
    Execute an agent with the given input.

    If `stream=true` in the request body, returns an SSE stream instead.
    """
    if agent_id not in _AGENTS:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    agent = _AGENTS[agent_id]

    # Handle streaming requests
    if request.stream:
        return await _execute_stream(agent_id, request)

    # Synchronous execution
    gateway = get_gateway()
    agent.status = AgentStatus.RUNNING

    try:
        response = await gateway.execute(
            request=request,
            agent_id=agent_id,
            template_id=agent_id,
        )
        agent.status = AgentStatus.IDLE
        return response

    except Exception as e:
        agent.status = AgentStatus.ERROR
        logger.exception("Agent execution failed: %s", agent_id)
        raise HTTPException(status_code=500, detail=str(e))


async def _execute_stream(agent_id: str, request: AgentExecuteRequest) -> StreamingResponse:
    """Return an SSE stream for agent execution."""
    gateway = get_gateway()

    async def event_generator():
        try:
            async for event in gateway.execute_stream(
                request=request,
                agent_id=agent_id,
                template_id=agent_id,
            ):
                data = event.model_dump_json()
                yield f"event: {event.event.value}\ndata: {data}\n\n"
                await asyncio.sleep(0)  # Yield control to event loop
        except Exception as e:
            error_data = json.dumps({"error": str(e), "trace_id": ""})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
