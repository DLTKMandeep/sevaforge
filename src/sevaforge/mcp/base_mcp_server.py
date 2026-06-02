"""
SevaForge Base MCP Server — JSON-RPC 2.0 Framework

Provides the foundation for all MCP (Model Context Protocol) servers:
  - JSON-RPC 2.0 compliant request/response handling
  - Automatic tool registration with the SevaForge tool registry
  - Auth context propagation from JWT tokens
  - Health monitoring and readiness checks
  - Request logging and metrics

Usage::

    class MyMCPServer(BaseMCPServer):
        def __init__(self):
            super().__init__(
                server_id="my-server",
                name="My MCP Server",
                description="Does something useful",
            )

        def _register_tools(self) -> list[MCPTool]:
            return [
                MCPTool(
                    name="my_tool",
                    description="Does the thing",
                    parameters=[
                        MCPToolParameter(name="input", type="string", required=True),
                    ],
                    handler=self._handle_my_tool,
                ),
            ]

        async def _handle_my_tool(self, params: dict) -> dict:
            return {"result": "done"}
"""

from __future__ import annotations

import abc
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────


class MCPServerState(str, Enum):
    """MCP server lifecycle states."""
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class MCPToolParameter:
    """A parameter definition for an MCP tool."""
    name: str
    type: str                       # "string" | "integer" | "number" | "boolean" | "object" | "array"
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[str] = field(default_factory=list)


