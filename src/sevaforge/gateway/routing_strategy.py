"""
SevaForge Routing Strategy -- Intelligent Model Selection

This module answers the question: "Given this user request, which LLM
model should handle it?"

Three components work together:

1. **TaskClassifier** -- Examines the input text and determines its
   complexity level (SIMPLE -> EXPERT).  This is a fast heuristic
   analysis, NOT an LLM call -- it runs in <1ms.

2. **RoutingStrategy** -- A policy that maps (complexity, available models)
   to a specific model choice.  Five built-in strategies:
   - CostOptimized:     Cheapest model that can handle the complexity
   - QualityFirst:      Best model available, regardless of cost
   - LatencyFirst:      Fastest-responding model
   - Balanced:          Weighted scoring across cost, quality, and speed
   - CapabilityMatched: Matches task domain (code, creative, etc.) to
                        the model with the best capability fit

3. **RoutingDecision** -- The output: which model to use, why it was
   chosen, and the estimated cost.  This gets attached to the
   ProviderResponse so you can audit routing decisions.

Example flow:
    input = "Review this Python function for security vulnerabilities"
    complexity = TaskClassifier.classify(input)        # -> MEDIUM
    strategy  = CostOptimizedStrategy()
    decision  = strategy.select(complexity, registry)  # -> claude-haiku (cheap enough for MEDIUM)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from .model_registry import (
    ModelCapability,
    ModelProfile,
    ModelRegistry,
    ModelTier,
)

logger = logging.getLogger(__name__)


# -- Task Complexity --


class TaskComplexity(str, Enum):
    """
    How hard is this task for an LLM?

    This drives tier selection:
        SIMPLE  -> Tier 1 (Fast)     -- classification, extraction, short Q&A
        MEDIUM  -> Tier 2 (Balanced) -- summarisation, code review, writing
        COMPLEX -> Tier 3 (Premium)  -- architecture, multi-step reasoning
        EXPERT  -> Tier 3 (Premium)  -- novel research, creative strategy
    """
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"
    EXPERT = "expert"


# -- Routing Decision --


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """
    The result of a routing strategy's model selection.

    Attached to every LLM response so you can audit why a particular
    model was chosen and how much it cost.
    """
    model_id: str                     # e.g. "claude-sonnet-4-20250514"
    provider: str                     # e.g. "anthropic"
    tier: ModelTier                   # which tier was selected
    strategy: str                     # which strategy made the decision
    complexity: TaskComplexity        # classified complexity of the input
    reason: str                       # human-readable explanation
    estimated_cost_per_1k: float      # blended cost per 1K tokens
    alternatives_considered: int = 0  # how many models were evaluated

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "tier": self.tier.value,
            "strategy": self.strategy,
            "complexity": self.complexity.value,
            "reason": self.reason,
            "estimated_cost_per_1k": round(self.estimated_cost_per_1k, 6),
            "alternatives_considered": self.alternatives_considered,
        }


# -- Task Classifier --


class TaskClassifier:
    """
    Classifies input text into a complexity level using fast heuristics.

    This is NOT an LLM call -- it's pattern matching and scoring that
    runs in microseconds.  The goal is "good enough" classification
    to pick the right model tier, not perfect accuracy.

    Scoring factors:
        1. Token count      -- Longer inputs tend to be more complex
        2. Complexity keywords -- Words like "architect", "design", "analyze"
                                 signal higher complexity
        3. Code presence    -- Code blocks suggest technical tasks
        4. Question depth   -- Multi-part questions score higher
        5. Domain signals   -- Security audit > simple greeting

    The classifier is intentionally conservative: when in doubt, it
    rounds UP to a higher complexity.  It's cheaper to over-provision
    (use Sonnet when Haiku would suffice) than to under-provision
    (use Haiku for a task that needs Sonnet and get a bad result).
    """

    # -- Keyword patterns that signal complexity --

    _SIMPLE_PATTERNS = re.compile(
        r"\b(hello|hi|hey|thanks|yes|no|ok|what is|define|list|"
        r"translate|convert|format|classify|label|extract|"
        r"summarize this sentence|short summary)\b",
        re.IGNORECASE,
    )

    _MEDIUM_PATTERNS = re.compile(
        r"\b(explain|compare|review|analyze|summarize|rewrite|"
        r"improve|refactor|debug|fix|test|implement|create|"
        r"write a function|code review|pull request|documentation|"
        r"unit test|integration test)\b",
        re.IGNORECASE,
    )

    _COMPLEX_PATTERNS = re.compile(
        r"\b(architect|design system|security audit|threat model|"
        r"performance optimization|scalability|distributed|"
        r"migration strategy|cost analysis|trade-?offs?|"
        r"end.to.end|multi.step|comprehensive|in.depth|"
        r"production.ready|enterprise|compliance|regulatory)\b",
        re.IGNORECASE,
    )

    _EXPERT_PATTERNS = re.compile(
        r"\b(novel approach|research|breakthrough|state.of.the.art|"
        r"theoretical|proof|formal verification|zero.day|"
        r"cryptographic|consensus algorithm|distributed consensus|"
        r"machine learning model|train|fine.tune|"
        r"patent|invention|original)\b",
        re.IGNORECASE,
    )

    # Code block detection
    _CODE_BLOCK = re.compile(r"```[\s\S]*?```|^( {4}|\t)\S", re.MULTILINE)

    @classmethod
    def classify(cls, text: str) -> TaskComplexity:
        """
        Classify text complexity.  Returns the highest matching level.

        Scoring:
            - Start at 0 points
            - Token count adds 0-3 points
            - Pattern matches add points per tier
            - Code presence adds 1 point
            - Multi-question adds 1 point
            - Map total score -> complexity level
        """
        if not text or not text.strip():
            return TaskComplexity.SIMPLE

        score = 0.0

        # -- Factor 1: Length (proxy for token count) --
        # ~4 chars per token is a rough approximation
        approx_tokens = len(text) // 4
        if approx_tokens > 2000:
            score += 3.0   # Very long input -- likely complex
        elif approx_tokens > 500:
            score += 2.0
        elif approx_tokens > 100:
            score += 1.0
        # Short inputs (< 100 tokens) add nothing

        # -- Factor 2: Keyword patterns --
        expert_hits = len(cls._EXPERT_PATTERNS.findall(text))
        complex_hits = len(cls._COMPLEX_PATTERNS.findall(text))
        medium_hits = len(cls._MEDIUM_PATTERNS.findall(text))
        simple_hits = len(cls._SIMPLE_PATTERNS.findall(text))

        score += expert_hits * 4.0
        score += complex_hits * 3.0
        score += medium_hits * 1.5
        score += simple_hits * 0.2  # Simple keywords slightly bias toward simple

        # -- Factor 3: Code presence --
        if cls._CODE_BLOCK.search(text):
            score += 1.5  # Code tasks are at least medium

        # -- Factor 4: Multi-question detection --
        question_marks = text.count("?")
        if question_marks >= 3:
            score += 2.0  # Multiple questions = more complex
        elif question_marks >= 2:
            score += 1.0

        # -- Factor 5: List/enumeration detection --
        numbered_items = len(re.findall(r"^\s*\d+[.)]\s", text, re.MULTILINE))
        if numbered_items >= 4:
            score += 1.5  # Multi-step instructions

        # -- Map score to complexity --
        if score >= 8.0:
            result = TaskComplexity.EXPERT
        elif score >= 5.0:
            result = TaskComplexity.COMPLEX
        elif score >= 2.0:
            result = TaskComplexity.MEDIUM
        else:
            result = TaskComplexity.SIMPLE

        logger.debug(
            "TaskClassifier: score=%.1f -> %s (tokens~%d, expert=%d, complex=%d, medium=%d)",
            score, result.value, approx_tokens, expert_hits, complex_hits, medium_hits,
        )
        return result

    @classmethod
    def classify_with_details(cls, text: str) -> dict[str, Any]:
        """Classify and return full scoring breakdown -- useful for debugging."""
        approx_tokens = len(text) // 4 if text else 0
        expert_hits = len(cls._EXPERT_PATTERNS.findall(text)) if text else 0
        complex_hits = len(cls._COMPLEX_PATTERNS.findall(text)) if text else 0
        medium_hits = len(cls._MEDIUM_PATTERNS.findall(text)) if text else 0
        simple_hits = len(cls._SIMPLE_PATTERNS.findall(text)) if text else 0
        has_code = bool(cls._CODE_BLOCK.search(text)) if text else False
        question_marks = text.count("?") if text else 0

        complexity = cls.classify(text)

        return {
            "complexity": complexity.value,
            "approx_tokens": approx_tokens,
            "pattern_hits": {
                "expert": expert_hits,
                "complex": complex_hits,
                "medium": medium_hits,
                "simple": simple_hits,
            },
            "has_code": has_code,
            "question_count": question_marks,
        }


# -- Routing Strategy Protocol --


class RoutingStrategy(Protocol):
    """
    Interface that all routing strategies must implement.

    A strategy takes the task complexity and the available models,
    then returns a RoutingDecision saying which model to use.
    """

    @property
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
    ) -> RoutingDecision:
        """
        Select the best model for the given complexity.

        Args:
            complexity:             Classified task complexity.
            registry:               Model catalog to choose from.
            available_providers:    Set of providers with valid API keys.
            preferred_capabilities: Optional capability hints from the agent
                                    (e.g., CODE for a code review agent).

        Returns:
            RoutingDecision with the chosen model and reasoning.
        """
        ...


# -- Complexity -> Tier Mapping --


_COMPLEXITY_TO_TIER: dict[TaskComplexity, ModelTier] = {
    TaskComplexity.SIMPLE: ModelTier.FAST,
    TaskComplexity.MEDIUM: ModelTier.BALANCED,
    TaskComplexity.COMPLEX: ModelTier.PREMIUM,
    TaskComplexity.EXPERT: ModelTier.PREMIUM,
}


def _fallback_model(
    registry: ModelRegistry,
    available_providers: set[str],
) -> ModelProfile | None:
    """Find ANY available model as a last resort."""
    for tier in [ModelTier.FAST, ModelTier.BALANCED, ModelTier.PREMIUM, ModelTier.LOCAL]:
        models = registry.get_available(tier, available_providers)
        if models:
            return models[0]
    return None


# -- Strategy 1: Cost Optimized --


class CostOptimizedStrategy:
    """
    Always picks the CHEAPEST model that can handle the task.

    For a SIMPLE task, this means Haiku or Flash ($0.08-$0.80/M).
    For COMPLEX, it still picks the cheapest PREMIUM model.

    Use when: You're processing high volume and want to minimise spend.
    Trade-off: May sacrifice quality on borderline tasks.
    """

    name = "cost_optimized"

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
    ) -> RoutingDecision:
        target_tier = _COMPLEXITY_TO_TIER[complexity]
        model = registry.cheapest(target_tier, available_providers)

        # Fallback: try lower tiers
        if model is None:
            for tier in ModelTier:
                model = registry.cheapest(tier, available_providers)
                if model:
                    break

        if model is None:
            raise ValueError("No models available in any tier")

        return RoutingDecision(
            model_id=model.model_id,
            provider=model.provider,
            tier=model.tier,
            strategy=self.name,
            complexity=complexity,
            reason=f"Cheapest {target_tier.value}-tier model at ${model.cost_per_1k_tokens:.4f}/1K tokens",
            estimated_cost_per_1k=model.cost_per_1k_tokens,
            alternatives_considered=len(registry.get_available(target_tier, available_providers)),
        )


# -- Strategy 2: Quality First --


class QualityFirstStrategy:
    """
    Always picks the MOST CAPABLE model available.

    Ignores cost entirely -- routes everything to Opus / o3 / Gemini Pro.
    Falls back to lower tiers only if premium isn't available.

    Use when: Accuracy matters more than cost (legal, medical, security).
    Trade-off: 10-60x more expensive than cost-optimized.
    """

    name = "quality_first"

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
    ) -> RoutingDecision:
        # Always try premium first, then balanced, then fast
        for tier in [ModelTier.PREMIUM, ModelTier.BALANCED, ModelTier.FAST]:
            models = registry.get_available(tier, available_providers)
            if models:
                # Pick the most expensive (= most capable) in the tier
                model = max(models, key=lambda m: m.cost_per_1k_tokens)
                return RoutingDecision(
                    model_id=model.model_id,
                    provider=model.provider,
                    tier=model.tier,
                    strategy=self.name,
                    complexity=complexity,
                    reason=f"Highest-capability model: {model.display_name}",
                    estimated_cost_per_1k=model.cost_per_1k_tokens,
                    alternatives_considered=len(models),
                )

        raise ValueError("No models available in any tier")


# -- Strategy 3: Latency First --


class LatencyFirstStrategy:
    """
    Picks the FASTEST-responding model available.

    Good for real-time UX where users are waiting (chat, autocomplete).
    Rounds up to a higher tier only for COMPLEX/EXPERT tasks.

    Use when: Response time matters more than cost or quality.
    Trade-off: May pick a less capable model for complex tasks.
    """

    name = "latency_first"

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
    ) -> RoutingDecision:
        # For simple/medium, always use fast tier
        # For complex/expert, use balanced (premium is too slow)
        if complexity in (TaskComplexity.SIMPLE, TaskComplexity.MEDIUM):
            target_tier = ModelTier.FAST
        else:
            target_tier = ModelTier.BALANCED

        model = registry.fastest(target_tier, available_providers)

        # Fallback to any fast model
        if model is None:
            model = registry.fastest(ModelTier.FAST, available_providers)
        if model is None:
            fb = _fallback_model(registry, available_providers)
            if fb is None:
                raise ValueError("No models available")
            model = fb

        return RoutingDecision(
            model_id=model.model_id,
            provider=model.provider,
            tier=model.tier,
            strategy=self.name,
            complexity=complexity,
            reason=f"Fastest available: {model.display_name} (~{model.typical_latency_ms}ms)",
            estimated_cost_per_1k=model.cost_per_1k_tokens,
            alternatives_considered=len(registry.get_available(target_tier, available_providers)),
        )


# -- Strategy 4: Balanced --


class BalancedStrategy:
    """
    Weighted scoring across cost, quality (tier), and latency.

    Each model gets a score:
        score = (quality_weight * quality_score)
              + (cost_weight    * cost_score)
              + (latency_weight * latency_score)

    Where each sub-score is normalised 0-1 within the candidate set.

    Default weights: quality=0.4, cost=0.35, latency=0.25
    These can be tuned per-tenant in the platform config.

    Use when: You want a reasonable default that doesn't over-optimise
    for any single dimension.
    """

    name = "balanced"

    def __init__(
        self,
        quality_weight: float = 0.4,
        cost_weight: float = 0.35,
        latency_weight: float = 0.25,
    ) -> None:
        total = quality_weight + cost_weight + latency_weight
        self._quality_w = quality_weight / total
        self._cost_w = cost_weight / total
        self._latency_w = latency_weight / total

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
    ) -> RoutingDecision:
        # Collect candidate models from appropriate tiers
        target_tier = _COMPLEXITY_TO_TIER[complexity]

        # Include target tier and one tier above/below for more options
        candidate_tiers = {target_tier}
        tier_order = [ModelTier.FAST, ModelTier.BALANCED, ModelTier.PREMIUM]
        idx = tier_order.index(target_tier) if target_tier in tier_order else 1
        if idx > 0:
            candidate_tiers.add(tier_order[idx - 1])
        if idx < len(tier_order) - 1:
            candidate_tiers.add(tier_order[idx + 1])

        candidates: list[ModelProfile] = []
        for tier in candidate_tiers:
            candidates.extend(registry.get_available(tier, available_providers))

        if not candidates:
            # Last resort: any available model
            fb = _fallback_model(registry, available_providers)
            if fb is None:
                raise ValueError("No models available")
            candidates = [fb]

        # -- Score each candidate --
        # Quality score: higher tier = higher quality
        tier_quality = {
            ModelTier.LOCAL: 0.2,
            ModelTier.FAST: 0.4,
            ModelTier.BALANCED: 0.7,
            ModelTier.PREMIUM: 1.0,
        }

        # Normalise cost and latency across candidates
        costs = [m.cost_per_1k_tokens for m in candidates]
        max_cost = max(costs) if costs else 1.0
        latencies = [m.typical_latency_ms for m in candidates]
        max_latency = max(latencies) if latencies else 1.0

        best_model = candidates[0]
        best_score = -1.0

        for model in candidates:
            quality_score = tier_quality.get(model.tier, 0.5)
            # Invert cost: cheaper = higher score
            cost_score = 1.0 - (model.cost_per_1k_tokens / max_cost) if max_cost > 0 else 1.0
            # Invert latency: faster = higher score
            latency_score = 1.0 - (model.typical_latency_ms / max_latency) if max_latency > 0 else 1.0

            total = (
                self._quality_w * quality_score
                + self._cost_w * cost_score
                + self._latency_w * latency_score
            )

            if total > best_score:
                best_score = total
                best_model = model

        return RoutingDecision(
            model_id=best_model.model_id,
            provider=best_model.provider,
            tier=best_model.tier,
            strategy=self.name,
            complexity=complexity,
            reason=(
                f"Best balanced score ({best_score:.2f}) -- "
                f"quality={tier_quality.get(best_model.tier, 0):.1f}, "
                f"cost=${best_model.cost_per_1k_tokens:.4f}/1K"
            ),
            estimated_cost_per_1k=best_model.cost_per_1k_tokens,
            alternatives_considered=len(candidates),
        )


# -- Strategy 5: Capability Matched --


class CapabilityMatchedStrategy:
    """
    Routes based on WHAT the task is, not just how complex it is.

    Detects the task domain from keywords:
        - Code-related   -> model with CODE capability
        - Creative writing -> model with CREATIVE capability
        - Data extraction -> model with EXTRACTION capability

    Then picks the best model in the appropriate tier that has
    that capability.

    Use when: You have specialised workloads and want the model
    that's best at that specific type of task.
    """

    name = "capability_matched"

    # Domain -> required capability mapping
    _DOMAIN_PATTERNS: list[tuple[re.Pattern[str], ModelCapability]] = [
        (re.compile(r"\b(code|function|class|bug|refactor|implement|python|javascript|typescript|rust|go|java)\b", re.I), ModelCapability.CODE),
        (re.compile(r"\b(security|vulnerability|CVE|OWASP|threat|exploit|injection|XSS|CSRF)\b", re.I), ModelCapability.CODE),
        (re.compile(r"\b(creative|story|poem|write|essay|blog|article|narrative)\b", re.I), ModelCapability.CREATIVE),
        (re.compile(r"\b(extract|parse|scrape|structure|JSON|CSV|table|data)\b", re.I), ModelCapability.EXTRACTION),
        (re.compile(r"\b(classify|categorize|label|sentiment|detect|filter)\b", re.I), ModelCapability.CLASSIFICATION),
        (re.compile(r"\b(summarize|summarise|TLDR|brief|recap|digest|synopsis)\b", re.I), ModelCapability.SUMMARIZATION),
        (re.compile(r"\b(reason|prove|logic|math|calculate|equation|theorem)\b", re.I), ModelCapability.REASONING),
        (re.compile(r"\b(image|picture|photo|screenshot|diagram|visual)\b", re.I), ModelCapability.VISION),
    ]

    def _detect_capability(self, text: str) -> ModelCapability:
        """Detect the primary capability needed from the input text."""
        scores: dict[ModelCapability, int] = {}
        for pattern, capability in self._DOMAIN_PATTERNS:
            hits = len(pattern.findall(text))
            if hits:
                scores[capability] = scores.get(capability, 0) + hits

        if scores:
            return max(scores, key=lambda c: scores[c])
        return ModelCapability.CHAT  # Default: general chat

    def select(
        self,
        complexity: TaskComplexity,
        registry: ModelRegistry,
        available_providers: set[str],
        *,
        preferred_capabilities: frozenset[ModelCapability] | None = None,
        input_text: str = "",
    ) -> RoutingDecision:
        # Determine required capability
        if preferred_capabilities:
            # Agent told us what it needs
            primary_cap = next(iter(preferred_capabilities))
        elif input_text:
            primary_cap = self._detect_capability(input_text)
        else:
            primary_cap = ModelCapability.CHAT

        target_tier = _COMPLEXITY_TO_TIER[complexity]

        # Find best model with this capability at the right tier
        model = registry.best_for_capability(
            primary_cap,
            available_providers,
            prefer_tier=target_tier,
        )

        # Fallback: any model in the target tier
        if model is None:
            model = registry.cheapest(target_tier, available_providers)
        if model is None:
            fb = _fallback_model(registry, available_providers)
            if fb is None:
                raise ValueError("No models available")
            model = fb

        return RoutingDecision(
            model_id=model.model_id,
            provider=model.provider,
            tier=model.tier,
            strategy=self.name,
            complexity=complexity,
            reason=f"Best {primary_cap.value} model: {model.display_name}",
            estimated_cost_per_1k=model.cost_per_1k_tokens,
            alternatives_considered=len(registry.get_available(target_tier, available_providers)),
        )


# -- Strategy Factory --

_STRATEGY_REGISTRY: dict[str, type] = {
    "cost_optimized": CostOptimizedStrategy,
    "quality_first": QualityFirstStrategy,
    "latency_first": LatencyFirstStrategy,
    "balanced": BalancedStrategy,
    "capability_matched": CapabilityMatchedStrategy,
}


def get_strategy(name: str, **kwargs: Any) -> Any:
    """
    Factory function to get a routing strategy by name.

    Args:
        name: One of: cost_optimized, quality_first, latency_first,
              balanced, capability_matched
        **kwargs: Strategy-specific parameters (e.g., weights for balanced)

    Returns:
        An instance of the requested strategy.
    """
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        available = ", ".join(sorted(_STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return cls(**kwargs)


def available_strategies() -> list[str]:
    """List all registered strategy names."""
    return sorted(_STRATEGY_REGISTRY.keys())
