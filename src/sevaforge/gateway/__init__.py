"""SevaForge AI Gateway — Prompt Assembly, Cache, Schema Gate, Multi-Router LLM."""

from .prompt_engine import PromptEngine
from .semantic_cache import SemanticCache
from .schema_gate import SchemaGate
from .ai_gateway import AIGateway
from .model_router import ModelRouter, ProviderResponse, ProviderError
from .model_registry import (
    ModelRegistry,
    ModelProfile,
    ModelPricing,
    ModelTier,
    ModelCapability,
)
from .routing_strategy import (
    TaskClassifier,
    TaskComplexity,
    RoutingDecision,
    CostOptimizedStrategy,
    QualityFirstStrategy,
    LatencyFirstStrategy,
    BalancedStrategy,
    CapabilityMatchedStrategy,
    get_strategy,
    available_strategies,
)

__all__ = [
    "PromptEngine",
    "SemanticCache",
    "SchemaGate",
    "AIGateway",
    "ModelRouter",
    "ProviderResponse",
    "ProviderError",
    "ModelRegistry",
    "ModelProfile",
    "ModelPricing",
    "ModelTier",
    "ModelCapability",
    "TaskClassifier",
    "TaskComplexity",
    "RoutingDecision",
    "CostOptimizedStrategy",
    "QualityFirstStrategy",
    "LatencyFirstStrategy",
    "BalancedStrategy",
    "CapabilityMatchedStrategy",
    "get_strategy",
    "available_strategies",
]
