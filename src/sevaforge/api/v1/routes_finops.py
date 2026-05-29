"""
SevaForge API — FinOps & Metering Layer Endpoints (Layer 9)
Per-request cost attribution, budget quotas, and spending controls.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sevaforge.finops import CostTracker, BudgetManager

router = APIRouter()

# ── Shared instances (lazy-initialized) ──────────────────────────────

_tracker: CostTracker | None = None
_budget: BudgetManager | None = None


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def get_budget() -> BudgetManager:
    global _budget
    if _budget is None:
        _budget = BudgetManager()
    return _budget


# ══════════════════════════════════════════════════════════════════════
# Usage Tracking Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/usage/record")
async def record_usage(request: Request) -> dict:
    """Record a single LLM usage event with cost attribution."""
    body = await request.json()

    agent_id = body.get("agent_id", "")
    user_id = body.get("user_id", "")
    tenant_id = body.get("tenant_id", "")
    model = body.get("model", "")
    input_tokens = body.get("input_tokens", 0)
    output_tokens = body.get("output_tokens", 0)

    if not model:
        raise HTTPException(400, "'model' is required")

    tracker = get_tracker()
    record = tracker.record_usage(
        agent_id=agent_id,
        user_id=user_id,
        tenant_id=tenant_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=body.get("latency_ms", 0.0),
        execution_id=body.get("execution_id", ""),
        trace_id=body.get("trace_id", ""),
        cached=body.get("cached", False),
        metadata=body.get("metadata"),
    )
    return record.to_dict()


@router.get("/usage/summary")
async def usage_summary(
    tenant_id: str | None = None,
    agent_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict:
    """Get an aggregated cost summary with optional filters."""
    from datetime import datetime

    tracker = get_tracker()

    st = datetime.fromisoformat(start_time) if start_time else None
    et = datetime.fromisoformat(end_time) if end_time else None

    summary = tracker.get_summary(
        tenant_id=tenant_id,
        agent_id=agent_id,
        start_time=st,
        end_time=et,
    )
    return summary.to_dict()


@router.get("/usage/history")
async def usage_history(
    tenant_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Get recent usage records, newest first."""
    tracker = get_tracker()
    records = tracker.get_usage_history(
        tenant_id=tenant_id,
        agent_id=agent_id,
        limit=limit,
    )
    return [r.to_dict() for r in records]


@router.get("/usage/top-consumers")
async def top_consumers(
    by: str = "tenant",
    limit: int = 10,
) -> list[dict]:
    """Return the top cost consumers ranked by total spend."""
    if by not in ("tenant", "agent", "user", "model"):
        raise HTTPException(400, "'by' must be one of: tenant, agent, user, model")

    tracker = get_tracker()
    results = tracker.get_top_consumers(by=by, limit=limit)
    return [
        {"identifier": identifier, "total_cost_usd": round(cost, 6)}
        for identifier, cost in results
    ]


@router.get("/usage/model-breakdown")
async def model_breakdown(tenant_id: str | None = None) -> dict:
    """Get per-model cost, request count, and token breakdowns."""
    tracker = get_tracker()
    return tracker.get_model_breakdown(tenant_id=tenant_id)


# ══════════════════════════════════════════════════════════════════════
# Pricing Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/pricing")
async def get_pricing() -> dict:
    """Return the current pricing table (per-1M-token rates)."""
    tracker = get_tracker()
    return tracker.get_pricing()


@router.post("/pricing")
async def update_pricing(request: Request) -> dict:
    """Update or add per-1M-token pricing for a model."""
    body = await request.json()
    model = body.get("model", "")
    input_price = body.get("input_price")
    output_price = body.get("output_price")

    if not model or input_price is None or output_price is None:
        raise HTTPException(400, "'model', 'input_price', and 'output_price' are required")

    tracker = get_tracker()
    tracker.update_pricing(model=model, input_price=input_price, output_price=output_price)
    return {
        "updated": True,
        "model": model,
        "input_price_per_1m": input_price,
        "output_price_per_1m": output_price,
    }


# ══════════════════════════════════════════════════════════════════════
# Budget Management Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/budget/quotas")
async def create_budget_quota(request: Request) -> dict:
    """Create a budget quota for a tenant."""
    body = await request.json()
    tenant_id = body.get("tenant_id", "")
    budget_limit_usd = body.get("budget_limit_usd", 0.0)

    if not tenant_id or budget_limit_usd <= 0:
        raise HTTPException(400, "'tenant_id' and positive 'budget_limit_usd' are required")

    budget = get_budget()
    quota = budget.create_quota(
        tenant_id=tenant_id,
        budget_limit_usd=budget_limit_usd,
        period=body.get("period", "monthly"),
        warning_threshold=body.get("warning_threshold", 0.80),
        critical_threshold=body.get("critical_threshold", 0.95),
        auto_throttle=body.get("auto_throttle", True),
        hard_limit=body.get("hard_limit", False),
        metadata=body.get("metadata"),
    )
    return quota.to_dict()


@router.get("/budget/quotas/{tenant_id}")
async def get_tenant_quotas(tenant_id: str) -> list[dict]:
    """Get all budget quotas for a tenant."""
    budget = get_budget()
    quotas = budget.get_tenant_quotas(tenant_id)
    return [q.to_dict() for q in quotas]


@router.post("/budget/check")
async def check_budget(request: Request) -> dict:
    """Pre-request budget check — determine if a request should proceed."""
    body = await request.json()
    tenant_id = body.get("tenant_id", "")
    estimated_cost = body.get("estimated_cost", 0.0)

    if not tenant_id:
        raise HTTPException(400, "'tenant_id' is required")

    budget = get_budget()
    result = budget.check_budget(tenant_id=tenant_id, estimated_cost=estimated_cost)
    return result.to_dict()


@router.post("/budget/spend")
async def record_spend(request: Request) -> dict:
    """Record actual spend against a tenant's budget quotas."""
    body = await request.json()
    tenant_id = body.get("tenant_id", "")
    amount_usd = body.get("amount_usd", 0.0)

    if not tenant_id or amount_usd <= 0:
        raise HTTPException(400, "'tenant_id' and positive 'amount_usd' are required")

    budget = get_budget()
    alerts = budget.record_spend(tenant_id=tenant_id, amount_usd=amount_usd)
    return {
        "recorded": True,
        "tenant_id": tenant_id,
        "amount_usd": amount_usd,
        "alerts_triggered": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
    }


@router.get("/budget/alerts")
async def get_budget_alerts(
    tenant_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Get recent budget alerts, newest first."""
    budget = get_budget()
    alerts = budget.get_alerts(tenant_id=tenant_id, limit=limit)
    return [a.to_dict() for a in alerts]


@router.get("/budget/report/{tenant_id}")
async def budget_report(tenant_id: str) -> dict:
    """Get a comprehensive budget report for a tenant."""
    budget = get_budget()
    return budget.get_budget_report(tenant_id)


# ══════════════════════════════════════════════════════════════════════
# FinOps Stats
# ══════════════════════════════════════════════════════════════════════


@router.get("/stats")
async def finops_stats() -> dict:
    """Return combined FinOps statistics (cost tracker + budget manager)."""
    return {
        "cost_tracker": get_tracker().stats(),
        "budget_manager": get_budget().stats(),
    }