@dataclass
class MCPTool:
    """
    An MCP tool — a callable operation exposed by the server.

    The handler is an async function: ``async def(params: dict) -> dict``.
    """
    name: str
    description: str
    parameters: list[MCPToolParameter] = field(default_factory=list)
    handler: Optional[Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = None
    category: str = ""
    tags: list[str] = field(default_factory=list)

    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema format for MCP tool listing."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class MCPRequest:
    """JSON-RPC 2.0 request."""
    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    jsonrpc: str = "2.0"

    # Auth context (propagated from the API layer)
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None


@dataclass
class MCPResponse:
    """JSON-RPC 2.0 response."""
    id: str = ""
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d

    @property
    def is_error(self) -> bool:
        return self.error is not None


# ── JSON-RPC Error Codes ─────────────────────────────────────────────

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ── Base MCP Server ──────────────────────────────────────────────────


class BaseMCPServer(abc.ABC):
    """
    Abstract base for all SevaForge MCP servers.

    Subclasses implement ``_register_tools()`` to define their tool set.
    The base class handles:
    - JSON-RPC dispatch
    - Tool schema generation
    - Auth context propagation
    - Request metrics
    - Health checking
    """

    def __init__(
        self,
        server_id: str,
        name: str,
        description: str,
        version: str = "1.0.0",
    ):
        self._server_id = server_id
        self._name = name
        self._description = description
        self._version = version
        self._state = MCPServerState.INITIALIZING
        self._created_at = datetime.utcnow()

        # Register tools
        self._tools: dict[str, MCPTool] = {}
        for tool in self._register_tools():
            self._tools[tool.name] = tool

        # Stats
        self._stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_latency_ms": 0.0,
        }
        # Per-tool call counts
        self._tool_stats: dict[str, int] = {t: 0 for t in self._tools}

        self._state = MCPServerState.READY
        logger.info(
            "MCP server '%s' ready: %d tools registered",
            self._server_id, len(self._tools),
        )

    # ── Properties ───────────────────────────────────────────────────

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> MCPServerState:
        return self._state

    @property
    def tools(self) -> dict[str, MCPTool]:
        return self._tools

    # ── Abstract Method ──────────────────────────────────────────────

    @abc.abstractmethod
    def _register_tools(self) -> list[MCPTool]:
        """
        Register all tools this server provides.

        Returns a list of MCPTool definitions with handlers.
        """
        ...

    # ── JSON-RPC Dispatch ────────────────────────────────────────────

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """
        Handle a JSON-RPC 2.0 request.

        Built-in methods:
          - ``tools/list``     — List available tools with schemas
          - ``tools/call``     — Call a specific tool by name
          - ``server/info``    — Server metadata
          - ``server/health``  — Health check

        Custom tool calls go through ``tools/call`` with the tool
        name in ``params.name``.
        """
        start_time = time.time()
        self._stats["total_requests"] += 1
        self._state = MCPServerState.RUNNING

        try:
            # Route built-in methods
            if request.method == "tools/list":
                result = self._handle_tools_list()
            elif request.method == "tools/call":
                result = await self._handle_tools_call(request)
            elif request.method == "server/info":
                result = self._handle_server_info()
            elif request.method == "server/health":
                result = self._handle_health()
            else:
                return MCPResponse(
                    id=request.id,
                    error={"code": METHOD_NOT_FOUND, "message": f"Method '{request.method}' not found"},
                )

            elapsed_ms = (time.time() - start_time) * 1000
            self._stats["successful_requests"] += 1
            self._stats["total_latency_ms"] += elapsed_ms

            return MCPResponse(id=request.id, result=result)

        except Exception as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            self._stats["failed_requests"] += 1
            self._stats["total_latency_ms"] += elapsed_ms
            logger.error("MCP server '%s' error: %s", self._server_id, exc, exc_info=True)

            return MCPResponse(
                id=request.id,
                error={"code": INTERNAL_ERROR, "message": str(exc)},
            )

        finally:
            self._state = MCPServerState.READY

    # ── Built-in Handlers ────────────────────────────────────────────

    def _handle_tools_list(self) -> dict[str, Any]:
        """List all available tools with their JSON schemas."""
        return {
            "tools": [tool.to_schema() for tool in self._tools.values()],
        }

    async def _handle_tools_call(self, request: MCPRequest) -> dict[str, Any]:
        """Dispatch a tool call to its handler."""
        tool_name = request.params.get("name", "")
        tool_args = request.params.get("arguments", {})

        if tool_name not in self._tools:
            raise ValueError(f"Tool '{tool_name}' not found. Available: {list(self._tools.keys())}")

        tool = self._tools[tool_name]
        if tool.handler is None:
            raise ValueError(f"Tool '{tool_name}' has no handler registered")

        # Validate required parameters
        for param in tool.parameters:
            if param.required and param.name not in tool_args:
                raise ValueError(f"Missing required parameter: {param.name}")

        # Execute handler with auth context
        logger.debug("MCP tool call: %s.%s", self._server_id, tool_name)
        self._tool_stats[tool_name] = self._tool_stats.get(tool_name, 0) + 1

        result = await tool.handler(
            tool_args,
            user_id=request.user_id,
            tenant_id=request.tenant_id,
        )

        return {
            "content": [{"type": "text", "text": str(result)}],
            "data": result,
        }

    def _handle_server_info(self) -> dict[str, Any]:
        """Return server metadata."""
        return {
            "server_id": self._server_id,
            "name": self._name,
            "description": self._description,
            "version": self._version,
            "state": self._state.value,
            "tools_count": len(self._tools),
            "tools": list(self._tools.keys()),
        }

    def _handle_health(self) -> dict[str, Any]:
        """Health check."""
        return {
            "status": "healthy" if self._state != MCPServerState.ERROR else "unhealthy",
            "server_id": self._server_id,
            "uptime_seconds": (datetime.utcnow() - self._created_at).total_seconds(),
        }

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return server statistics."""
        avg_latency = (
            self._stats["total_latency_ms"] / max(1, self._stats["total_requests"])
        )
        return {
            "server_id": self._server_id,
            "name": self._name,
            "state": self._state.value,
            "version": self._version,
            "tools_count": len(self._tools),
            "tool_calls": dict(self._tool_stats),
            "avg_latency_ms": round(avg_latency, 2),
            "uptime_seconds": (datetime.utcnow() - self._created_at).total_seconds(),
            **self._stats,
        }

    def info(self) -> dict[str, Any]:
        """Return server info for API responses."""
        return {
            "server_id": self._server_id,
            "name": self._name,
            "description": self._description,
            "version": self._version,
            "state": self._state.value,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "parameters": [
                        {"name": p.name, "type": p.type, "required": p.required}
                        for p in t.parameters
                    ],
                }
                for t in self._tools.values()
            ],
        }
