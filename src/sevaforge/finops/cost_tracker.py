"""
SevaForge FinOps — Cost Tracker

Per-request cost attribution and rollup engine.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class UsageRecord:
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    execution_id: str = ""
    trace_id: str = ""
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"record_id": self.record_id, "timestamp": self.timestamp.isoformat(), "agent_id": self.agent_id, "user_id": self.user_id, "tenant_id": self.tenant_id, "model": self.model, "input_tokens": self.input_tokens, "output_tokens": self.output_tokens, "cost_usd": self.cost_usd, "latency_ms": self.latency_ms, "execution_id": self.execution_id, "trace_id": self.trace_id, "cached": self.cached, "metadata": self.metadata}


@dataclass
class CostSummary:
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)
    total_cost_usd: float = 0.0
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_cost_per_request: float = 0.0
    avg_latency_ms: float = 0.0
    by_model: dict[str, float] = field(default_factory=dict)
    by_agent: dict[str, float] = field(default_factory=dict)
    by_tenant: dict[str, float] = field(default_factory=dict)
    cache_hit_rate: float = 0.0
    cache_savings_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"period_start": self.period_start.isoformat(), "period_end": self.period_end.isoformat(), "total_cost_usd": round(self.total_cost_usd, 6), "total_requests": self.total_requests, "total_input_tokens": self.total_input_tokens, "total_output_tokens": self.total_output_tokens, "avg_cost_per_request": round(self.avg_cost_per_request, 6), "avg_latency_ms": round(self.avg_latency_ms, 2), "by_model": {k: round(v, 6) for k, v in self.by_model.items()}, "by_agent": {k: round(v, 6) for k, v in self.by_agent.items()}, "by_tenant": {k: round(v, 6) for k, v in self.by_tenant.items()}, "cache_hit_rate": round(self.cache_hit_rate, 4), "cache_savings_usd": round(self.cache_savings_usd, 6)}


DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
}
_FALLBACK_RATE: dict[str, float] = {"input": 3.0, "output": 15.0}


class CostTracker:
    def __init__(self, max_records: int = 100_000) -> None:
        self._max_records = max_records
        self._records: list[UsageRecord] = []
        self._pricing: dict[str, dict[str, float]] = {k: dict(v) for k, v in DEFAULT_PRICING.items()}
        self._lock = threading.Lock()
        self._stats = {"total_tracked": 0, "total_cost": 0.0, "records_count": 0}

    def record_usage(self, agent_id: str, user_id: str, tenant_id: str, model: str, input_tokens: int, output_tokens: int, latency_ms: float = 0.0, execution_id: str = "", trace_id: str = "", cached: bool = False, metadata: dict[str, Any] | None = None) -> UsageRecord:
        cost = 0.0 if cached else self.calculate_cost(model, input_tokens, output_tokens)
        record = UsageRecord(agent_id=agent_id, user_id=user_id, tenant_id=tenant_id, model=model, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost, latency_ms=latency_ms, execution_id=execution_id, trace_id=trace_id, cached=cached, metadata=metadata or {})
        with self._lock:
            self._records.append(record)
            self._stats["total_tracked"] += 1
            self._stats["total_cost"] += cost
            self._stats["records_count"] = len(self._records)
            if len(self._records) > self._max_records:
                overflow = len(self._records) - self._max_records
                self._records = self._records[overflow:]
                self._stats["records_count"] = len(self._records)
        return record

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = self._pricing.get(model, _FALLBACK_RATE)
        return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

    def get_summary(self, tenant_id: str | None = None, agent_id: str | None = None, start_time: datetime | None = None, end_time: datetime | None = None) -> CostSummary:
        filtered = self._filter_records(tenant_id, agent_id, start_time, end_time)
        if not filtered:
            now = datetime.utcnow()
            return CostSummary(period_start=start_time or now, period_end=end_time or now)
        total_cost = sum(r.cost_usd for r in filtered)
        total_latency = sum(r.latency_ms for r in filtered)
        cached_count = sum(1 for r in filtered if r.cached)
        by_model: dict[str, float] = defaultdict(float)
        by_agent: dict[str, float] = defaultdict(float)
        by_tenant: dict[str, float] = defaultdict(float)
        for rec in filtered:
            by_model[rec.model] += rec.cost_usd
            by_agent[rec.agent_id] += rec.cost_usd
            by_tenant[rec.tenant_id] += rec.cost_usd
        count = len(filtered)
        return CostSummary(period_start=min(r.timestamp for r in filtered), period_end=max(r.timestamp for r in filtered), total_cost_usd=total_cost, total_requests=count, total_input_tokens=sum(r.input_tokens for r in filtered), total_output_tokens=sum(r.output_tokens for r in filtered), avg_cost_per_request=total_cost / count if count else 0.0, avg_latency_ms=total_latency / count if count else 0.0, by_model=dict(by_model), by_agent=dict(by_agent), by_tenant=dict(by_tenant), cache_hit_rate=cached_count / count if count else 0.0)

    def get_top_consumers(self, by: str = "tenant", limit: int = 10, start_time: datetime | None = None) -> list[tuple[str, float]]:
        filtered = self._filter_records(start_time=start_time)
        buckets: dict[str, float] = defaultdict(float)
        attr_map = {"tenant": "tenant_id", "agent": "agent_id", "user": "user_id"}
        attr = attr_map.get(by, "tenant_id")
        for rec in filtered:
            buckets[getattr(rec, attr, "unknown")] += rec.cost_usd
        return sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:limit]

    def get_model_breakdown(self, tenant_id: str | None = None, start_time: datetime | None = None) -> dict[str, dict[str, Any]]:
        filtered = self._filter_records(tenant_id=tenant_id, start_time=start_time)
        breakdown: dict[str, dict[str, Any]] = {}
        for rec in filtered:
            if rec.model not in breakdown:
                breakdown[rec.model] = {"cost": 0.0, "requests": 0, "input_tokens": 0, "output_tokens": 0}
            entry = breakdown[rec.model]
            entry["cost"] += rec.cost_usd
            entry["requests"] += 1
            entry["input_tokens"] += rec.input_tokens
            entry["output_tokens"] += rec.output_tokens
        return breakdown

    def get_usage_history(self, tenant_id: str | None = None, agent_id: str | None = None, limit: int = 100) -> list[UsageRecord]:
        filtered = self._filter_records(tenant_id=tenant_id, agent_id=agent_id)
        return list(reversed(filtered))[:limit]

    def update_pricing(self, model: str, input_price: float, output_price: float) -> None:
        with self._lock:
            self._pricing[model] = {"input": input_price, "output": output_price}

    def get_pricing(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {k: dict(v) for k, v in self._pricing.items()}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"total_tracked": self._stats["total_tracked"], "total_cost": round(self._stats["total_cost"], 6), "records_count": self._stats["records_count"], "max_records": self._max_records, "models_priced": len(self._pricing)}

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._stats = {"total_tracked": 0, "total_cost": 0.0, "records_count": 0}
            self._pricing = {k: dict(v) for k, v in DEFAULT_PRICING.items()}

    def _filter_records(self, tenant_id: str | None = None, agent_id: str | None = None, start_time: datetime | None = None, end_time: datetime | None = None) -> list[UsageRecord]:
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
