"""
SevaForge API — Tools & Integration Layer Endpoints (Layer 4)
Semantic tool discovery, registration, and external API connector management.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sevaforge.tools import ToolRegistry, ToolDefinition, ToolCapability, APIConnector, ConnectorConfig
from sevaforge.tools.api_connector import AuthScheme

router = APIRouter()

# ── Shared instances (lazy-initialized) ──────────────────────────────

_registry: ToolRegistry | None = None
_connector: APIConnector | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_connector() -> APIConnector:
    global _connector
    if _connector is None:
        _connector = APIConnector()
    return _connector


# ══════════════════════════════════════════════════════════════════════
# Tool Registry Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/register")
async def register_tool(request: Request) -> dict:
    """Register a new tool with the semantic registry."""
    body = await request.json()

    capabilities = [
        ToolCapability(
            name=c.get("name", ""),
            description=c.get("description", ""),
            input_schema=c.get("input_schema", {}),
            output_schema=c.get("output_schema", {}),
        )
        for c in body.get("capabilities", [])
    ]

    tool_def = ToolDefinition(
        name=body.get("name", ""),
        description=body.get("description", ""),
        version=body.get("version", "1.0.0"),
        capabilities=capabilities,
        tags=body.get("tags", []),
        category=body.get("category", "general"),
        author=body.get("author", ""),
    )

    registry = get_registry()
    registered = registry.register_tool(tool_def)
    return registered.to_dict()


@router.delete("/{tool_id}")
async def unregister_tool(tool_id: str) -> dict:
    """Unregister a tool from the registry."""
    registry = get_registry()
    if not registry.unregister_tool(tool_id):
        raise HTTPException(404, f"Tool '{tool_id}' not found")
    return {"unregistered": True, "tool_id": tool_id}


@router.get("/")
async def list_tools(
    category: str | None = None,
    tag: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """List all registered tools with optional filters."""
    registry = get_registry()
    tools = registry.list_tools(category=category, tag=tag, active_only=active_only)
    return [t.to_dict() for t in tools]


@router.get("/{tool_id}")
async def get_tool(tool_id: str) -> dict:
    """Get a specific tool by its ID."""
    registry = get_registry()
    tool = registry.get_tool(tool_id)
    if not tool:
        raise HTTPException(404, f"Tool '{tool_id}' not found")
    return tool.to_dict()


@router.post("/search")
async def search_tools(request: Request) -> list[dict]:
    """Perform semantic search over registered tools."""
    body = await request.json()
    query = body.get("query", "")
    top_k = body.get("top_k", 5)

    if not query:
        raise HTTPException(400, "'query' is required")

    registry = get_registry()
    results = registry.search_tools(query, top_k=top_k)
    return [
        {"tool": tool.to_dict(), "similarity_score": round(score, 4)}
        for tool, score in results
    ]


@router.post("/suggest")
async def suggest_tools(request: Request) -> list[dict]:
    """Suggest tools for a task description using semantic + capability matching."""
    body = await request.json()
    task_description = body.get("task_description", "")

    if not task_description:
        raise HTTPException(400, "'task_description' is required")

    registry = get_registry()
    return registry.suggest_tools(task_description, top_k=body.get("top_k", 5))


# ══════════════════════════════════════════════════════════════════════
# API Connector Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/connectors/register")
async def register_connector(request: Request) -> dict:
    """Register an external API connector."""
    body = await request.json()

    config = ConnectorConfig(
        name=body.get("name", ""),
        base_url=body.get("base_url", ""),
        auth_scheme=AuthScheme(body.get("auth_scheme", "none")),
        auth_config=body.get("auth_config", {}),
        default_headers=body.get("default_headers", {}),
        timeout_seconds=body.get("timeout_seconds", 30),
        retry_max=body.get("retry_max", 3),
        retry_backoff_factor=body.get("retry_backoff_factor", 0.5),
        rate_limit_rpm=body.get("rate_limit_rpm", 60),
    )

    connector = get_connector()
    registered = connector.register_connector(config)
    return registered.to_dict()


@router.get("/connectors/")
async def list_connectors(active_only: bool = True) -> list[dict]:
    """List all registered API connectors."""
    connector = get_connector()
    return [c.to_dict() for c in connector.list_connectors(active_only=active_only)]


@router.post("/connectors/{connector_id}/call")
async def call_connector(connector_id: str, request: Request) -> dict:
    """Call an external API through a registered connector."""
    body = await request.json()
    method = body.get("method", "GET")
    path = body.get("path", "")
    params = body.get("params")
    req_body = body.get("body")

    connector = get_connector()
    try:
        response = connector.call(
            connector_id=connector_id,
            method=method,
            path=path,
            params=params,
            body=req_body,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))

    return response.to_dict()


@router.get("/connectors/stats")
async def connector_stats() -> dict:
    """Return connector-level statistics."""
    return get_connector().stats()
