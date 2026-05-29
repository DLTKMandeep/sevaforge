"""
SevaForge API — Data Layer Endpoints (Layer 8)
PostgreSQL management, Redis operations, and event stream monitoring.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.data.postgres import PostgresManager
from sevaforge.data.redis_client import RedisManager
from sevaforge.data.event_stream import EventBus, Event, EventType

router = APIRouter()

# ── Shared instances ─────────────────────────────────────────────────

_postgres: PostgresManager | None = None
_redis: RedisManager | None = None
_event_bus: EventBus | None = None


def get_postgres() -> PostgresManager:
    global _postgres
    if _postgres is None:
        _postgres = PostgresManager()
        _postgres.initialize()
    return _postgres


def get_redis() -> RedisManager:
    global _redis
    if _redis is None:
        _redis = RedisManager()
    return _redis


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# ── Request Models ───────────────────────────────────────────────────


class InsertRecordRequest(BaseModel):
    data: dict[str, Any]
    record_id: str | None = None


class UpdateRecordRequest(BaseModel):
    updates: dict[str, Any]


class QueryRecordsRequest(BaseModel):
    filters: dict[str, Any] = {}
    limit: int = 100
    offset: int = 0
    sort_by: str | None = None
    sort_desc: bool = False


class SessionSetRequest(BaseModel):
    key: str
    field_name: str
    value: Any
    ttl: int | None = None


class RateLimitCheckRequest(BaseModel):
    key: str
    cost: int = 1


class PublishEventRequest(BaseModel):
    event_type: str = "custom"
    source: str = ""
    data: dict[str, Any] = {}
    correlation_id: str = ""
    tenant_id: str = "default"


# ══════════════════════════════════════════════════════════════════════
# PostgreSQL Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/db/health")
async def db_health() -> dict:
    """Check database health."""
    return get_postgres().health_check()


@router.get("/db/migrations")
async def db_migrations() -> dict:
    """Get migration status."""
    return get_postgres().migrations.status()


@router.post("/db/migrations/apply")
async def apply_migrations() -> dict:
    """Apply all pending migrations."""
    pg = get_postgres()
    applied = pg.migrations.apply_all()
    return {"applied": applied, "status": pg.migrations.status()}


@router.get("/db/pool/stats")
async def pool_stats() -> dict:
    """Get connection pool statistics."""
    return get_postgres().pool.stats()


@router.post("/db/pool/recycle")
async def recycle_pool() -> dict:
    """Recycle idle connections."""
    recycled = get_postgres().pool.recycle_idle()
    return {"recycled": recycled}


# ── Repository CRUD ──────────────────────────────────────────────────


@router.post("/db/{table_name}/records")
async def insert_record(table_name: str, req: InsertRecordRequest) -> dict:
    """Insert a record into a table."""
    repo = get_postgres().get_repository(table_name)
    rid = repo.insert(req.data, record_id=req.record_id)
    return {"inserted": True, "id": rid, "table": table_name}


@router.get("/db/{table_name}/records/{record_id}")
async def get_record(table_name: str, record_id: str) -> dict:
    repo = get_postgres().get_repository(table_name)
    record = repo.get(record_id)
    if not record:
        raise HTTPException(404, f"Record '{record_id}' not found in '{table_name}'")
    return record


@router.put("/db/{table_name}/records/{record_id}")
async def update_record(table_name: str, record_id: str, req: UpdateRecordRequest) -> dict:
    repo = get_postgres().get_repository(table_name)
    if not repo.update(record_id, req.updates):
        raise HTTPException(404, f"Record '{record_id}' not found in '{table_name}'")
    return {"updated": True, "id": record_id}


@router.delete("/db/{table_name}/records/{record_id}")
async def delete_record(table_name: str, record_id: str) -> dict:
    repo = get_postgres().get_repository(table_name)
    if not repo.delete(record_id):
        raise HTTPException(404, f"Record '{record_id}' not found in '{table_name}'")
    return {"deleted": True, "id": record_id}


@router.post("/db/{table_name}/query")
async def query_records(table_name: str, req: QueryRecordsRequest) -> dict:
    """Query records with filters and pagination."""
    repo = get_postgres().get_repository(table_name)
    records = repo.query(
        filters=req.filters,
        limit=req.limit,
        offset=req.offset,
        sort_by=req.sort_by,
        sort_desc=req.sort_desc,
    )
    return {
        "table": table_name,
        "total": repo.count(req.filters),
        "records": records,
    }


@router.get("/db/{table_name}/stats")
async def table_stats(table_name: str) -> dict:
    repo = get_postgres().get_repository(table_name)
    return repo.stats()


# ══════════════════════════════════════════════════════════════════════
# Redis Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/redis/health")
async def redis_health() -> dict:
    """Check Redis health."""
    return get_redis().health_check()


@router.post("/redis/sessions/set")
async def redis_session_set(req: SessionSetRequest) -> dict:
    """Set a field in a session hash."""
    redis = get_redis()
    redis.sessions.set(req.key, req.field_name, req.value, ttl=req.ttl)
    return {"set": True, "key": req.key, "field": req.field_name}


@router.get("/redis/sessions/{key}")
async def redis_session_get(key: str) -> dict:
    """Get all fields of a session hash."""
    redis = get_redis()
    data = redis.sessions.get_all(key)
    return {"key": key, "data": data, "exists": bool(data)}


@router.delete("/redis/sessions/{key}")
async def redis_session_delete(key: str) -> dict:
    redis = get_redis()
    deleted = redis.sessions.delete(key)
    return {"deleted": deleted, "key": key}


@router.post("/redis/rate-limit/check")
async def check_rate_limit(req: RateLimitCheckRequest) -> dict:
    """Check if a request is allowed under rate limiting."""
    redis = get_redis()
    allowed = redis.rate_limiter.allow(req.key, cost=req.cost)
    remaining = redis.rate_limiter.remaining(req.key)
    return {
        "key": req.key,
        "allowed": allowed,
        "remaining_tokens": remaining,
    }


@router.get("/redis/rate-limit/stats")
async def rate_limit_stats() -> dict:
    return get_redis().rate_limiter.stats()


@router.post("/redis/flush")
async def redis_flush() -> dict:
    """Flush all Redis data."""
    return get_redis().flush_all()


# ══════════════════════════════════════════════════════════════════════
# Event Stream Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/events/emit")
async def emit_event(req: PublishEventRequest) -> dict:
    """Emit an event to the event bus."""
    bus = get_event_bus()
    event = Event(
        event_type=EventType(req.event_type),
        source=req.source,
        data=req.data,
        correlation_id=req.correlation_id,
        tenant_id=req.tenant_id,
    )
    delivered = bus.emit(event)
    return {
        "event_id": event.event_id,
        "event_type": req.event_type,
        "delivered_to": delivered,
    }


@router.get("/events/history")
async def event_history(
    event_type: str | None = None,
    source: str | None = None,
    correlation_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query event history."""
    bus = get_event_bus()
    etype = EventType(event_type) if event_type else None
    events = bus.get_history(
        event_type=etype,
        source=source,
        correlation_id=correlation_id,
        limit=limit,
    )
    return [e.to_dict() for e in events]


@router.get("/events/subscriptions")
async def event_subscriptions() -> list[dict]:
    return get_event_bus().subscriptions()


@router.get("/events/dead-letters")
async def dead_letters(limit: int = 50) -> list[dict]:
    return get_event_bus().dead_letters(limit=limit)


@router.get("/events/stats")
async def event_stats() -> dict:
    return get_event_bus().stats()
