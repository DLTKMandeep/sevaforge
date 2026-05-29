"""
SevaForge Pydantic Models
All request/response schemas for the REST API and internal pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSEEventType(str, Enum):
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"
    RESULT = "result"
    ERROR = "error"
    DONE = "done"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ── Health ─────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    environment: str
    uptime_seconds: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Agent ──────────────────────────────────────────────────────────────


class AgentInfo(BaseModel):
    """Metadata for a registered agent."""

    agent_id: str
    name: str
    description: str
    status: AgentStatus = AgentStatus.IDLE
    capabilities: list[str] = []
    default_model: str = "claude-sonnet-4-20250514"
    version: str = "1.0.0"


# ── Execution Request / Response ───────────────────────────────────────


class AgentExecuteRequest(BaseModel):
    """Request body for POST /agents/{agent_id}/execute."""

    input: str = Field(..., min_length=1, max_length=10000, description="The user query or instruction")
    params: dict[str, Any] = Field(default_factory=dict, description="Agent-specific parameters")
    model: Optional[str] = Field(None, description="Override default model for this request")
    stream: bool = Field(False, description="Whether to return SSE stream")
    cache_bypass: bool = Field(False, description="Skip semantic cache lookup")


class SourceReference(BaseModel):
    """A source cited in the response."""

    title: str
    url: Optional[str] = None
    relevance_score: float = 0.0


class AgentExecuteResponse(BaseModel):
    """Response body for a completed agent execution."""

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED
    result: Any = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    trace_id: str = Field(default_factory=lambda: f"sf-{uuid.uuid4().hex[:12]}")
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    sources: list[SourceReference] = []
    cached: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Execution Record (persisted) ──────────────────────────────────────


class ExecutionRecord(BaseModel):
    """Full execution record for storage and audit."""

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    user_id: str = "anonymous"
    tenant_id: str = "default"
    status: ExecutionStatus = ExecutionStatus.PENDING
    request: AgentExecuteRequest
    response: Optional[AgentExecuteResponse] = None
    trace_id: str = Field(default_factory=lambda: f"sf-{uuid.uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── SSE Events ─────────────────────────────────────────────────────────


class SSEEvent(BaseModel):
    """A single Server-Sent Event in the streaming response."""

    event: SSEEventType
    data: Any
    trace_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── AI Gateway Models ─────────────────────────────────────────────────


class CacheStats(BaseModel):
    """Response for GET /cache/stats."""

    enabled: bool = True
    total_entries: int = 0
    exact_hits: int = 0
    semantic_hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    estimated_savings_usd: float = 0.0


class PromptMessage(BaseModel):
    """A single message in the chat completion format."""

    role: str  # system, user, assistant
    content: str


class AssembledPrompt(BaseModel):
    """Output of the prompt assembly engine."""

    messages: list[PromptMessage]
    template_id: str
    template_version: str
    variables: dict[str, Any] = {}
    estimated_tokens: int = 0


# ── Example Agent Output Schemas (for Schema Gate) ────────────────────


class Finding(BaseModel):
    """A single finding from a code review or security scan."""

    severity: Severity
    location: str = Field(..., description="File path and line number")
    title: str
    description: str
    suggestion: str = ""


class CodeReviewOutput(BaseModel):
    """Validated output schema for the code-review agent."""

    summary: str
    findings: list[Finding] = []
    overall_risk: Severity = Severity.LOW
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# ── Error ──────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error: str
    detail: str = ""
    trace_id: str = ""
    status_code: int = 500
