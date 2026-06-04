"""
SevaForge Model Registry — Tiered Model Catalog

Every LLM model the platform can route to is registered here with its
capabilities, pricing, speed profile, and provider mapping.  The routing
strategy consults this registry to resolve a *tier* (fast / balanced /
premium / local) into the best concrete model that's actually available.

Concepts:
    ModelTier   — Capability bucket (FAST, BALANCED, PREMIUM, LOCAL).
    ModelProfile — Everything the router needs to know about one model:
                   provider, tier, pricing per token, typical latency,
                   context window, and capability tags.
    ModelRegistry — Singleton catalog.  call ``get_available(tier)`` and
                    it returns only models whose provider SDK + API key
                    are actually present.

Why tiers?
    A routing strategy never says "use claude-haiku-4-5-20251001".  It says
    "I need a FAST-tier model."  The registry resolves that to the best
    concrete model available *right now*.  If Anthropic is down, FAST
    resolves to gemini-2.0-flash instead.  The strategy doesn't need to
    know about failover — the registry handles it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# — Enums ———————————————————————————————————————————


class ModelTier(str, Enum):
    """
    Capability tiers — from cheapest/fastest to most capable.

    FAST      — Sub-second latency, low cost, good for classification,
                extraction, simple Q&A.  (Haiku, Flash)
    BALANCED  — General-purpose workhorses.  Code review, summarisation,
                multi-step reasoning.  (Sonnet, GPT-4o)
    PREMIUM   — Maximum capability.  Architecture decisions, complex
                analysis, creative writing.  (Opus, o3)
    LOCAL     — Self-hosted models via Ollama or vLLM.  Zero marginal
                cost, full data privacy, but lower capability.
    """
    FAST = "fast"
    BALANCED = "balanced"
    PREMIUM = "premium"
    LOCAL = "local"


class ModelCapability(str, Enum):
    """Tags that describe what a model is good at."""
    CHAT = "chat"
    CODE = "code"
    REASONING = "reasoning"
    CREATIVE = "creative"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    SUMMARIZATION = "summarization"
    VISION = "vision"
    TOOL_USE = "tool_use"
    LONG_CONTEXT = "long_context"


# — Data Models —————————————————————————————————————


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """
    Cost per million tokens (USD).

    Example: Claude Sonnet charges $3/M input, $15/M output.
    To get cost for a single call:
        cost = (input_tokens * input_per_m + output_tokens * output_per_m) / 1_000_000
    """
    input_per_m: float   # USD per 1M input tokens
    output_per_m: float  # USD per 1M output tokens


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """
    Complete profile for a single LLM model.

    This is what the router uses to make decisions.  Every field is
    a *static* property of the model — things that don't change at
    runtime (unlike latency, which the health tracker measures live).
    """
    model_id: str                        # e.g. "claude-sonnet-4-20250514"
    provider: str                        # "anthropic" | "openai" | "google" | "local"
    tier: ModelTier                      # capability bucket
    display_name: str                    # human-friendly name
    pricing: ModelPricing                # cost per M tokens
    context_window: int                  # max tokens (input + output)
    typical_latency_ms: float            # expected p50 latency for a 500-token response
    capabilities: frozenset[ModelCapability] = frozenset()
    max_output_tokens: int = 4096        # model's max output limit
    supports_streaming: bool = True
    supports_tool_use: bool = False
    supports_vision: bool = False
    deprecated: bool = False             # still works but will be removed
    notes: str = ""                      # e.g. "Best for code tasks"

    @property
    def cost_per_1k_tokens(self) -> float:
        """Blended cost estimate per 1K tokens (assumes 1:1 input:output ratio)."""
        return (self.pricing.input_per_m + self.pricing.output_per_m) / 2000

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "tier": self.tier.value,
            "display_name": self.display_name,
            "pricing": {
                "input_per_m_usd": self.pricing.input_per_m,
                "output_per_m_usd": self.pricing.output_per_m,
            },
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "typical_latency_ms": self.typical_latency_ms,
            "capabilities": sorted(c.value for c in self.capabilities),
            "supports_streaming": self.supports_streaming,
            "supports_tool_use": self.supports_tool_use,
            "supports_vision": self.supports_vision,
            "deprecated": self.deprecated,
            "notes": self.notes,
        }


# — Built-in Model Catalog —————————————————————————
#
# These are the models the platform ships with.  Operators can add
# custom models via the API or config file.

_BUILTIN_MODELS: list[ModelProfile] = [
    # — Anthropic ———————————————————————————————————
    ModelProfile(
        model_id="claude-opus-4-20250514",
        provider="anthropic",
        tier=ModelTier.PREMIUM,
        display_name="Claude Opus 4",
        pricing=ModelPricing(input_per_m=15.0, output_per_m=75.0),
        context_window=200_000,
        max_output_tokens=32_000,
        typical_latency_ms=3000,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.REASONING, ModelCapability.CREATIVE,
            ModelCapability.TOOL_USE, ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        }),
        supports_tool_use=True,
        supports_vision=True,
        notes="Most capable Anthropic model — use for complex reasoning",
    ),
    ModelProfile(
        model_id="claude-sonnet-4-20250514",
        provider="anthropic",
        tier=ModelTier.BALANCED,
        display_name="Claude Sonnet 4",
        pricing=ModelPricing(input_per_m=3.0, output_per_m=15.0),
        context_window=200_000,
        max_output_tokens=16_000,
        typical_latency_ms=1500,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.REASONING, ModelCapability.CREATIVE,
            ModelCapability.TOOL_USE, ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT, ModelCapability.SUMMARIZATION,
        }),
        supports_tool_use=True,
        supports_vision=True,
        notes="Best balance of speed, cost, and capability",
    ),
    ModelProfile(
        model_id="claude-haiku-4-5-20251001",
        provider="anthropic",
        tier=ModelTier.FAST,
        display_name="Claude Haiku 4.5",
        pricing=ModelPricing(input_per_m=0.80, output_per_m=4.0),
        context_window=200_000,
        max_output_tokens=8_192,
        typical_latency_ms=400,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.CLASSIFICATION, ModelCapability.EXTRACTION,
            ModelCapability.SUMMARIZATION, ModelCapability.TOOL_USE,
            ModelCapability.VISION,
        }),
        supports_tool_use=True,
        supports_vision=True,
        notes="Fastest Anthropic model — ideal for classification and extraction",
    ),

    # — OpenAI ——————————————————————————————————————
    ModelProfile(
        model_id="gpt-4o",
        provider="openai",
        tier=ModelTier.BALANCED,
        display_name="GPT-4o",
        pricing=ModelPricing(input_per_m=2.50, output_per_m=10.0),
        context_window=128_000,
        max_output_tokens=16_384,
        typical_latency_ms=1200,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.REASONING, ModelCapability.CREATIVE,
            ModelCapability.TOOL_USE, ModelCapability.VISION,
            ModelCapability.SUMMARIZATION,
        }),
        supports_tool_use=True,
        supports_vision=True,
        notes="OpenAI's flagship multimodal model",
    ),
    ModelProfile(
        model_id="gpt-4o-mini",
        provider="openai",
        tier=ModelTier.FAST,
        display_name="GPT-4o Mini",
        pricing=ModelPricing(input_per_m=0.15, output_per_m=0.60),
        context_window=128_000,
        max_output_tokens=16_384,
        typical_latency_ms=350,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.CLASSIFICATION, ModelCapability.EXTRACTION,
            ModelCapability.SUMMARIZATION, ModelCapability.TOOL_USE,
        }),
        supports_tool_use=True,
        notes="Cheapest OpenAI model — excellent for simple tasks",
    ),
    ModelProfile(
        model_id="o3",
        provider="openai",
        tier=ModelTier.PREMIUM,
        display_name="o3 (Reasoning)",
        pricing=ModelPricing(input_per_m=10.0, output_per_m=40.0),
        context_window=200_000,
        max_output_tokens=100_000,
        typical_latency_ms=8000,
        capabilities=frozenset({
            ModelCapability.REASONING, ModelCapability.CODE,
            ModelCapability.CHAT, ModelCapability.TOOL_USE,
        }),
        supports_tool_use=True,
        notes="Extended thinking — best for math, logic, complex code",
    ),

    # — Google ——————————————————————————————————————
    ModelProfile(
        model_id="gemini-2.5-pro",
        provider="google",
        tier=ModelTier.BALANCED,
        display_name="Gemini 2.5 Pro",
        pricing=ModelPricing(input_per_m=1.25, output_per_m=10.0),
        context_window=1_000_000,
        max_output_tokens=65_536,
        typical_latency_ms=1800,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CODE,
            ModelCapability.REASONING, ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT, ModelCapability.TOOL_USE,
        }),
        supports_tool_use=True,
        supports_vision=True,
        notes="1M context window — best for very long documents",
    ),
    ModelProfile(
        model_id="gemini-2.0-flash",
        provider="google",
        tier=ModelTier.FAST,
        display_name="Gemini 2.0 Flash",
        pricing=ModelPricing(input_per_m=0.075, output_per_m=0.30),
        context_window=1_000_000,
        max_output_tokens=8_192,
        typical_latency_ms=300,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.CLASSIFICATION,
            ModelCapability.EXTRACTION, ModelCapability.SUMMARIZATION,
            ModelCapability.VISION,
        }),
        supports_vision=True,
        notes="Cheapest option with massive context — great for bulk processing",
    ),

    # — Local / Self-Hosted —————————————————————————
    ModelProfile(
        model_id="codellama:13b",
        provider="local",
        tier=ModelTier.LOCAL,
        display_name="CodeLlama 13B",
        pricing=ModelPricing(input_per_m=0.0, output_per_m=0.0),
        context_window=16_384,
        max_output_tokens=4_096,
        typical_latency_ms=2000,
        capabilities=frozenset({
            ModelCapability.CODE, ModelCapability.CHAT,
        }),
        supports_streaming=True,
        notes="Self-hosted via Ollama — zero cost, full privacy",
    ),
    ModelProfile(
        model_id="llama3:8b",
        provider="local",
        tier=ModelTier.LOCAL,
        display_name="Llama 3 8B",
        pricing=ModelPricing(input_per_m=0.0, output_per_m=0.0),
        context_window=8_192,
        max_output_tokens=4_096,
        typical_latency_ms=1500,
        capabilities=frozenset({
            ModelCapability.CHAT, ModelCapability.SUMMARIZATION,
            ModelCapability.CLASSIFICATION,
        }),
        supports_streaming=True,
        notes="Self-hosted general purpose — good for data-sensitive workloads",
    ),
]


# — Model Registry ——————————————————————————————————


class ModelRegistry:
    """
    Singleton catalog of all known models.

    The registry knows about every model the platform *could* use.
    At runtime, it filters to only those whose provider is actually
    available (SDK installed + API key set).

    Usage::

        registry = ModelRegistry()
        # Get all FAST-tier models that are actually available
        fast_models = registry.get_available(ModelTier.FAST, available_providers={"anthropic", "google"})
        # -> [claude-haiku-4-5-20251001, gemini-2.0-flash]

        # Get cheapest model for a tier
        cheapest = registry.cheapest(ModelTier.FAST, available_providers={"anthropic"})
        # -> claude-haiku-4-5-20251001

        # Get best model with a specific capability
        code_model = registry.best_for_capability(ModelCapability.CODE, available_providers={"anthropic"})
        # -> claude-sonnet-4-20250514
    """

    def __init__(self) -> None:
        # model_id -> ModelProfile
        self._models: dict[str, ModelProfile] = {}
        # tier -> list of model_ids (sorted by cost ascending)
        self._by_tier: dict[ModelTier, list[str]] = {tier: [] for tier in ModelTier}
        # provider -> list of model_ids
        self._by_provider: dict[str, list[str]] = {}

        # Load built-in catalog
        for profile in _BUILTIN_MODELS:
            self.register(profile)

        logger.info(
            "ModelRegistry initialized: %d models across %d providers",
            len(self._models),
            len(self._by_provider),
        )

    def register(self, profile: ModelProfile) -> None:
        """
        Add or update a model in the registry.

        Models are automatically indexed by tier and provider for
        fast lookups during routing decisions.
        """
        self._models[profile.model_id] = profile

        # Index by tier (keep sorted by cost)
        tier_list = self._by_tier[profile.tier]
        if profile.model_id not in tier_list:
            tier_list.append(profile.model_id)
            tier_list.sort(key=lambda mid: self._models[mid].cost_per_1k_tokens)

        # Index by provider
        provider_list = self._by_provider.setdefault(profile.provider, [])
        if profile.model_id not in provider_list:
            provider_list.append(profile.model_id)

    def get(self, model_id: str) -> ModelProfile | None:
        """Look up a model by its ID."""
        return self._models.get(model_id)

    def get_available(
        self,
        tier: ModelTier,
        available_providers: set[str],
    ) -> list[ModelProfile]:
        """
        Get all models in a tier that have an available provider.

        Returns models sorted by cost (cheapest first).
        """
        return [
            self._models[mid]
            for mid in self._by_tier.get(tier, [])
            if self._models[mid].provider in available_providers
            and not self._models[mid].deprecated
        ]

    def cheapest(
        self,
        tier: ModelTier,
        available_providers: set[str],
    ) -> ModelProfile | None:
        """Get the cheapest available model in a tier."""
        available = self.get_available(tier, available_providers)
        return available[0] if available else None

    def fastest(
        self,
        tier: ModelTier,
        available_providers: set[str],
    ) -> ModelProfile | None:
        """Get the lowest-latency model in a tier."""
        available = self.get_available(tier, available_providers)
        if not available:
            return None
        return min(available, key=lambda m: m.typical_latency_ms)

    def best_for_capability(
        self,
        capability: ModelCapability,
        available_providers: set[str],
        prefer_tier: ModelTier | None = None,
    ) -> ModelProfile | None:
        """
        Find the best model with a specific capability.

        If prefer_tier is set, looks there first.  Otherwise searches
        from PREMIUM down to FAST.
        """
        search_order = (
            [prefer_tier] if prefer_tier
            else [ModelTier.PREMIUM, ModelTier.BALANCED, ModelTier.FAST, ModelTier.LOCAL]
        )
        for tier in search_order:
            for model in self.get_available(tier, available_providers):
                if capability in model.capabilities:
                    return model
        return None

    def all_models(self) -> list[ModelProfile]:
        """Return all registered models."""
        return list(self._models.values())

    def providers(self) -> list[str]:
        """Return all provider names with at least one model."""
        return sorted(self._by_provider.keys())

    def tier_summary(self, available_providers: set[str]) -> dict[str, Any]:
        """Summary of available models per tier — for dashboards."""
        summary = {}
        for tier in ModelTier:
            models = self.get_available(tier, available_providers)
            summary[tier.value] = {
                "count": len(models),
                "models": [m.model_id for m in models],
                "cheapest_per_1k": models[0].cost_per_1k_tokens if models else None,
            }
        return summary

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_models": len(self._models),
            "providers": self.providers(),
            "models": [m.to_dict() for m in self._models.values()],
        }
