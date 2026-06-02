"""
SevaForge BaseAgent — Abstract foundation for all platform agents.

Every agent in the platform extends this class and gets automatic integration
with all 9 architecture layers:

    L1  API Foundation   — Structured request/response schemas
    L2  Auth & Edge      — JWT context propagation, rate-limit awareness
    L3  Orchestration    — A2A delegation, context memory, workflow participation
    L4  Tools            — Tool registry lookup, API connector access
    L5  AI Gateway       — LLM calls via ModelRouter with circuit breaker failover
    L6  Trust & Safety   — Input/output guardrails, OTel tracing, audit trail
    L7  Knowledge        — Hybrid search for RAG context
    L8  Data             — Session persistence, event streaming
    L9  FinOps           — Per-execution cost tracking, budget checks

Usage::

    class CodeReviewAgent(BaseAgent):
        def __init__(self):
            super().__init__(AgentConfig(
                agent_id="code-review",
                name="Code Review Agent",
                description="Reviews code for bugs, style, and security issues",
                capabilities=[
                    AgentCapability(name="static_analysis", description="Analyze code patterns"),
                    AgentCapability(name="security_review", description="Check for vulnerabilities"),
                ],
                system_prompt="You are an expert code reviewer...",
                default_model="claude-sonnet-4-20250514",
            ))

        async def execute(self, ctx: AgentExecutionContext) -> dict:
            # Your agent logic — all layers available via self.*
            llm_result = await self.call_llm(ctx, "Review this code: ...")
            return {"review": llm_result.content}
"""

from __future__ import annotations

import abc
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sevaforge.auth.jwt_handler import TokenPayload
from sevaforge.auth.rate_limiter import CircuitBreaker, CircuitBreakerError
from sevaforge.config import get_settings
from sevaforge.finops.cost_tracker import CostTracker, UsageRecord
from sevaforge.gateway.model_router import ModelRouter, ProviderResponse
from sevaforge.orchestration.a2a import A2AProtocol, AgentMessage, MessageType
from sevaforge.orchestration.context import ContextMemory, ConversationTurn
from sevaforge.tools.tool_registry import ToolRegistry
from sevaforge.trust.audit import AuditTrail, AuditAction
from sevaforge.trust.guardrails import GuardrailsEngine, GuardrailResult
from sevaforge.trust.otel import OTelManager

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────


