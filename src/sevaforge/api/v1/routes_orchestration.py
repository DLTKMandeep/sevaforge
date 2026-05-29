"""
SevaForge API — Orchestration Layer Endpoints (Layer 3)
A2A messaging, workflow execution, and context memory management.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.orchestration.a2a import A2AProtocol, MessagePriority, MessageType
from sevaforge.orchestration.context import ContextMemory
from sevaforge.orchestration.workflow import (
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowEngine,
    WorkflowNode,
    EdgeCondition,
)

router = APIRouter()

# ── Shared instances (lazy-initialized) ──────────────────────────────

_a2a: A2AProtocol | None = None
_workflow_engine: WorkflowEngine | None = None
_context_memory: ContextMemory | None = None


def get_a2a() -> A2AProtocol:
    global _a2a
    if _a2a is None:
        _a2a = A2AProtocol()
    return _a2a


def get_workflow_engine() -> WorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
        # Register a default mock executor
        _workflow_engine.set_default_executor(
            lambda node, ctx: {"agent": node.agent_id, "status": "completed", "params": node.params}
        )
    return _workflow_engine


def get_context_memory() -> ContextMemory:
    global _context_memory
    if _context_memory is None:
        _context_memory = ContextMemory()
    return _context_memory


# ── Request Models ───────────────────────────────────────────────────


class AgentRegistration(BaseModel):
    agent_id: str
    name: str
    capabilities: list[str] = []


class SendMessageRequest(BaseModel):
    source: str
    target: str
    payload: dict[str, Any] = {}
    message_type: str = "event"
    priority: str = "normal"
    topic: str = ""


class PublishRequest(BaseModel):
    source: str
    topic: str
    payload: dict[str, Any] = {}


class BroadcastRequest(BaseModel):
    source: str
    payload: dict[str, Any] = {}


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]] = []


class CreateSessionRequest(BaseModel):
    user_id: str = "anonymous"
    tenant_id: str = "default"
    metadata: dict[str, Any] = {}
    tags: list[str] = []


class StoreStateRequest(BaseModel):
    key: str
    value: Any


class AddTurnRequest(BaseModel):
    role: str = "user"
    content: str
    agent_id: str = ""
    metadata: dict[str, Any] = {}


# ══════════════════════════════════════════════════════════════════════
# A2A Protocol Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/a2a/agents")
async def register_a2a_agent(req: AgentRegistration) -> dict:
    """Register an agent on the A2A bus."""
    a2a = get_a2a()
    endpoint = a2a.register_agent(req.agent_id, req.name, req.capabilities)
    return {
        "registered": True,
        "agent_id": endpoint.agent_id,
        "name": endpoint.name,
    }


@router.get("/a2a/agents")
async def list_a2a_agents() -> list[dict]:
    """List all agents registered on the A2A bus."""
    a2a = get_a2a()
    return [
        {
            "agent_id": ep.agent_id,
            "name": ep.name,
            "capabilities": ep.capabilities,
            "subscriptions": ep.subscriptions,
            "is_active": ep.is_active,
        }
        for ep in a2a.list_agents()
    ]


@router.delete("/a2a/agents/{agent_id}")
async def unregister_a2a_agent(agent_id: str) -> dict:
    a2a = get_a2a()
    removed = a2a.unregister_agent(agent_id)
    if not removed:
        raise HTTPException(404, f"Agent '{agent_id}' not found on A2A bus")
    return {"unregistered": True, "agent_id": agent_id}


@router.post("/a2a/send")
async def send_message(req: SendMessageRequest) -> dict:
    """Send a point-to-point message between agents."""
    a2a = get_a2a()
    msg = a2a.send(
        source=req.source,
        target=req.target,
        payload=req.payload,
        message_type=MessageType(req.message_type),
        priority=MessagePriority(req.priority),
        topic=req.topic,
    )
    return {
        "message_id": msg.message_id,
        "status": msg.status.value,
        "correlation_id": msg.correlation_id,
    }


@router.post("/a2a/publish")
async def publish_message(req: PublishRequest) -> dict:
    """Publish a message to all topic subscribers."""
    a2a = get_a2a()
    messages = a2a.publish(req.source, req.topic, req.payload)
    return {"published": True, "recipients": len(messages), "topic": req.topic}


@router.post("/a2a/broadcast")
async def broadcast_message(req: BroadcastRequest) -> dict:
    """Broadcast a message to all registered agents."""
    a2a = get_a2a()
    messages = a2a.broadcast(req.source, req.payload)
    return {"broadcast": True, "recipients": len(messages)}


@router.get("/a2a/inbox/{agent_id}")
async def get_inbox(agent_id: str, limit: int = 50) -> dict:
    """Retrieve pending messages for an agent."""
    a2a = get_a2a()
    messages = a2a.receive(agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "messages": [
            {
                "message_id": m.message_id,
                "source": m.source_agent,
                "type": m.message_type.value,
                "topic": m.topic,
                "payload": m.payload,
                "status": m.status.value,
            }
            for m in messages
        ],
    }


@router.get("/a2a/stats")
async def a2a_stats() -> dict:
    return get_a2a().stats()


# ══════════════════════════════════════════════════════════════════════
# Workflow Engine Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/workflows")
async def create_workflow(req: CreateWorkflowRequest) -> dict:
    """Create and register a workflow definition."""
    engine = get_workflow_engine()

    definition = WorkflowDefinition(name=req.name, description=req.description)
    for n in req.nodes:
        definition.add_node(WorkflowNode(
            node_id=n["node_id"],
            agent_id=n["agent_id"],
            name=n.get("name", ""),
            params=n.get("params", {}),
            timeout_seconds=n.get("timeout_seconds", 300),
            max_retries=n.get("max_retries", 0),
        ))
    for e in req.edges:
        definition.add_edge(WorkflowEdge(
            source=e["source"],
            target=e["target"],
            condition=EdgeCondition(e.get("condition", "on_success")),
        ))

    try:
        wf_id = engine.register_workflow(definition)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    return {
        "workflow_id": wf_id,
        "name": req.name,
        "nodes": len(req.nodes),
        "edges": len(req.edges),
    }


@router.get("/workflows")
async def list_workflows() -> list[dict]:
    engine = get_workflow_engine()
    return [wf.to_dict() for wf in engine.list_workflows()]


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict:
    engine = get_workflow_engine()
    wf = engine.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")
    return wf.to_dict()


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str) -> dict:
    engine = get_workflow_engine()
    if not engine.delete_workflow(workflow_id):
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")
    return {"deleted": True, "workflow_id": workflow_id}


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str) -> dict:
    """Execute a workflow synchronously."""
    engine = get_workflow_engine()
    try:
        run = engine.execute_sync(workflow_id)
    except KeyError:
        raise HTTPException(404, f"Workflow '{workflow_id}' not found")
    return run.to_dict()


@router.get("/workflows/runs/{run_id}")
async def get_workflow_run(run_id: str) -> dict:
    engine = get_workflow_engine()
    run = engine.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return run.to_dict()


@router.get("/workflows/engine/stats")
async def workflow_stats() -> dict:
    return get_workflow_engine().stats()


# ══════════════════════════════════════════════════════════════════════
# Context Memory Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/context/sessions")
async def create_session(req: CreateSessionRequest) -> dict:
    """Create a new context session."""
    memory = get_context_memory()
    session = memory.create_session(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        metadata=req.metadata,
        tags=req.tags,
    )
    return session.to_dict()


@router.get("/context/sessions")
async def list_sessions(
    user_id: str | None = None,
    tenant_id: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> list[dict]:
    memory = get_context_memory()
    sessions = memory.list_sessions(user_id=user_id, tenant_id=tenant_id, tag=tag, limit=limit)
    return [s.to_dict() for s in sessions]


@router.get("/context/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    memory = get_context_memory()
    session = memory.get_session(session_id)
    if not session:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return session.to_dict()


@router.delete("/context/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    memory = get_context_memory()
    if not memory.delete_session(session_id):
        raise HTTPException(404, f"Session '{session_id}' not found")
    return {"deleted": True, "session_id": session_id}


@router.post("/context/sessions/{session_id}/state")
async def store_state(session_id: str, req: StoreStateRequest) -> dict:
    """Store a key-value pair in the session's shared state."""
    memory = get_context_memory()
    if not memory.store(session_id, req.key, req.value):
        raise HTTPException(404, f"Session '{session_id}' not found")
    return {"stored": True, "key": req.key}


