"""
SevaForge API — Trust & Observability Layer Endpoints (Layer 6)
Content guardrails, OpenTelemetry tracing, and immutable audit trail.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sevaforge.trust import GuardrailsEngine, OTelManager, AuditTrail, AuditAction

router = APIRouter()

# ── Shared instances (lazy-initialized) ──────────────────────────────

_guardrails: GuardrailsEngine | None = None
_otel: OTelManager | None = None
_audit: AuditTrail | None = None


def get_guardrails() -> GuardrailsEngine:
    global _guardrails
    if _guardrails is None:
        _guardrails = GuardrailsEngine()
    return _guardrails


def get_otel() -> OTelManager:
    global _otel
    if _otel is None:
        _otel = OTelManager()
    return _otel


def get_audit() -> AuditTrail:
    global _audit
    if _audit is None:
        _audit = AuditTrail()
    return _audit


# ══════════════════════════════════════════════════════════════════════
# Guardrails Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/guardrails/check-input")
async def check_input(request: Request) -> dict:
    """Run input-side guardrail checks (PII, injection, toxic, policy)."""
    body = await request.json()
    text = body.get("text", "")
    context = body.get("context", {})

    if not text:
        raise HTTPException(400, "'text' is required")

    engine = get_guardrails()
    result = engine.check_input(text, context=context)
    return result.to_dict()


@router.post("/guardrails/check-output")
async def check_output(request: Request) -> dict:
    """Run output-side guardrail checks (data leak, PII, toxic, policy)."""
    body = await request.json()
    text = body.get("text", "")
    context = body.get("context", {})

    if not text:
        raise HTTPException(400, "'text' is required")

    engine = get_guardrails()
    result = engine.check_output(text, context=context)
    return result.to_dict()


@router.get("/guardrails/stats")
async def guardrails_stats() -> dict:
    """Return guardrails engine statistics."""
    return get_guardrails().stats()


# ══════════════════════════════════════════════════════════════════════
# OpenTelemetry Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/otel/start-span")
async def start_span(request: Request) -> dict:
    """Start a new trace span and return the span context."""
    body = await request.json()
    operation_name = body.get("operation_name", "")
    attributes = body.get("attributes", {})

    if not operation_name:
        raise HTTPException(400, "'operation_name' is required")

    otel = get_otel()
    span = otel.start_span(operation_name=operation_name, attributes=attributes)
    return span.to_dict()


@router.get("/otel/traces")
async def get_traces(limit: int = 100) -> list[dict]:
    """Retrieve recent traces with all their spans."""
    otel = get_otel()
    return otel.get_traces(limit=limit)


@router.get("/otel/metrics")
async def get_metrics() -> dict:
    """Return all recorded metrics (counters, gauges, histograms)."""
    return get_otel().get_metrics()


# ══════════════════════════════════════════════════════════════════════
# Audit Trail Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/audit/record")
async def record_audit(request: Request) -> dict:
    """Record an auditable action in the immutable audit trail."""
    body = await request.json()
    action_str = body.get("action", "")
    actor_id = body.get("actor_id", "")
    actor_type = body.get("actor_type", "user")

    if not action_str or not actor_id:
        raise HTTPException(400, "'action' and 'actor_id' are required")

    try:
        action = AuditAction(action_str)
    except ValueError:
        valid_actions = [a.value for a in AuditAction]
        raise HTTPException(400, f"Invalid action '{action_str}'. Valid: {valid_actions}")

    audit = get_audit()
    entry = audit.record(
        action=action,
        actor_id=actor_id,
        actor_type=actor_type,
        resource_type=body.get("resource_type", ""),
        resource_id=body.get("resource_id", ""),
        details=body.get("details", {}),
        outcome=body.get("outcome", "success"),
        tenant_id=body.get("tenant_id", "default"),
        ip_address=body.get("ip_address", ""),
        trace_id=body.get("trace_id", ""),
    )
    return entry.to_dict()


@router.get("/audit/query")
async def query_audit(
    actor_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query audit entries with optional filters."""
    audit = get_audit()

    action_enum = None
    if action:
        try:
            action_enum = AuditAction(action)
        except ValueError:
            raise HTTPException(400, f"Invalid action '{action}'")

    entries = audit.query(
        actor_id=actor_id,
        action=action_enum,
        resource_type=resource_type,
        tenant_id=tenant_id,
        limit=limit,
    )
    return [e.to_dict() for e in entries]


@router.get("/audit/{entry_id}")
async def get_audit_entry(entry_id: str) -> dict:
    """Retrieve a specific audit entry by ID."""
    audit = get_audit()
    entry = audit.get_entry(entry_id)
    if not entry:
        raise HTTPException(404, f"Audit entry '{entry_id}' not found")
    return entry.to_dict()


@router.get("/audit/{entry_id}/verify")
async def verify_audit_entry(entry_id: str) -> dict:
    """Verify the integrity of an audit entry's checksum."""
    audit = get_audit()
    entry = audit.get_entry(entry_id)
    if not entry:
        raise HTTPException(404, f"Audit entry '{entry_id}' not found")

    is_valid = audit.verify_integrity(entry)
    return {
        "entry_id": entry_id,
        "integrity_valid": is_valid,
        "checksum": entry.checksum,
    }


@router.get("/audit/stats")
async def audit_stats() -> dict:
    """Return audit trail statistics."""
    return get_audit().stats()
