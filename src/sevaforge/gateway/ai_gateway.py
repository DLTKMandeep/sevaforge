"""
SevaForge AI Gateway — Unified Facade
Orchestrates: Prompt Assembly → Cache Lookup → Model Call → Schema Gate.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, AsyncIterator

from sevaforge.config import get_settings
from sevaforge.models.schemas import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AssembledPrompt,
    ExecutionStatus,
    SSEEvent,
    SSEEventType,
)

from .prompt_engine import PromptEngine
from .schema_gate import SchemaGate, SchemaValidationError
from .semantic_cache import SemanticCache

logger = logging.getLogger(__name__)


class AIGateway:
    """
    The single entry point for all LLM interactions.

    Flow:
        1. Assemble prompt from template + variables  (PromptEngine)
        2. Check cache for existing response           (SemanticCache)
        3. Route to LLM provider                       (ModelRouter — pluggable)
        4. Validate response against output schema      (SchemaGate)
        5. Store in cache
        6. Return typed response

    Usage:
        gateway = AIGateway()
        response = await gateway.execute(request, agent_id="code-review")

    Streaming:
        async for event in gateway.execute_stream(request, agent_id="code-review"):
            yield event
    """

    def __init__(
        self,
        prompt_engine: PromptEngine | None = None,
        cache: SemanticCache | None = None,
        schema_gate: SchemaGate | None = None,
    ):
        self._prompt_engine = prompt_engine or PromptEngine()
        self._cache = cache or SemanticCache()
        self._schema_gate = schema_gate or SchemaGate()
        self._settings = get_settings()

        # Pluggable model caller — set via configure()
        self._model_caller: Any = None

    def configure(self, model_caller: Any) -> None:
        """
        Inject the model caller (e.g., ModelRouter, AnthropicClient).

        The caller must implement:
            async def call(messages: list[dict], model: str, max_tokens: int) -> str
        """
        self._model_caller = model_caller
        logger.info("AI Gateway configured with model caller: %s", type(model_caller).__name__)

    async def _call_model(self, prompt: AssembledPrompt, model: str | None = None) -> str:
        """
        Call the LLM with the assembled prompt.

        If no model_caller is configured, returns a mock response for development.
        """
        model = model or self._settings.default_model

        if self._model_caller is None:
            # Development mock — returns a placeholder
            logger.warning("No model caller configured — returning mock response")
            messages_preview = prompt.messages[-1].content[:100] if prompt.messages else ""
            return (
                f'{{"result": "Mock response for development", '
                f'"model": "{model}", '
                f'"input_preview": "{messages_preview}..."}}'
            )

        messages = [{"role": m.role, "content": m.content} for m in prompt.messages]
        return await self._model_caller.call(
            messages=messages,
            model=model,
            max_tokens=self._settings.max_tokens,
        )

    async def execute(
        self,
        request: AgentExecuteRequest,
        agent_id: str,
        template_id: str | None = None,
        output_schema: Any | None = None,
    ) -> AgentExecuteResponse:
        """
        Full synchronous execution pipeline.

        Args:
            request: The incoming agent execution request.
            agent_id: The agent handling this request.
            template_id: Prompt template to use (defaults to agent_id).
            output_schema: Optional Pydantic model for output validation.

        Returns:
            AgentExecuteResponse with result, cost, latency, etc.
        """
        start_time = time.time()
        trace_id = f"sf-{uuid.uuid4().hex[:12]}"
        execution_id = str(uuid.uuid4())
        template_id = template_id or agent_id

        logger.info(
            "Gateway execute: agent=%s, trace=%s, cache_bypass=%s",
            agent_id,
            trace_id,
            request.cache_bypass,
        )

        try:
            # ── Step 1: Assemble Prompt ──────────────────────────────────
            variables = {"input": request.input, **request.params}
            try:
                prompt = self._prompt_engine.assemble(template_id, variables)
            except KeyError:
                # No template found — build a simple prompt
                from sevaforge.models.schemas import PromptMessage

                prompt = AssembledPrompt(
                    messages=[
                        PromptMessage(role="system", content=f"You are {agent_id}, an AI assistant."),
                        PromptMessage(role="user", content=request.input),
                    ],
                    template_id="default",
                    template_version="1.0.0",
                    variables=variables,
                    estimated_tokens=len(request.input) // 4,
                )

            prompt_hash = self._prompt_engine.hash_prompt(prompt)

            # ── Step 2: Cache Lookup ───────────────────────────────────
            if not request.cache_bypass:
                cache_hit = self._cache.lookup(prompt_hash)
                if cache_hit:
                    latency_ms = (time.time() - start_time) * 1000
                    logger.info("Cache hit for trace=%s (latency=%.1fms)", trace_id, latency_ms)
                    return AgentExecuteResponse(
                        execution_id=execution_id,
                        agent_id=agent_id,
                        status=ExecutionStatus.SUCCEEDED,
                        result=cache_hit.response,
                        confidence=1.0,
                        trace_id=trace_id,
                        model_used=cache_hit.model,
                        latency_ms=latency_ms,
                        cached=True,
                    )

            # ── Step 3: Call Model ─────────────────────────────────────
            model = request.model or self._settings.default_model
            raw_output = await self._call_model(prompt, model)

            # ── Step 4: Schema Validation ────────────────────────────────
            result: Any = raw_output
            confidence = 0.8  # Base confidence for unvalidated output

            if output_schema:
                try:
                    validated = await self._schema_gate.validate_with_retry(
                        raw_output,
                        output_schema,
                        retry_fn=lambda p: self._call_model(
                            AssembledPrompt(
                                messages=[
                                    prompt.messages[0],
                                    from_models_import("PromptMessage")(role="user", content=p),
                                ],
                                template_id=template_id,
                                template_version=prompt.template_version,
                            )
                        ),
                        original_prompt=request.input,
                    )
                    result = validated.model_dump()
                    confidence = 0.95
                except SchemaValidationError as e:
                    logger.error("Schema validation failed for trace=%s: %s", trace_id, e)
                    # Return raw output with lower confidence
                    result = {"raw_output": raw_output, "validation_errors": e.errors}
                    confidence = 0.4

            # ── Step 5: Cache Store ────────────────────────────────────
            self._cache.store(prompt_hash, result, model)

            # ── Build Response ─────────────────────────────────────────
            latency_ms = (time.time() - start_time) * 1000
            # Rough token estimation
            input_tokens = prompt.estimated_tokens
            output_tokens = len(str(raw_output)) // 4

            return AgentExecuteResponse(
                execution_id=execution_id,
                agent_id=agent_id,
                status=ExecutionStatus.SUCCEEDED,
                result=result,
                confidence=confidence,
                trace_id=trace_id,
                model_used=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=self._estimate_cost(model, input_tokens, output_tokens),
                latency_ms=latency_ms,
                cached=False,
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.exception("Gateway execution failed: trace=%s", trace_id)
            return AgentExecuteResponse(
                execution_id=execution_id,
                agent_id=agent_id,
                status=ExecutionStatus.FAILED,
                result={"error": str(e)},
                confidence=0.0,
                trace_id=trace_id,
                latency_ms=latency_ms,
            )

    async def execute_stream(
        self,
        request: AgentExecuteRequest,
        agent_id: str,
        template_id: str | None = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Streaming execution — yields SSE events as the pipeline progresses.

        Events:
          1. thinking   — Prompt assembled, sending to model
          2. tool_call  — (future) Tool use detected
          3. retrieval  — (future) RAG retrieval happening
          4. result     — Final result
          5. done       — Stream complete
        """
        trace_id = f"sf-{uuid.uuid4().hex[:12]}"

        # Event: Thinking
        yield SSEEvent(
            event=SSEEventType.THINKING,
            data={"message": "Assembling prompt and checking cache..."},
            trace_id=trace_id,
        )

        # Assemble prompt
        template_id = template_id or agent_id
        variables = {"input": request.input, **request.params}
        try:
            prompt = self._prompt_engine.assemble(template_id, variables)
        except KeyError:
            from sevaforge.models.schemas import PromptMessage

            prompt = AssembledPrompt(
                messages=[
                    PromptMessage(role="system", content=f"You are {agent_id}, an AI assistant."),
                    PromptMessage(role="user", content=request.input),
                ],
                template_id="default",
                template_version="1.0.0",
                variables=variables,
            )

        # Event: Thinking (model call)
        yield SSEEvent(
            event=SSEEventType.THINKING,
            data={"message": f"Calling model: {request.model or self._settings.default_model}"},
            trace_id=trace_id,
        )

        # Call model
        try:
            raw_output = await self._call_model(prompt, request.model)
        except Exception as e:
            yield SSEEvent(
                event=SSEEventType.ERROR,
                data={"error": str(e)},
                trace_id=trace_id,
            )
            return

        # Event: Result
        yield SSEEvent(
            event=SSEEventType.RESULT,
            data={"result": raw_output},
            trace_id=trace_id,
        )

        # Event: Done
        yield SSEEvent(
            event=SSEEventType.DONE,
            data={"message": "Execution complete"},
            trace_id=trace_id,
        )

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Rough cost estimation per model (USD)."""
        # Pricing per 1M tokens (approximate)
        pricing = {
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
            "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
        }
        rates = pricing.get(model, {"input": 3.0, "output": 15.0})
        return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

    @property
    def cache(self) -> SemanticCache:
        """Access the semantic cache for stats/management."""
        return self._cache

    @property
    def prompt_engine(self) -> PromptEngine:
        """Access the prompt engine for template management."""
        return self._prompt_engine

    @property
    def schema_gate(self) -> SchemaGate:
        """Access the schema gate for validation."""
        return self._schema_gate
