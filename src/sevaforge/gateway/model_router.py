"""
SevaForge Model Router — Multi-Provider LLM Gateway with Intelligent Routing

Routes requests to Anthropic, OpenAI, Google, or Mock providers.  Now with
a pluggable routing strategy layer that *decides* which model to use based
on task complexity, cost, latency, and capability requirements.

Architecture::

    User Request
         |
    TaskClassifier -> complexity (simple / medium / complex / expert)
         |
    RoutingStrategy -> picks model (cost / quality / latency / balanced / capability)
         |
    ModelRegistry -> resolves model_id -> provider adapter
         |
    ProviderAdapter -> Anthropic / OpenAI / Google / Mock
         |
    CircuitBreaker + Retry
         |
    ProviderResponse (content + tokens + cost + routing_decision)

Usage::

    from sevaforge.gateway.model_router import ModelRouter

    # Simple (backward compatible) -- returns text string
    router = ModelRouter()
    text = await router.call(
        messages=[{"role": "user", "content": "Hello"}],
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
    )

    # Advanced -- returns ProviderResponse with full metadata
    response = await router.call_advanced(
        messages=[{"role": "user", "content": "Review this code for security issues"}],
        max_tokens=4096,
        # model is auto-selected by the routing strategy!
    )
    print(response.content)           # LLM output
    print(response.routing_decision)  # why this model was chosen
    print(response.cost_usd)          # actual cost

Integration with AIGateway::

    gateway = AIGateway()
    gateway.configure(ModelRouter())
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from sevaforge.auth.rate_limiter import CircuitBreaker, CircuitBreakerError
from sevaforge.config import get_settings
from sevaforge.gateway.model_registry import ModelRegistry, ModelTier
from sevaforge.gateway.routing_strategy import (
    BalancedStrategy,
    CapabilityMatchedStrategy,
    CostOptimizedStrategy,
    LatencyFirstStrategy,
    QualityFirstStrategy,
    RoutingDecision,
    TaskClassifier,
    TaskComplexity,
    available_strategies,
    get_strategy,
)

logger = logging.getLogger(__name__)

# -- Optional provider SDK imports --

try:
    import anthropic  # type: ignore[import-untyped]

    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    HAS_ANTHROPIC = False

try:
    import openai  # type: ignore[import-untyped]

    HAS_OPENAI = True
except ImportError:
    openai = None  # type: ignore[assignment]
    HAS_OPENAI = False

try:
    import google.generativeai as genai  # type: ignore[import-untyped]

    HAS_GOOGLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    HAS_GOOGLE = False


# -- Data Models --


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """
    Normalised response from any LLM provider.

    Includes the routing decision that explains *why* this model was
    chosen, plus a computed cost_usd for FinOps tracking.
    """

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    provider: str  # "anthropic" | "openai" | "google" | "mock"
    routing_decision: RoutingDecision | None = None  # How the model was selected
    cost_usd: float = 0.0  # Computed cost for this call


class ProviderError(Exception):
    """Raised when an LLM provider call fails after exhausting retries."""

    def __init__(self, provider: str, message: str, cause: BaseException | None = None):
        self.provider = provider
        super().__init__(f"[{provider}] {message}")
        self.__cause__ = cause


# -- Provider Protocol --


class ProviderAdapter(Protocol):
    """Structural type that every adapter satisfies."""

    @property
    def name(self) -> str: ...

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse: ...


# -- Anthropic Adapter --


class AnthropicAdapter:
    """Adapter for Anthropic Claude models (claude-*)."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        if not HAS_ANTHROPIC:
            raise ProviderError(
                "anthropic",
                "The 'anthropic' package is not installed. "
                "Install it with: pip install anthropic",
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        start = time.perf_counter()

        # Anthropic requires a separate 'system' parameter; extract it from
        # the messages list so the SDK receives only user/assistant turns.
        system_prompt: str | None = None
        api_messages: list[dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                api_messages.append(msg)

        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": api_messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = await self._client.messages.create(**kwargs)

            latency = (time.perf_counter() - start) * 1000
            return ProviderResponse(
                content=response.content[0].text,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=round(latency, 2),
                provider=self.name,
            )
        except Exception as exc:
            raise ProviderError(self.name, str(exc), cause=exc) from exc


# -- OpenAI Adapter --


class OpenAIAdapter:
    """Adapter for OpenAI GPT / o1 / o3 models."""

    name = "openai"

    def __init__(self, api_key: str) -> None:
        if not HAS_OPENAI:
            raise ProviderError(
                "openai",
                "The 'openai' package is not installed. "
                "Install it with: pip install openai",
            )
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        start = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,  # type: ignore[arg-type]
            )

            choice = response.choices[0]
            usage = response.usage

            latency = (time.perf_counter() - start) * 1000
            return ProviderResponse(
                content=choice.message.content or "",
                model=response.model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=round(latency, 2),
                provider=self.name,
            )
        except Exception as exc:
            raise ProviderError(self.name, str(exc), cause=exc) from exc


# -- Google Gemini Adapter --


class GoogleAdapter:
    """Adapter for Google Gemini models."""

    name = "google"

    def __init__(self, api_key: str) -> None:
        if not HAS_GOOGLE:
            raise ProviderError(
                "google",
                "The 'google-generativeai' package is not installed. "
                "Install it with: pip install google-generativeai",
            )
        genai.configure(api_key=api_key)

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        start = time.perf_counter()
        try:
            gm = genai.GenerativeModel(
                model_name=model,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )

            # Convert messages to Gemini content format.
            contents: list[dict[str, Any]] = []
            system_parts: list[str] = []
            for msg in messages:
                if msg["role"] == "system":
                    system_parts.append(msg["content"])
                else:
                    role = "user" if msg["role"] == "user" else "model"
                    text = msg["content"]
                    if system_parts and role == "user":
                        text = "\n\n".join(system_parts) + "\n\n" + text
                        system_parts.clear()
                    contents.append({"role": role, "parts": [text]})

            # If only system messages were provided, promote to a single user turn.
            if not contents and system_parts:
                contents.append({"role": "user", "parts": ["\n\n".join(system_parts)]})

            response = await gm.generate_content_async(contents=contents)

            latency = (time.perf_counter() - start) * 1000

            # Approximate token counts from character lengths.
            input_text = " ".join(
                part for c in contents for part in (c.get("parts") or []) if isinstance(part, str)
            )
            approx_input_tokens = len(input_text) // 4
            output_text = response.text or ""
            approx_output_tokens = len(output_text) // 4

            return ProviderResponse(
                content=output_text,
                model=model,
                input_tokens=approx_input_tokens,
                output_tokens=approx_output_tokens,
                latency_ms=round(latency, 2),
                provider=self.name,
            )
        except Exception as exc:
            raise ProviderError(self.name, str(exc), cause=exc) from exc


# -- Mock Adapter --


class MockAdapter:
    """
    Mock LLM provider for local development and testing.

    Generates deterministic, realistic-looking responses without requiring
    any API keys or external network calls.  Simulates 100-500 ms latency.
    """

    name = "mock"

    _RESPONSES = [
        "Based on my analysis, the most effective approach would be to break this down "
        "into smaller components and tackle each one systematically.",
        "I've reviewed the information provided. Here are the key findings and "
        "recommended next steps for your consideration.",
        "This is an interesting challenge. Let me outline a structured solution that "
        "addresses each of your requirements in turn.",
        "After careful evaluation, I recommend the following approach which balances "
        "simplicity, performance, and maintainability.",
        "Here's a comprehensive response covering the main points. I've organized "
        "it by priority so you can act on the most critical items first.",
    ]

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        start = time.perf_counter()

        # Deterministic-ish selection based on input content length.
        input_text = " ".join(m.get("content", "") for m in messages)
        idx = len(input_text) % len(self._RESPONSES)
        base = self._RESPONSES[idx]

        # Mirror a portion of the input to make the response feel contextual.
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg["content"]
                break

        if last_user:
            snippet = last_user[:120].rstrip()
            body = (
                f'{base}\n\nRegarding your input ("{snippet}..."), '
                "I have processed the request and generated this response "
                "using the mock provider.  In production, this would be "
                "replaced by a real LLM completion."
            )
        else:
            body = base

        # Simulate realistic latency (100-500 ms).
        delay = random.uniform(0.1, 0.5)
        await asyncio.sleep(delay)

        latency = (time.perf_counter() - start) * 1000
        approx_input = len(input_text) // 4
        approx_output = len(body) // 4

        return ProviderResponse(
            content=body,
            model=f"mock-{model}",
            input_tokens=approx_input,
            output_tokens=approx_output,
            latency_ms=round(latency, 2),
            provider=self.name,
        )


# -- Router Stats --


@dataclass
class RouterStats:
    """Aggregated call statistics for the model router."""

    total_calls: int = 0
    total_tokens: int = 0
    failover_count: int = 0
    calls_per_provider: dict[str, int] = field(default_factory=dict)
    failures_per_provider: dict[str, int] = field(default_factory=dict)
    latency_sum_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.latency_sum_ms / self.total_calls if self.total_calls else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "failover_count": self.failover_count,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "calls_per_provider": dict(self.calls_per_provider),
            "failures_per_provider": dict(self.failures_per_provider),
        }


