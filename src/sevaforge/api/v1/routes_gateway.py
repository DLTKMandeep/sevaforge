"""
SevaForge API — Gateway Management Endpoints
Cache stats, template listing, gateway administration, and multi-router LLM management.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sevaforge.api.app import get_gateway
from sevaforge.gateway.model_registry import ModelRegistry, ModelTier, ModelCapability
from sevaforge.gateway.model_router import ModelRouter
from sevaforge.gateway.routing_strategy import (
    TaskClassifier,
    TaskComplexity,
    available_strategies,
    get_strategy,
)
from sevaforge.models.schemas import CacheStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway")


# ── Cache Management ──────────────────────────────────────────────────


@router.get("/cache/stats", response_model=CacheStats)
async def cache_stats() -> CacheStats:
    """Return current cache statistics."""
    gateway = get_gateway()
    return gateway.cache.stats()


@router.post("/cache/clear")
async def cache_clear() -> dict:
    """Clear all cache entries."""
    gateway = get_gateway()
    count = gateway.cache.clear()
    logger.info("Cache cleared via API: %d entries removed", count)
    return {"cleared": count}


@router.post("/cache/evict")
async def cache_evict_expired() -> dict:
    """Evict expired cache entries."""
    gateway = get_gateway()
    count = gateway.cache.evict_expired()
    return {"evicted": count}


# ── Prompt Templates ──────────────────────────────────────────────────


@router.get("/templates")
async def list_templates() -> list[dict]:
    """List all loaded prompt templates."""
    gateway = get_gateway()
    return gateway.prompt_engine.list_templates()


@router.post("/templates/reload")
async def reload_templates() -> dict:
    """Hot-reload prompt templates from disk."""
    gateway = get_gateway()
    gateway.prompt_engine.reload()
    templates = gateway.prompt_engine.list_templates()
    logger.info("Templates reloaded via API: %d loaded", len(templates))
    return {"reloaded": len(templates), "templates": [t["template_id"] for t in templates]}


# ── Gateway Info ──────────────────────────────────────────────────────


@router.get("/info")
async def gateway_info() -> dict:
    """Return gateway configuration and status."""
    gateway = get_gateway()
    cache_stats = gateway.cache.stats()
    templates = gateway.prompt_engine.list_templates()

    return {
        "status": "operational",
        "components": {
            "prompt_engine": {
                "templates_loaded": len(templates),
                "template_ids": [t["template_id"] for t in templates],
            },
            "semantic_cache": {
                "enabled": cache_stats.enabled,
                "entries": cache_stats.total_entries,
                "hit_rate": f"{cache_stats.hit_rate:.1%}",
            },
            "schema_gate": {
                "max_retries": gateway.schema_gate._max_retries,
            },
        },
    }


# ── Multi-Router LLM Management ─────────────────────────────────────
#
# These endpoints expose the intelligent routing system: model registry,
# task classification, routing strategies, and router diagnostics.

_router_instance: ModelRouter | None = None


def _get_router() -> ModelRouter:
    """Get or create the shared ModelRouter instance."""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


# ── Request Models ──

class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to classify")


class StrategyChangeRequest(BaseModel):
    strategy: str = Field(..., description="Strategy name to switch to")
    quality_weight: float | None = Field(None, ge=0, le=1, description="Quality weight (balanced only)")
    cost_weight: float | None = Field(None, ge=0, le=1, description="Cost weight (balanced only)")
    latency_weight: float | None = Field(None, ge=0, le=1, description="Latency weight (balanced only)")


class RoutePreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to route")
    strategy: str | None = Field(None, description="Strategy override (uses default if not set)")


# ── Model Registry Endpoints ──

@router.get("/router/models")
async def list_models() -> dict[str, Any]:
    """List all models in the registry with their profiles."""
    mr = _get_router()
    return mr.model_registry.to_dict()


@router.get("/router/models/tiers")
async def model_tiers() -> dict[str, Any]:
    """Get models grouped by tier with availability status."""
    mr = _get_router()
    available = set(mr.available_providers) - {"mock"}
    if not available:
        available = {"mock"}
    return {
        "available_providers": sorted(available),
        "tiers": mr.model_registry.tier_summary(available),
    }


# ── Task Classification Endpoints ──

@router.post("/router/classify")
async def classify_task(body: ClassifyRequest) -> dict[str, Any]:
    """
    Classify input text complexity.

    Returns the complexity level (simple/medium/complex/expert)
    and the full scoring breakdown showing what factors contributed.
    """
    return TaskClassifier.classify_with_details(body.text)


# ── Routing Strategy Endpoints ──

@router.get("/router/strategies")
async def list_strategies() -> dict[str, Any]:
    """List all available routing strategies."""
    mr = _get_router()
    return {
        "active_strategy": mr.strategy_name,
        "available": available_strategies(),
        "descriptions": {
            "cost_optimized": "Cheapest model that can handle the task complexity",
            "quality_first": "Most capable model available regardless of cost",
            "latency_first": "Fastest-responding model for real-time UX",
            "balanced": "Weighted scoring across cost, quality, and latency",
            "capability_matched": "Routes based on task domain (code, creative, etc.)",
        },
    }


@router.post("/router/strategy")
async def change_strategy(body: StrategyChangeRequest) -> dict[str, Any]:
    """Switch the active routing strategy."""
    mr = _get_router()
    try:
        kwargs = {}
        if body.strategy == "balanced":
            if body.quality_weight is not None:
                kwargs["quality_weight"] = body.quality_weight
            if body.cost_weight is not None:
                kwargs["cost_weight"] = body.cost_weight
            if body.latency_weight is not None:
                kwargs["latency_weight"] = body.latency_weight
        mr.set_strategy(body.strategy, **kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "active_strategy": mr.strategy_name,
        "message": f"Strategy changed to '{body.strategy}'",
    }


@router.post("/router/preview")
async def preview_routing(body: RoutePreviewRequest) -> dict[str, Any]:
    """
    Preview which model would be selected without making an LLM call.

    Shows the full routing decision: complexity classification,
    strategy reasoning, selected model, and estimated cost.
    Useful for testing and tuning routing strategies.
    """
    mr = _get_router()

    # Classify
    classification = TaskClassifier.classify_with_details(body.text)
    complexity = TaskClassifier.classify(body.text)

    # Get available providers
    available = set(mr.available_providers) - {"mock"}
    if not available:
        available = {"mock"}

    # Apply strategy
    strategy_name = body.strategy or mr.strategy_name
    try:
        strategy = get_strategy(strategy_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        decision = strategy.select(
            complexity=complexity,
            registry=mr.model_registry,
            available_providers=available,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {
        "classification": classification,
        "routing_decision": decision.to_dict(),
        "strategy_used": strategy_name,
    }


# ── Router Diagnostics ──

@router.get("/router/info")
async def router_info() -> dict[str, Any]:
    """Full router status — strategy, registry, health, stats."""
    mr = _get_router()
    return mr.routing_info()


@router.get("/router/stats")
async def router_stats() -> dict[str, Any]:
    """Router call statistics."""
    mr = _get_router()
    return mr.stats.to_dict()


@router.get("/router/health")
async def router_health() -> dict[str, Any]:
    """Provider circuit breaker health status."""
    mr = _get_router()
    return mr.provider_health()
