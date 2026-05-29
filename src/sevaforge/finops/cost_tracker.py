"""
SevaForge FinOps — Cost Tracker

Per-request cost attribution and rollup engine.
Tracks every LLM call with full dimensional metadata (agent, user, tenant,
model) and produces cost summaries, breakdowns, and monthly projections.

Architecture:
    record_usage() → UsageRecord  (immutable event)
    get_summary()  → CostSummary  (aggregated rollup)
    get_top_consumers() / get_model_breakdown() → analytics views

In-memory storage with configurable max_records for development.
Designed for drop-in replacement with a persistent backend (Postgres, ClickHouse).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class UsageRecord:
    """Immutable record of a single LLM invocation and its cost."""

    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Dimensional keys
    agent_id: str = ""
    user_id: str = ""
    tenant_id: str = ""

    # Model & token usage
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0

    # Cost & performance
    cost_usd: float = 0.0
    latency_ms: float = 0.0

    # Correlation
    execution_id: str = ""
    trace_id: str = ""

    # Flags
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "execution_id": self.execution_id,
            "trace_id": self.trace_id,
            "cached": self.cached,
            "metadata": self.metadata,
        }


@dataclass
class CostSummary:
    """Aggregated cost summary over a time window."""

    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)

    total_cost_usd: float = 0.0
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    avg_cost_per_request: float = 0.0
    avg_latency_ms: float = 0.0

    # Breakdowns
    by_model: dict[str, float] = field(default_factory=dict)
    by_agent: dict[str, float] = field(default_factory=dict)
    by_tenant: dict[str, float] = field(default_factory=dict)

    # Cache efficiency
    cache_hit_rate: float = 0.0
    cache_savings_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "avg_cost_per_request": round(self.avg_cost_per_request, 6),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "by_model": {k: round(v, 6) for k, v in self.by_model.items()},
            "by_agent": {k: round(v, 6) for k, v in self.by_agent.items()},
            "by_tenant": {k: round(v, 6) for k, v in self.by_tenant.items()},
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "cache_savings_usd": round(self.cache_savings_usd, 6),
        }


# ── Pricing Table ────────────────────────────────────────────────────

# Per-1M-token pricing (USD).  Kept as a module-level default so that
# CostTracker instances start with sane defaults but can be updated at
# runtime via update_pricing().

DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-opus-4-20250514":       {"input": 15.0,  "output": 75.0},
    "claude-sonnet-4-20250514":     {"input": 3.0,   "output": 15.0},
    "claude-haiku-4-5-20251001":    {"input": 0.80,  "output": 4.0},
    # OpenAI
    "gpt-4o":                       {"input": 2.50,  "output": 10.0},
    "gpt-4o-mini":                  {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":                  {"input": 10.0,  "output": 30.0},
    "o3-mini":                      {"input": 1.10,  "output": 4.40},
    # Google
    "gemini-2.0-flash":             {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro":               {"input": 1.25,  "output": 10.0},
    "gemini-2.5-flash":             {"input": 0.15,  "output": 0.60},
    # Meta (self-hosted reference pricing)
    "llama-3.3-70b":                {"input": 0.40,  "output": 0.40},
    "llama-4-scout":                {"input": 0.17,  "output": 0.30},
    # Mistral
    "mistral-large":                {"input": 2.0,   "output": 6.0},
    "mistral-small":                {"input": 0.10,  "output": 0.30},
}

# Fallback rate when a model is not in the pricing table.
_FALLBACK_RATE: dict[str, float] = {"input": 3.0, "output": 15.0}


# ── Cost Tracker ─────────────────────────────────────────────────────


class CostTracker:
    """
    Per-request cost attribution and analytics engine.

    Thread-safe in-memory store with configurable capacity.
    Supports dimensional roll-ups (by model, agent, tenant) and
    monthly cost projection based on recent usage velocity.

    Usage:
        tracker = CostTracker()
        record = tracker.record_usage(
            agent_id="code-review",
            user_id="u-123",
            tenant_id="t-acme",
            model="claude-sonnet-4-20250514",
            input_tokens=1500,
            output_tokens=400,
        )
        summary = tracker.get_summary(tenant_id="t-acme")
    """

    def __init__(self, max_records: int = 100_000) -> None:
        self._max_records = max_records
        self._records: list[UsageRecord] = []
        self._pricing: dict[str, dict[str, float]] = {
            k: dict(v) for k, v in DEFAULT_PRICING.items()
        }
        self._lock = threading.Lock()

        # Observability stats
        self._stats = {
            "total_tracked": 0,
            "total_cost": 0.0,
            "records_count": 0,
        }

    # ── Core API ─────────────────────────────────────────────────────

    def record_usage(
        self,
        agent_id: str,
        user_id: str,
        tenant_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float = 0.0,
        execution_id: str = "",
        trace_id: str = "",
        cached: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """
        Record a single LLM usage event and compute its cost.

        For cached responses the cost is recorded as zero; the uncached
        equivalent cost is tracked separately for cache-savings analytics.

        Returns:
            The immutable UsageRecord with computed cost_usd.
        """
        cost = 0.0 if cached else self.calculate_cost(model, input_tokens, output_tokens)

        record = UsageRecord(
            agent_id=agent_id,
            user_id=user_id,
            tenant_id=tenant_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            execution_id=execution_id,
            trace_id=trace_id,
            cached=cached,
            metadata=metadata or {},
        )

        with self._lock:
            self._records.append(record)
            self._stats["total_tracked"] += 1
            self._stats["total_cost"] += cost
            self._stats["records_count"] = len(self._records)

            # Evict oldest records when capacity is exceeded
            if len(self._records) > self._max_records:
                overflow = len(self._records) - self._max_records
                self._records = self._records[overflow:]
                self._stats["records_count"] = len(self._records)

        logger.debug(
            "Recorded usage: agent=%s tenant=%s model=%s cost=$%.6f cached=%s",
            agent_id,
            tenant_id,
            model,
            cost,
            cached,
        )
        return record

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate the USD cost for a given model and token counts.

        Uses the internal pricing table; falls back to a conservative
        default rate for unknown models.
        """
        rates = self._pricing.get(model, _FALLBACK_RATE)
        return (
            input_tokens * rates["input"] + output_tokens * rates["output"]
        ) / 1_000_000

    # ── Queries ──────────────────────────────────────────────────────

    def get_summary(
        self,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> CostSummary:
        """
        Build an aggregated cost summary, optionally filtered by
        tenant, agent, and/or time window.
        """
        filtered = self._filter_records(tenant_id, agent_id, start_time, end_time)
        if not filtered:
            now = datetime.utcnow()
            return CostSummary(period_start=start_time or now, period_end=end_time or now)

        total_cost = 0.0
        total_input = 0
        total_output = 0
        total_latency = 0.0
        cached_count = 0
        by_model: dict[str, float] = defaultdict(float)
        by_agent: dict[str, float] = defaultdict(float)
        by_tenant: dict[str, float] = defaultdict(float)

        for rec in filtered:
            total_cost += rec.cost_usd
            total_input += rec.input_tokens
            total_output += rec.output_tokens
            total_latency += rec.latency_ms
            if rec.cached:
                cached_count += 1
            by_model[rec.model] += rec.cost_usd
            by_agent[rec.agent_id] += rec.cost_usd
            by_tenant[rec.tenant_id] += rec.cost_usd

        count = len(filtered)
        period_start = min(r.timestamp for r in filtered)
        period_end = max(r.timestamp for r in filtered)

        # Estimate how much money caching saved
        cache_savings = 0.0
        for rec in filtered:
            if rec.cached:
                cache_savings += self.calculate_cost(
                    rec.model, rec.input_tokens, rec.output_tokens
                )

        return CostSummary(
            period_start=period_start,
            period_end=period_end,
            total_cost_usd=total_cost,
            total_requests=count,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            avg_cost_per_request=total_cost / count if count else 0.0,
            avg_latency_ms=total_latency / count if count else 0.0,
            by_model=dict(by_model),
            by_agent=dict(by_agent),
            by_tenant=dict(by_tenant),
            cache_hit_rate=cached_count / count if count else 0.0,
            cache_savings_usd=cache_savings,
        )

    def get_top_consumers(
        self,
        by: str = "tenant",
        limit: int = 10,
        start_time: datetime | None = None,
    ) -> list[tuple[str, float]]:
        """
        Return the top cost consumers ranked by total spend.

        Args:
            by: Dimension to group by — "tenant", "agent", or "user".
            limit: Maximum number of results.
            start_time: Only consider records after this timestamp.

        Returns:
            List of (identifier, total_cost_usd) tuples, descending.
        """
        filtered = self._filter_records(start_time=start_time)
        buckets: dict[str, float] = defaultdict(float)

        attr_map = {"tenant": "tenant_id", "agent": "agent_id", "user": "user_id"}
        attr = attr_map.get(by, "tenant_id")

        for rec in filtered:
            key = getattr(rec, attr, "unknown")
            buckets[key] += rec.cost_usd

        ranked = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
        return ranked[:limit]

    def get_model_breakdown(
        self,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
    ) -> dict[str, dict[str, Any]]:
        """
        Return per-model cost, request count, and token totals.

        Returns:
            {model_name: {"cost": float, "requests": int, "input_tokens": int, "output_tokens": int}}
        """
        filtered = self._filter_records(tenant_id=tenant_id, start_time=start_time)
        breakdown: dict[str, dict[str, Any]] = {}

        for rec in filtered:
            if rec.model not in breakdown:
                breakdown[rec.model] = {
                    "cost": 0.0,
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            entry = breakdown[rec.model]
            entry["cost"] += rec.cost_usd
            entry["requests"] += 1
            entry["input_tokens"] += rec.input_tokens
            entry["output_tokens"] += rec.output_tokens

        return breakdown

    def get_usage_history(
        self,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[UsageRecord]:
        """Return the most recent usage records, newest first."""
        filtered = self._filter_records(tenant_id=tenant_id, agent_id=agent_id)
        # Return newest first, capped at limit
        return list(reversed(filtered))[:limit]

    def estimate_monthly_cost(self, tenant_id: str) -> float:
        """
        Project the current month's total spend based on the velocity
        of spending so far this month.

        If no data exists for the current month, returns 0.0.
        """
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        filtered = self._filter_records(tenant_id=tenant_id, start_time=month_start)

        if not filtered:
            return 0.0

        total_spend = sum(r.cost_usd for r in filtered)
        elapsed_days = max((now - month_start).total_seconds() / 86400, 1.0)

        # Days in current month
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        days_in_month = (next_month - month_start).days

        daily_rate = total_spend / elapsed_days
        return daily_rate * days_in_month

    # ── Pricing Management ───────────────────────────────────────────

    def update_pricing(
        self,
        model: str,
        input_price: float,
        output_price: float,
    ) -> None:
        """
        Update or add per-1M-token pricing for a model.

        Args:
            model: Model identifier (e.g. "claude-sonnet-4-20250514").
            input_price: USD per 1M input tokens.
            output_price: USD per 1M output tokens.
        """
        with self._lock:
            self._pricing[model] = {"input": input_price, "output": output_price}
        logger.info(
            "Pricing updated: model=%s input=$%.4f/1M output=$%.4f/1M",
            model,
            input_price,
            output_price,
        )

    def get_pricing(self) -> dict[str, dict[str, float]]:
        """Return a copy of the current pricing table."""
        with self._lock:
            return {k: dict(v) for k, v in self._pricing.items()}

    # ── Observability ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return tracker statistics for health/observability endpoints."""
        with self._lock:
            return {
                "total_tracked": self._stats["total_tracked"],
                "total_cost": round(self._stats["total_cost"], 6),
                "records_count": self._stats["records_count"],
                "max_records": self._max_records,
                "models_priced": len(self._pricing),
            }

    def reset(self) -> None:
        """Clear all records and reset stats. Intended for testing."""
        with self._lock:
            self._records.clear()
            self._stats = {
                "total_tracked": 0,
                "total_cost": 0.0,
                "records_count": 0,
            }
            self._pricing = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
        logger.info("CostTracker reset")

    # ── Internal Helpers ─────────────────────────────────────────────

    def _filter_records(
        self,
        tenant_id: str | None = None,
        agent_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[UsageRecord]:
        """Apply optional filters to the records list."""
        with self._lock:
            records = list(self._records)

        if tenant_id:
            records = [r for r in records if r.tenant_id == tenant_id]
        if agent_id:
            records = [r for r in records if r.agent_id == agent_id]
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]

        return records
