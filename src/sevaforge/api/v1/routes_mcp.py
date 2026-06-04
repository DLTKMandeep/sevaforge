"""
SevaForge API v1 — MCP Server Routes (Week 5)

Endpoints for MCP server management, tool listing, and tool invocation.

Endpoints:
  GET  /mcp/servers                        List all MCP servers
  GET  /mcp/servers/{server_id}            Get MCP server info
  GET  /mcp/servers/{server_id}/tools      List tools for a server
  POST /mcp/servers/{server_id}/call       Call a tool on a server
  GET  /mcp/servers/{server_id}/health     Health check for a server
  GET  /mcp/servers/{server_id}/stats      Get server statistics
  GET  /mcp/tools                          List all tools across all servers
  GET  /mcp/stats                          MCP subsystem statistics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.mcp import (
    GitHubMCPServer,
    DeploymentMCPServer,
    SecurityMCPServer,
    ObservabilityMCPServer,
    GitMCPServer,
    CIMCPServer,
    CDMCPServer,
    CICDMCPServer,
    CloudMCPServer,
    DiscoveryMCPServer,
    E2EMCPServer,
    IACMCPServer,
    NormalizeMCPServer,
    DiagramGeneratorMCPServer,
    EmbeddingMCPServer,
    VectorStoreMCPServer,
    VertexAIMCPServer,
)
from sevaforge.mcp.base_mcp_server import BaseMCPServer, MCPRequest

logger = logging.getLogger(__name__)
router = APIRouter()

# ── MCP Server Registry ─────────────────────────────────────────────

_mcp_registry: dict[str, BaseMCPServer] = {}


def _ensure_mcp_registry() -> dict[str, BaseMCPServer]:
    """Lazy-initialize the MCP server registry."""
    if not _mcp_registry:
        servers = [
            # Week 5 core servers
            GitHubMCPServer(),
            DeploymentMCPServer(),
            SecurityMCPServer(),
            ObservabilityMCPServer(),
            # Ported servers
            GitMCPServer(),
            CIMCPServer(),
            CDMCPServer(),
            CICDMCPServer(),
            CloudMCPServer(),
            DiscoveryMCPServer(),
            E2EMCPServer(),
            IACMCPServer(),
            NormalizeMCPServer(),
            DiagramGeneratorMCPServer(),
            EmbeddingMCPServer(),
            VectorStoreMCPServer(),
            VertexAIMCPServer(),
        ]
        for server in servers:
            _mcp_registry[server.server_id] = server
        logger.info("MCP registry initialized: %d servers", len(_mcp_registry))
    return _mcp_registry


def _get_server(server_id: str) -> BaseMCPServer:
    registry = _ensure_mcp_registry()
    server = registry.get(server_id)
    if server is None:
        raise HTTPException(
            status_code=404,
            detail=f"MCP server '{server_id}' not found. Available: {list(registry.keys())}",
        )
    return server


# ── Request Models ───────────────────────────────────────────────────


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    user_id: str = Field("anonymous", description="User ID for auth context propagation")
    tenant_id: str = Field("default", description="Tenant ID for auth context")


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/mcp/servers")
async def list_servers() -> dict[str, Any]:
    """List all registered MCP servers."""
    registry = _ensure_mcp_registry()
    return {
        "total_servers": len(registry),
        "servers": [server.info() for server in registry.values()],
    }


@router.get("/mcp/servers/{server_id}")
async def get_server_info(server_id: str) -> dict[str, Any]:
    """Get detailed information about an MCP server."""
    server = _get_server(server_id)
    return server.info()


@router.get("/mcp/servers/{server_id}/tools")
async def list_server_tools(server_id: str) -> dict[str, Any]:
    """List all tools provided by an MCP server."""
    server = _get_server(server_id)
    return {
        "server_id": server_id,
        "tools": [tool.to_schema() for tool in server.tools.values()],
    }


@router.post("/mcp/servers/{server_id}/call")
async def call_tool(server_id: str, body: MCPToolCallRequest) -> dict[str, Any]:
    """
    Call a tool on an MCP server.

    Uses JSON-RPC 2.0 protocol internally.
    Auth context (user_id, tenant_id) is propagated to the tool handler.
    """
    server = _get_server(server_id)

    # Verify tool exists
    if body.tool_name not in server.tools:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{body.tool_name}' not found on server '{server_id}'. "
                   f"Available: {list(server.tools.keys())}",
        )

    # Build JSON-RPC request
    request = MCPRequest(
        method="tools/call",
        params={
            "name": body.tool_name,
            "arguments": body.arguments,
        },
        user_id=body.user_id,
        tenant_id=body.tenant_id,
    )

    response = await server.handle_request(request)

    if response.is_error:
        raise HTTPException(
            status_code=500,
            detail=response.error.get("message", "Tool call failed") if response.error else "Unknown error",
        )

    return {
        "server_id": server_id,
        "tool_name": body.tool_name,
        "result": response.result,
    }


@router.get("/mcp/servers/{server_id}/health")
async def server_health(server_id: str) -> dict[str, Any]:
    """Health check for an MCP server."""
    server = _get_server(server_id)
    request = MCPRequest(method="server/health")
    response = await server.handle_request(request)
    return response.result or {"status": "unknown"}


@router.get("/mcp/servers/{server_id}/stats")
async def server_stats(server_id: str) -> dict[str, Any]:
    """Get runtime statistics for an MCP server."""
    server = _get_server(server_id)
    return server.stats()


@router.get("/mcp/tools")
async def list_all_tools() -> dict[str, Any]:
    """List all tools across all MCP servers."""
    registry = _ensure_mcp_registry()
    all_tools = []
    for server in registry.values():
        for tool in server.tools.values():
            all_tools.append({
                "server_id": server.server_id,
                "server_name": server.name,
                **tool.to_schema(),
            })

    return {
        "total_tools": len(all_tools),
        "tools": all_tools,
    }


@router.get("/mcp/stats")
async def mcp_stats() -> dict[str, Any]:
    """Get MCP subsystem statistics."""
    registry = _ensure_mcp_registry()
    total_tools = 0
    total_requests = 0
    server_summaries = []

    for server in registry.values():
        stats = server.stats()
        total_tools += stats["tools_count"]
        total_requests += stats["total_requests"]
        server_summaries.append({
            "server_id": server.server_id,
            "name": server.name,
            "state": stats["state"],
            "tools_count": stats["tools_count"],
            "total_requests": stats["total_requests"],
            "avg_latency_ms": stats["avg_latency_ms"],
        })

    return {
        "total_servers": len(registry),
        "total_tools": total_tools,
        "total_requests": total_requests,
        "servers": server_summaries,
    }