@router.get("/context/sessions/{session_id}/state")
async def get_state(session_id: str) -> dict:
    memory = get_context_memory()
    return memory.get_state(session_id)


@router.post("/context/sessions/{session_id}/turns")
async def add_turn(session_id: str, req: AddTurnRequest) -> dict:
    """Add a conversation turn to the session history."""
    memory = get_context_memory()
    turn = memory.add_turn(
        session_id=session_id,
        role=req.role,
        content=req.content,
        agent_id=req.agent_id,
        metadata=req.metadata,
    )
    if not turn:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return turn.to_dict()


@router.get("/context/sessions/{session_id}/history")
async def get_history(session_id: str, limit: int | None = None) -> list[dict]:
    memory = get_context_memory()
    turns = memory.get_history(session_id, limit=limit)
    return [t.to_dict() for t in turns]


@router.get("/context/sessions/{session_id}/window")
async def get_context_window(session_id: str, max_turns: int = 20) -> dict:
    """Get a context window suitable for LLM input."""
    memory = get_context_memory()
    return memory.get_context_window(session_id, max_turns=max_turns)


@router.post("/context/sessions/{session_id}/fork")
async def fork_session(session_id: str) -> dict:
    """Fork a session for branching workflows."""
    memory = get_context_memory()
    forked = memory.fork_session(session_id)
    if not forked:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return forked.to_dict()


@router.get("/context/stats")
async def context_stats() -> dict:
    return get_context_memory().stats()