# -- Model Router --


class ModelRouter:
    """
    Multi-provider LLM router with intelligent routing and circuit breaker failover.

    Supports:
    - Anthropic (Claude models) via ``anthropic`` SDK
    - OpenAI (GPT / o1 / o3 models) via ``openai`` SDK
    - Google (Gemini models) via ``google-generativeai`` SDK
    - Mock provider for development (no API key needed)

    Intelligent Routing (NEW):
    - TaskClassifier analyses input complexity (simple -> expert)
    - RoutingStrategy selects optimal model (cost / quality / latency / balanced)
    - ModelRegistry resolves model tier to concrete model + provider

    Legacy Features (preserved):
    - Automatic provider detection from model name prefix
    - Independent circuit breaker per provider (auto-failover)
    - Configurable retry with exponential backoff
    - Token counting and cost estimation
    - Request / response logging with stats aggregation

    Two calling modes:
    - ``call()``          -- backward compatible, returns str
    - ``call_advanced()`` -- returns ProviderResponse with routing decision
    """

    # Provider prefixes for auto-detection (used in legacy mode)
    _ANTHROPIC_PREFIXES = ("claude-",)
    _OPENAI_PREFIXES = ("gpt-", "o1-", "o3-")
    _GOOGLE_PREFIXES = ("gemini-",)

    def __init__(
        self,
        *,
        routing_strategy: str = "balanced",
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        breaker_failure_threshold: int = 5,
        breaker_recovery_timeout: float = 30.0,
        strategy_kwargs: dict[str, Any] | None = None,
    ) -> None:
        settings = get_settings()

        self._default_model = settings.default_model
        self._fallback_model = settings.fallback_model
        self._max_tokens = settings.max_tokens
        self._temperature = settings.temperature

        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

        # -- Intelligent Routing Components (NEW) --
        self._model_registry = ModelRegistry()
        self._task_classifier = TaskClassifier()
        self._strategy = get_strategy(routing_strategy, **(strategy_kwargs or {}))
        self._strategy_name = routing_strategy

        # -- Build adapters lazily based on available keys --
        self._adapters: dict[str, Any] = {}  # provider name -> adapter
        self._breakers: dict[str, CircuitBreaker] = {}

        if settings.anthropic_api_key:
            try:
                self._adapters["anthropic"] = AnthropicAdapter(settings.anthropic_api_key)
            except ProviderError as exc:
                logger.warning("Anthropic adapter unavailable: %s", exc)

        # OpenAI key is not in default settings; support it via env anyway.
        openai_key = getattr(settings, "openai_api_key", "") or ""
        if openai_key:
            try:
                self._adapters["openai"] = OpenAIAdapter(openai_key)
            except ProviderError as exc:
                logger.warning("OpenAI adapter unavailable: %s", exc)

        if settings.google_api_key:
            try:
                self._adapters["google"] = GoogleAdapter(settings.google_api_key)
            except ProviderError as exc:
                logger.warning("Google adapter unavailable: %s", exc)

        # Mock is always available.
        self._adapters["mock"] = MockAdapter()

        # Create a circuit breaker per adapter.
        for name in self._adapters:
            self._breakers[name] = CircuitBreaker(
                name=f"model-router-{name}",
                failure_threshold=breaker_failure_threshold,
                recovery_timeout=breaker_recovery_timeout,
            )

        self._stats = RouterStats()

        available = ", ".join(sorted(self._adapters.keys()))
        logger.info(
            "ModelRouter initialised -- strategy=%s adapters=[%s] default=%s fallback=%s",
            routing_strategy,
            available,
            self._default_model,
            self._fallback_model,
        )

    # -- Public Interface (AIGateway contract) --

    async def call(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        Route an LLM call to the appropriate provider and return the
        completion text.

        This is the primary method consumed by
        :meth:`AIGateway._call_model`.

        Args:
            messages:   Chat messages in OpenAI-style format
                        ``[{"role": "...", "content": "..."}]``.
            model:      Model identifier (e.g. ``claude-sonnet-4-20250514``).
                        Falls back to ``settings.default_model``.
            max_tokens: Maximum tokens for the response.
                        Falls back to ``settings.max_tokens``.

        Returns:
            The generated text from the LLM.

        Raises:
            ProviderError: If both the primary and fallback providers fail.
        """
        model = model or self._default_model
        max_tokens = max_tokens or self._max_tokens
        provider_name = self._detect_provider(model)

        # -- Primary attempt --
        try:
            response = await self._call_with_retry(
                provider_name, messages, model, max_tokens
            )
            self._record_success(response)
            return response.content
        except (CircuitBreakerError, ProviderError) as primary_exc:
            logger.warning(
                "Primary provider '%s' failed for model '%s': %s -- attempting failover",
                provider_name,
                model,
                primary_exc,
            )
            self._stats.failover_count += 1
            self._stats.failures_per_provider[provider_name] = (
                self._stats.failures_per_provider.get(provider_name, 0) + 1
            )

        # -- Failover attempt --
        fallback_provider = self._detect_provider(self._fallback_model)

        # If the fallback resolves to the same provider that just failed,
        # drop straight to mock so we always have a last resort.
        if fallback_provider == provider_name:
            fallback_provider = "mock"
            fallback_model = self._fallback_model
        else:
            fallback_model = self._fallback_model

        try:
            response = await self._call_with_retry(
                fallback_provider, messages, fallback_model, max_tokens
            )
            self._record_success(response)
            logger.info(
                "Failover succeeded: provider=%s model=%s",
                fallback_provider,
                fallback_model,
            )
            return response.content
        except (CircuitBreakerError, ProviderError) as fallback_exc:
            logger.warning(
                "Fallback provider '%s' also failed: %s -- falling back to mock",
                fallback_provider,
                fallback_exc,
            )
            self._stats.failures_per_provider[fallback_provider] = (
                self._stats.failures_per_provider.get(fallback_provider, 0) + 1
            )

        # -- Last resort: mock --
        if fallback_provider != "mock":
            try:
                response = await self._call_with_retry(
                    "mock", messages, model, max_tokens
                )
                self._record_success(response)
                logger.info("Last-resort mock provider returned a response")
                return response.content
            except Exception as mock_exc:
                raise ProviderError(
                    "mock",
                    "All providers failed including mock",
                    cause=mock_exc,
                ) from mock_exc

        # If mock itself was the fallback and it failed, propagate.
        raise ProviderError(
            "all",
            f"All providers exhausted (primary={provider_name}, "
            f"fallback={fallback_provider})",
        )

    # -- Advanced Call (Intelligent Routing) --

    async def call_advanced(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        strategy_override: str | None = None,
    ) -> ProviderResponse:
        """
        Intelligent model routing -- the router DECIDES which model to use.

        If ``model`` is provided, it's used directly (explicit override).
        If ``model`` is None, the router:
            1. Classifies the input complexity
            2. Applies the routing strategy
            3. Selects the optimal model from the registry
            4. Dispatches to the provider

        Returns:
            ProviderResponse with content, tokens, cost, AND routing_decision
            explaining why this model was chosen.
        """
        max_tokens = max_tokens or self._max_tokens
        temp = temperature or self._temperature

        # -- Determine routing decision --
        routing_decision: RoutingDecision | None = None

        if model is None:
            # INTELLIGENT ROUTING: let the strategy decide
            input_text = " ".join(
                m.get("content", "") for m in messages if m.get("role") == "user"
            )
            complexity = self._task_classifier.classify(input_text)

            # Use override strategy or the default one
            strategy = (
                get_strategy(strategy_override)
                if strategy_override
                else self._strategy
            )

            available_providers = set(self._adapters.keys()) - {"mock"}
            if not available_providers:
                available_providers = {"mock"}

            routing_decision = strategy.select(
                complexity=complexity,
                registry=self._model_registry,
                available_providers=available_providers,
            )

            model = routing_decision.model_id
            provider_name = routing_decision.provider

            logger.info(
                "Multi-router: complexity=%s strategy=%s -> model=%s provider=%s reason='%s'",
                complexity.value,
                strategy.name,
                model,
                provider_name,
                routing_decision.reason,
            )
        else:
            # EXPLICIT MODEL: use legacy provider detection
            provider_name = self._detect_provider(model)

        # -- Call provider with retry + failover --
        try:
            response = await self._call_with_retry(
                provider_name, messages, model, max_tokens, temp
            )
        except (CircuitBreakerError, ProviderError):
            # Primary failed -- try failover
            self._stats.failover_count += 1
            fallback_provider = self._detect_provider(self._fallback_model)
            if fallback_provider == provider_name:
                fallback_provider = "mock"

            try:
                response = await self._call_with_retry(
                    fallback_provider, messages, self._fallback_model, max_tokens, temp
                )
            except (CircuitBreakerError, ProviderError):
                if fallback_provider != "mock":
                    response = await self._call_with_retry(
                        "mock", messages, model, max_tokens, temp
                    )
                else:
                    raise

        # -- Compute cost --
        model_profile = self._model_registry.get(response.model) or self._model_registry.get(model)
        if model_profile:
            cost = (
                response.input_tokens * model_profile.pricing.input_per_m
                + response.output_tokens * model_profile.pricing.output_per_m
            ) / 1_000_000
        else:
            cost = 0.0

        # -- Build enriched response --
        enriched = ProviderResponse(
            content=response.content,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            provider=response.provider,
            routing_decision=routing_decision,
            cost_usd=round(cost, 8),
        )

        self._record_success(enriched)
        return enriched

    # -- Strategy Management --

    def set_strategy(self, strategy_name: str, **kwargs: Any) -> None:
        """Switch the default routing strategy at runtime."""
        self._strategy = get_strategy(strategy_name, **kwargs)
        self._strategy_name = strategy_name
        logger.info("Routing strategy changed to: %s", strategy_name)

    @property
    def strategy_name(self) -> str:
        """Currently active routing strategy."""
        return self._strategy_name

    @property
    def model_registry(self) -> ModelRegistry:
        """Access the model registry for introspection."""
        return self._model_registry

    @property
    def task_classifier(self) -> TaskClassifier:
        """Access the task classifier for testing/debugging."""
        return self._task_classifier

    # -- Provider Detection --

    def _detect_provider(self, model: str) -> str:
        """
        Determine which provider to use based on the model name.

        Returns one of: ``"anthropic"``, ``"openai"``, ``"google"``, ``"mock"``.
        """
        lower = model.lower()

        if lower == "mock":
            return "mock"

        if any(lower.startswith(p) for p in self._ANTHROPIC_PREFIXES):
            if "anthropic" in self._adapters:
                return "anthropic"
            logger.debug("Anthropic adapter not available; routing to mock")
            return "mock"

        if any(lower.startswith(p) for p in self._OPENAI_PREFIXES):
            if "openai" in self._adapters:
                return "openai"
            logger.debug("OpenAI adapter not available; routing to mock")
            return "mock"

        if any(lower.startswith(p) for p in self._GOOGLE_PREFIXES):
            if "google" in self._adapters:
                return "google"
            logger.debug("Google adapter not available; routing to mock")
            return "mock"

        # Unknown model prefix -- fall back to mock.
        logger.debug("Unknown model prefix for '%s'; routing to mock", model)
        return "mock"

    # -- Retry + Circuit Breaker --

    async def _call_with_retry(
        self,
        provider_name: str,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float | None = None,
    ) -> ProviderResponse:
        """
        Call a provider adapter with exponential-backoff retry, guarded by
        the per-provider circuit breaker.

        Raises:
            CircuitBreakerError: If the breaker is open.
            ProviderError:       If all retries are exhausted.
        """
        adapter = self._adapters[provider_name]
        breaker = self._breakers[provider_name]
        temp = temperature if temperature is not None else self._temperature

        # Check circuit state before attempting any call.
        if breaker.state.value == "open":
            raise CircuitBreakerError(
                f"Circuit breaker for '{provider_name}' is open"
            )

        last_exc: BaseException | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = await adapter.call(
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temp,
                )
                breaker.record_success()
                return response

            except ProviderError as exc:
                last_exc = exc
                breaker.record_failure()
                logger.warning(
                    "Provider '%s' attempt %d/%d failed: %s",
                    provider_name,
                    attempt,
                    self._max_retries,
                    exc,
                )

                # If the breaker has tripped open, stop retrying immediately.
                if breaker.state.value == "open":
                    raise CircuitBreakerError(
                        f"Circuit breaker for '{provider_name}' tripped open "
                        f"after {attempt} failures"
                    ) from exc

                # Exponential backoff with jitter.
                if attempt < self._max_retries:
                    delay = self._retry_base_delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, delay * 0.3)
                    await asyncio.sleep(delay + jitter)

        raise ProviderError(
            provider_name,
            f"All {self._max_retries} retries exhausted",
            cause=last_exc,
        )

    # -- Stats Helpers --

    def _record_success(self, response: ProviderResponse) -> None:
        """Update aggregate statistics after a successful call."""
        self._stats.total_calls += 1
        self._stats.total_tokens += response.input_tokens + response.output_tokens
        self._stats.latency_sum_ms += response.latency_ms
        self._stats.calls_per_provider[response.provider] = (
            self._stats.calls_per_provider.get(response.provider, 0) + 1
        )

    # -- Public Accessors --

    @property
    def stats(self) -> RouterStats:
        """Access aggregated router statistics."""
        return self._stats

    @property
    def available_providers(self) -> list[str]:
        """List of provider names with initialised adapters."""
        return sorted(self._adapters.keys())

    def provider_health(self) -> dict[str, dict[str, Any]]:
        """
        Return health status of every provider circuit breaker.

        Useful for admin dashboards and health-check endpoints.
        """
        return {
            name: breaker.stats()
            for name, breaker in self._breakers.items()
        }

    def routing_info(self) -> dict[str, Any]:
        """
        Full routing system status -- for admin dashboards.

        Returns strategy config, model registry summary, provider health,
        and call statistics.
        """
        available = set(self._adapters.keys()) - {"mock"}
        return {
            "strategy": self._strategy_name,
            "available_strategies": available_strategies(),
            "providers": {
                "available": sorted(available),
                "all_adapters": sorted(self._adapters.keys()),
            },
            "model_registry": self._model_registry.tier_summary(
                available if available else {"mock"}
            ),
            "provider_health": self.provider_health(),
            "stats": self._stats.to_dict(),
        }

    def __repr__(self) -> str:
        providers = ", ".join(self.available_providers)
        return (
            f"<ModelRouter strategy={self._strategy_name!r} "
            f"providers=[{providers}] "
            f"default={self._default_model!r} "
            f"fallback={self._fallback_model!r}>"
        )