class AgentState(str, Enum):
    """Agent lifecycle states."""
    IDLE = "idle"
    EXECUTING = "executing"
    WAITING = "waiting"          # Waiting for delegate response
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class AgentCapability:
    """A single capability that an agent advertises."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""
    agent_id: str
    name: str
    description: str
    version: str = "1.0.0"
    capabilities: list[AgentCapability] = field(default_factory=list)
    system_prompt: str = ""
    default_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3
    max_retries: int = 2
    timeout_seconds: float = 120.0
    tags: list[str] = field(default_factory=list)
    guardrails_enabled: bool = True
    cost_tracking_enabled: bool = True
    audit_enabled: bool = True


@dataclass
class AgentExecutionContext:
    """
    Runtime context for a single agent execution.

    Created by the platform for each request and passed to the agent's
    ``execute()`` method.  Contains the user input, auth info, session
    state, and configuration overrides.
    """
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    input: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    user: Optional[TokenPayload] = None
    tenant_id: str = "default"
    session_id: str = ""
    model_override: Optional[str] = None
    trace_id: str = field(default_factory=lambda: f"sf-{uuid.uuid4().hex[:12]}")
    parent_agent_id: Optional[str] = None      # Set when called via A2A delegation
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentResult:
    """Standardised result from an agent execution."""
    execution_id: str
    agent_id: str
    status: str = "succeeded"      # succeeded | failed | partial
    result: Any = None
    confidence: float = 0.0
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    trace_id: str = ""
    guardrail_flags: list[str] = field(default_factory=list)
    delegated_to: list[str] = field(default_factory=list)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "result": self.result,
            "confidence": self.confidence,
            "model_used": self.model_used,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "trace_id": self.trace_id,
            "guardrail_flags": self.guardrail_flags,
            "delegated_to": self.delegated_to,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


# ── BaseAgent ────────────────────────────────────────────────────────


class BaseAgent(abc.ABC):
    """
    Abstract base class for all SevaForge agents.

    Subclasses implement :meth:`execute` with their domain-specific logic.
    All 9-layer integrations (guardrails, cost tracking, audit, etc.) are
    handled automatically by the :meth:`run` orchestration method.

    Layer integration via helper methods:

    - :meth:`call_llm`       — L5 AI Gateway (ModelRouter + circuit breaker)
    - :meth:`guard_input`    — L6 input guardrails
    - :meth:`guard_output`   — L6 output guardrails
    - :meth:`delegate`       — L3 A2A agent delegation
    - :meth:`remember`       — L3 context memory store
    - :meth:`recall`         — L3 context memory retrieve
    - :meth:`search_tools`   — L4 semantic tool discovery
    - :meth:`search_knowledge` — L7 hybrid knowledge search
    - :meth:`track_cost`     — L9 cost tracking
    - :meth:`audit`          — L6 audit trail
    """

    def __init__(self, config: AgentConfig):
        self._config = config
        self._state = AgentState.IDLE
        self._created_at = datetime.utcnow()

        # ── Layer singletons (lazy-initialised) ──
        self._model_router: Optional[ModelRouter] = None
        self._guardrails: Optional[GuardrailsEngine] = None
        self._cost_tracker: Optional[CostTracker] = None
        self._audit_trail: Optional[AuditTrail] = None
        self._otel: Optional[OTelManager] = None
        self._a2a: Optional[A2AProtocol] = None
        self._context_memory: Optional[ContextMemory] = None
        self._tool_registry: Optional[ToolRegistry] = None
        self._circuit_breaker = CircuitBreaker(
            name=f"agent-{config.agent_id}",
            failure_threshold=5,
            recovery_timeout=30.0,
        )

        # ── Stats ──
        self._stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_llm_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "total_latency_ms": 0.0,
            "guardrail_blocks": 0,
            "delegations": 0,
        }

    # ── Properties ───────────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        return self._config.agent_id

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def description(self) -> str:
        return self._config.description

    @property
    def config(self) -> AgentConfig:
        return self._config

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def capabilities(self) -> list[AgentCapability]:
        return self._config.capabilities

    # ── Layer Accessors (lazy init) ──────────────────────────────────

    def _get_model_router(self) -> ModelRouter:
        if self._model_router is None:
            self._model_router = ModelRouter()
        return self._model_router

    def _get_guardrails(self) -> GuardrailsEngine:
        if self._guardrails is None:
            self._guardrails = GuardrailsEngine()
        return self._guardrails

    def _get_cost_tracker(self) -> CostTracker:
        if self._cost_tracker is None:
            self._cost_tracker = CostTracker()
        return self._cost_tracker

    def _get_audit_trail(self) -> AuditTrail:
        if self._audit_trail is None:
            self._audit_trail = AuditTrail()
        return self._audit_trail

    def _get_otel(self) -> OTelManager:
        if self._otel is None:
            self._otel = OTelManager()
        return self._otel

    def _get_a2a(self) -> A2AProtocol:
        if self._a2a is None:
            self._a2a = A2AProtocol()
        return self._a2a

    def _get_context_memory(self) -> ContextMemory:
        if self._context_memory is None:
            self._context_memory = ContextMemory()
        return self._context_memory

    def _get_tool_registry(self) -> ToolRegistry:
        if self._tool_registry is None:
            self._tool_registry = ToolRegistry()
        return self._tool_registry

    # ── Dependency Injection ─────────────────────────────────────────

    def set_model_router(self, router: ModelRouter) -> None:
        """Inject a shared ModelRouter instance."""
        self._model_router = router

    def set_guardrails(self, engine: GuardrailsEngine) -> None:
        self._guardrails = engine

    def set_cost_tracker(self, tracker: CostTracker) -> None:
        self._cost_tracker = tracker

    def set_audit_trail(self, trail: AuditTrail) -> None:
        self._audit_trail = trail

    def set_otel(self, otel: OTelManager) -> None:
        self._otel = otel

    def set_a2a(self, a2a: A2AProtocol) -> None:
        self._a2a = a2a

    def set_context_memory(self, memory: ContextMemory) -> None:
        self._context_memory = memory

    def set_tool_registry(self, registry: ToolRegistry) -> None:
        self._tool_registry = registry

    # ── Abstract Method ──────────────────────────────────────────────

    @abc.abstractmethod
    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Agent-specific logic — implemented by each concrete agent.

        Args:
            ctx: Execution context with user input, auth, params, etc.

        Returns:
            A dict with the agent's result payload.  The ``run()``
            method wraps this in a standardised ``AgentResult``.
        """
        ...

    # ── Main Orchestration ───────────────────────────────────────────

    async def run(self, ctx: AgentExecutionContext) -> AgentResult:
        """
        Full execution pipeline with all 9 layers wired in.

        Flow:
            1. Input guardrails  (L6)
            2. Audit: EXECUTE    (L6)
            3. OTel span start   (L6)
            4. Context restore   (L3)
            5. execute() — agent logic (subclass)
            6. Output guardrails (L6)
            7. Cost tracking     (L9)
            8. Context save      (L3)
            9. Audit: COMPLETE   (L6)
            10. OTel span end    (L6)
        """
        start_time = time.time()
        self._state = AgentState.EXECUTING
        self._stats["total_executions"] += 1

        result = AgentResult(
            execution_id=ctx.execution_id,
            agent_id=self.agent_id,
            trace_id=ctx.trace_id,
        )

        try:
            # ── 1. Input Guardrails (L6) ──
            if self._config.guardrails_enabled:
                input_check = self._get_guardrails().check_input(ctx.input)
                if not input_check.passed:
                    violations = [v.get("type", "unknown") for v in input_check.violations]
                    result.status = "blocked"
                    result.error = f"Input blocked by guardrails: {', '.join(violations)}"
                    result.guardrail_flags = violations
                    self._stats["guardrail_blocks"] += 1
                    logger.warning(
                        "Agent %s: input blocked — violations=%s",
                        self.agent_id, violations,
                    )
                    return result

            # ── 2. Audit: EXECUTE (L6) ──
            if self._config.audit_enabled:
                self._get_audit_trail().record(
                    action=AuditAction.EXECUTE,
                    actor_id=ctx.user.user_id if ctx.user else "system",
                    actor_type="user" if ctx.user else "system",
                    resource_type="agent",
                    resource_id=self.agent_id,
                    tenant_id=ctx.tenant_id,
                    details={
                        "execution_id": ctx.execution_id,
                        "input_length": len(ctx.input),
                        "model": ctx.model_override or self._config.default_model,
                    },
                )

            # ── 3. OTel Span (L6) ──
            span = self._get_otel().start_span(
                operation_name=f"agent.{self.agent_id}.execute",
                attributes={
                    "agent_id": self.agent_id,
                    "execution_id": ctx.execution_id,
                    "tenant_id": ctx.tenant_id,
                    "trace_id": ctx.trace_id,
                },
            )

            # ── 4. Context Restore (L3) ──
            if ctx.session_id:
                session = self._get_context_memory().get_session(ctx.session_id)
                if session:
                    ctx.conversation_history = [
                        t.to_dict() for t in session.history[-10:]
                    ]

            # ── 5. Execute Agent Logic ──
            agent_output = await self.execute(ctx)

            # ── 6. Output Guardrails (L6) ──
            output_text = str(agent_output.get("result", agent_output))
            if self._config.guardrails_enabled:
                output_check = self._get_guardrails().check_output(output_text)
                if not output_check.passed:
                    violations = [v.get("type", "unknown") for v in output_check.violations]
                    result.guardrail_flags = violations
                    logger.warning(
                        "Agent %s: output flagged — violations=%s (allowing with flags)",
                        self.agent_id, violations,
                    )

            # ── Build Result ──
            elapsed_ms = (time.time() - start_time) * 1000
            result.status = "succeeded"
            result.result = agent_output
            result.confidence = agent_output.get("confidence", 0.8)
            result.model_used = agent_output.get("model_used", self._config.default_model)
            result.input_tokens = agent_output.get("input_tokens", 0)
            result.output_tokens = agent_output.get("output_tokens", 0)
            result.latency_ms = elapsed_ms
            result.delegated_to = agent_output.get("delegated_to", [])

            # ── 7. Cost Tracking (L9) ──
            if self._config.cost_tracking_enabled and result.input_tokens > 0:
                cost = self._get_cost_tracker().record_usage(UsageRecord(
                    agent_id=self.agent_id,
                    user_id=ctx.user.user_id if ctx.user else "system",
                    tenant_id=ctx.tenant_id,
                    model=result.model_used,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                    execution_id=ctx.execution_id,
                ))
                result.cost_usd = cost

            # ── 8. Context Save (L3) ──
            if ctx.session_id:
                memory = self._get_context_memory()
                memory.add_turn(
                    ctx.session_id,
                    ConversationTurn(
                        role="user",
                        agent_id=self.agent_id,
                        content=ctx.input,
                    ),
                )
                memory.add_turn(
                    ctx.session_id,
                    ConversationTurn(
                        role="assistant",
                        agent_id=self.agent_id,
                        content=output_text[:2000],
                        metadata={"execution_id": ctx.execution_id},
                    ),
                )

            # ── 9. Audit: COMPLETE (L6) ──
            if self._config.audit_enabled:
                self._get_audit_trail().record(
                    action=AuditAction.READ,
                    actor_id=self.agent_id,
                    actor_type="agent",
                    resource_type="execution",
                    resource_id=ctx.execution_id,
                    tenant_id=ctx.tenant_id,
                    details={
                        "status": "succeeded",
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd,
                        "latency_ms": result.latency_ms,
                    },
                )

            # ── 10. OTel End (L6) ──
            self._get_otel().end_span(
                span.span_id,
                attributes={
                    "status": "succeeded",
                    "latency_ms": elapsed_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                },
            )

            # Update stats
            self._stats["successful_executions"] += 1
            self._stats["total_input_tokens"] += result.input_tokens
            self._stats["total_output_tokens"] += result.output_tokens
            self._stats["total_cost_usd"] += result.cost_usd
            self._stats["total_latency_ms"] += result.latency_ms

        except Exception as exc:
            elapsed_ms = (time.time() - start_time) * 1000
            result.status = "failed"
            result.error = str(exc)
            result.latency_ms = elapsed_ms
            self._stats["failed_executions"] += 1
            logger.error("Agent %s execution failed: %s", self.agent_id, exc, exc_info=True)

            # Audit the failure
            if self._config.audit_enabled:
                self._get_audit_trail().record(
                    action=AuditAction.READ,
                    actor_id=self.agent_id,
                    actor_type="agent",
                    resource_type="execution",
                    resource_id=ctx.execution_id,
                    tenant_id=ctx.tenant_id,
                    details={"status": "failed", "error": str(exc)},
                )

        finally:
            self._state = AgentState.IDLE

        return result

    # ── L5: LLM Call Helper ──────────────────────────────────────────

    async def call_llm(
        self,
        ctx: AgentExecutionContext,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> ProviderResponse:
        """
        Call an LLM via the ModelRouter with circuit breaker protection.

        Uses the agent's default model unless overridden by ``ctx.model_override``
        or the ``model`` parameter.

        Returns:
            ProviderResponse with content, token counts, and latency.
        """
        target_model = model or ctx.model_override or self._config.default_model
        sys_prompt = system_prompt or self._config.system_prompt

        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})

        # Add conversation history for multi-turn context
        for turn in ctx.conversation_history[-6:]:
            messages.append({
                "role": turn.get("role", "user"),
                "content": turn.get("content", ""),
            })

        messages.append({"role": "user", "content": prompt})

        self._stats["total_llm_calls"] += 1

        response = await self._get_model_router().call(
            messages=messages,
            model=target_model,
            max_tokens=max_tokens or self._config.max_tokens,
            temperature=temperature or self._config.temperature,
        )

        return response

    # ── L3: Delegation Helper ────────────────────────────────────────

    async def delegate(
        self,
        ctx: AgentExecutionContext,
        target_agent_id: str,
        task: str,
        params: Optional[dict[str, Any]] = None,
    ) -> AgentMessage:
        """
        Delegate a subtask to another agent via the A2A protocol.

        The target agent will receive the task as a REQUEST message
        with this agent as the sender.

        Returns:
            The AgentMessage that was queued for delivery.
        """
        a2a = self._get_a2a()
        message = a2a.send(
            sender_id=self.agent_id,
            receiver_id=target_agent_id,
            message_type=MessageType.REQUEST,
            content=task,
            metadata={
                "execution_id": ctx.execution_id,
                "trace_id": ctx.trace_id,
                "params": params or {},
                "parent_agent": self.agent_id,
            },
        )
        self._stats["delegations"] += 1
        logger.info(
            "Agent %s delegated to %s: %s",
            self.agent_id, target_agent_id, task[:80],
        )
        return message

    # ── L3: Context Memory Helpers ───────────────────────────────────

    def remember(self, session_id: str, key: str, value: Any) -> None:
        """Store a value in context memory for the session."""
        self._get_context_memory().store(session_id, key, value)

    def recall(self, session_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from context memory."""
        return self._get_context_memory().get(session_id, key, default)

    # ── L6: Guardrail Helpers ────────────────────────────────────────

    def guard_input(self, text: str) -> GuardrailResult:
        """Run input through guardrails and return the result."""
        return self._get_guardrails().check_input(text)

    def guard_output(self, text: str) -> GuardrailResult:
        """Run output through guardrails and return the result."""
        return self._get_guardrails().check_output(text)

    # ── L4: Tool Helpers ─────────────────────────────────────────────

    def search_tools(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search the tool registry for tools matching the query."""
        return self._get_tool_registry().search(query, top_k=top_k)

    # ── L6: Audit Helper ────────────────────────────────────────────

    def audit(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        tenant_id: str = "default",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an audit trail entry."""
        self._get_audit_trail().record(
            action=action,
            actor_id=self.agent_id,
            actor_type="agent",
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            details=details or {},
        )

    # ── Stats & Info ─────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return agent statistics."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self._state.value,
            "version": self._config.version,
            "uptime_seconds": (datetime.utcnow() - self._created_at).total_seconds(),
            **self._stats,
        }

    def info(self) -> dict[str, Any]:
        """Return agent metadata for API responses."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "version": self._config.version,
            "state": self._state.value,
            "default_model": self._config.default_model,
            "capabilities": [
                {"name": c.name, "description": c.description}
                for c in self._config.capabilities
            ],
            "tags": self._config.tags,
            "guardrails_enabled": self._config.guardrails_enabled,
            "cost_tracking_enabled": self._config.cost_tracking_enabled,
        }

    def reset_stats(self) -> None:
        """Reset counters — for testing."""
        self._stats = {k: 0 if isinstance(v, int) else 0.0 for k, v in self._stats.items()}
