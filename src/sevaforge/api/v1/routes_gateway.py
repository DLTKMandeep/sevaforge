"""
SevaForge API — Gateway Management Endpoints
Cache stats, template listing, and gateway administration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from sevaforge.api.app import get_gateway
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
