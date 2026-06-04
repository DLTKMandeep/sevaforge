"""
SevaForge FinOps — Budget Manager

Budget quotas and spending controls for multi-tenant cost governance.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BudgetStatus(str, Enum):
    ACTIVE = "active"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"
    SUSPENDED = "suspended"


@dataclass
class BudgetAlert:
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    quota_id: str = ""
    tenant_id: str = ""
    alert_type: str = "warning"
    current_spend: float = 0.0
    budget_limit: float = 0.0
    percentage_used: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"alert_id": self.alert_id, "timestamp": self.timestamp.isoformat(), "quota_id": self.quota_id, "tenant_id": self.tenant_id, "alert_type": self.alert_type, "current_spend": round(self.current_spend, 6), "budget_limit": round(self.budget_limit, 6), "percentage_used": round(self.percentage_used, 4), "message": self.message}


@dataclass
class BudgetQuota:
    quota_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    budget_limit_usd: float = 0.0
    period: str = "monthly"
    warning_threshold: float = 0.80
    critical_threshold: float = 0.95
    auto_throttle: bool = True
    hard_limit: bool = False
    current_spend: float = 0.0
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)
    status: BudgetStatus = BudgetStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def percentage_used(self) -> float:
        if self.budget_limit_usd <= 0:
            return 0.0
        return self.current_spend / self.budget_limit_usd

    @property
    def remaining_budget(self) -> float:
        return max(self.budget_limit_usd - self.current_spend, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {"quota_id": self.quota_id, "tenant_id": self.tenant_id, "budget_limit_usd": round(self.budget_limit_usd, 6), "period": self.period, "warning_threshold": self.warning_threshold, "critical_threshold": self.critical_threshold, "auto_throttle": self.auto_throttle, "hard_limit": self.hard_limit, "current_spend": round(self.current_spend, 6), "period_start": self.period_start.isoformat(), "period_end": self.period_end.isoformat(), "status": self.status.value, "percentage_used": round(self.percentage_used, 4), "remaining_budget": round(self.remaining_budget, 6), "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat(), "metadata": self.metadata}


@dataclass
class BudgetCheckResult:
    allowed: bool = True
    quota_id: str = ""
    remaining_budget: float = 0.0
    status: BudgetStatus = BudgetStatus.ACTIVE
    throttle_factor: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "quota_id": self.quota_id, "remaining_budget": round(self.remaining_budget, 6), "status": self.status.value, "throttle_factor": round(self.throttle_factor, 4)}


AlertCallback = Callable[[BudgetAlert], None]


class BudgetManager:
    def __init__(self) -> None:
        self._quotas: dict[str, BudgetQuota] = {}
        self._tenant_index: dict[str, list[str]] = {}
        self._alerts: list[BudgetAlert] = []
        self._alert_callbacks: list[AlertCallback] = []
        self._lock = threading.RLock()
        self._stats = {"quotas_created": 0, "checks_performed": 0, "requests_throttled": 0, "requests_blocked": 0, "alerts_generated": 0}

    def create_quota(self, tenant_id: str, budget_limit_usd: float, period: str = "monthly", warning_threshold: float = 0.80, critical_threshold: float = 0.95, auto_throttle: bool = True, hard_limit: bool = False, metadata: dict[str, Any] | None = None) -> BudgetQuota:
        now = datetime.utcnow()
        period_start, period_end = self._compute_period_bounds(now, period)
        quota = BudgetQuota(tenant_id=tenant_id, budget_limit_usd=budget_limit_usd, period=period, warning_threshold=warning_threshold, critical_threshold=critical_threshold, auto_throttle=auto_throttle, hard_limit=hard_limit, period_start=period_start, period_end=period_end, status=BudgetStatus.ACTIVE, created_at=now, updated_at=now, metadata=metadata or {})
        with self._lock:
            self._quotas[quota.quota_id] = quota
            self._tenant_index.setdefault(tenant_id, []).append(quota.quota_id)
            self._stats["quotas_created"] += 1
        return quota

    def get_tenant_quotas(self, tenant_id: str) -> list[BudgetQuota]:
        with self._lock:
            quota_ids = self._tenant_index.get(tenant_id, [])
            return [self._quotas[qid] for qid in quota_ids if qid in self._quotas]

    def check_budget(self, tenant_id: str, estimated_cost: float = 0.0) -> BudgetCheckResult:
        with self._lock:
            self._stats["checks_performed"] += 1
            quotas = self.get_tenant_quotas(tenant_id)
        if not quotas:
            return BudgetCheckResult(allowed=True, throttle_factor=1.0)
        worst_status = BudgetStatus.ACTIVE
        min_throttle = 1.0
        min_remaining = float("inf")
        blocking_quota_id = ""
        blocked = False
        for quota in quotas:
            projected = quota.current_spend + estimated_cost
            pct = projected / quota.budget_limit_usd if quota.budget_limit_usd > 0 else 0.0
            remaining = quota.remaining_budget - estimated_cost
            if remaining < min_remaining:
                min_remaining = remaining
            if pct >= 1.0:
                status = BudgetStatus.EXCEEDED
            elif pct >= quota.critical_threshold:
                status = BudgetStatus.CRITICAL
            elif pct >= quota.warning_threshold:
                status = BudgetStatus.WARNING
            else:
                status = BudgetStatus.ACTIVE
            status_severity = {BudgetStatus.ACTIVE: 0, BudgetStatus.WARNING: 1, BudgetStatus.CRITICAL: 2, BudgetStatus.EXCEEDED: 3, BudgetStatus.SUSPENDED: 4}
            if status_severity.get(status, 0) > status_severity.get(worst_status, 0):
                worst_status = status
                blocking_quota_id = quota.quota_id
            if quota.auto_throttle and pct >= quota.warning_threshold:
                range_width = 1.0 - quota.warning_threshold
                if range_width > 0:
                    overshoot = min(pct - quota.warning_threshold, range_width) / range_width
                    throttle = max(1.0 - (overshoot * 0.9), 0.1)
                else:
                    throttle = 0.1
                min_throttle = min(min_throttle, throttle)
            if quota.hard_limit and pct >= 1.0:
                blocked = True
                blocking_quota_id = quota.quota_id
        if blocked:
            with self._lock:
                self._stats["requests_blocked"] += 1
            return BudgetCheckResult(allowed=False, quota_id=blocking_quota_id, remaining_budget=max(min_remaining, 0.0), status=BudgetStatus.EXCEEDED, throttle_factor=0.0)
        if min_throttle < 1.0:
            with self._lock:
                self._stats["requests_throttled"] += 1
        return BudgetCheckResult(allowed=True, quota_id=blocking_quota_id, remaining_budget=max(min_remaining, 0.0), status=worst_status, throttle_factor=min_throttle)

    def record_spend(self, tenant_id: str, amount_usd: float) -> list[BudgetAlert]:
        all_alerts: list[BudgetAlert] = []
        with self._lock:
            quota_ids = self._tenant_index.get(tenant_id, [])
            quotas = [self._quotas[qid] for qid in quota_ids if qid in self._quotas]
        for quota in quotas:
            old_pct = quota.percentage_used
            with self._lock:
                quota.current_spend += amount_usd
                quota.updated_at = datetime.utcnow()
                self._update_status(quota)
            new_alerts = self._check_thresholds(quota, old_pct)
            all_alerts.extend(new_alerts)
        return all_alerts

    def _check_thresholds(self, quota: BudgetQuota, previous_pct: float) -> list[BudgetAlert]:
        alerts: list[BudgetAlert] = []
        current_pct = quota.percentage_used
        if previous_pct < quota.warning_threshold <= current_pct:
            alerts.append(BudgetAlert(quota_id=quota.quota_id, tenant_id=quota.tenant_id, alert_type="warning", current_spend=quota.current_spend, budget_limit=quota.budget_limit_usd, percentage_used=current_pct, message=f"Warning: {current_pct:.0%} of budget used"))
        if previous_pct < quota.critical_threshold <= current_pct:
            alerts.append(BudgetAlert(quota_id=quota.quota_id, tenant_id=quota.tenant_id, alert_type="critical", current_spend=quota.current_spend, budget_limit=quota.budget_limit_usd, percentage_used=current_pct, message=f"CRITICAL: {current_pct:.0%} of budget used"))
        if previous_pct < 1.0 <= current_pct:
            alerts.append(BudgetAlert(quota_id=quota.quota_id, tenant_id=quota.tenant_id, alert_type="exceeded", current_spend=quota.current_spend, budget_limit=quota.budget_limit_usd, percentage_used=current_pct, message=f"EXCEEDED: {current_pct:.0%} of budget used"))
        if alerts:
            with self._lock:
                self._alerts.extend(alerts)
                self._stats["alerts_generated"] += len(alerts)
        return alerts

    def _update_status(self, quota: BudgetQuota) -> None:
        pct = quota.percentage_used
        if quota.status == BudgetStatus.SUSPENDED:
            return
        if pct >= 1.0:
            quota.status = BudgetStatus.EXCEEDED
        elif pct >= quota.critical_threshold:
            quota.status = BudgetStatus.CRITICAL
        elif pct >= quota.warning_threshold:
            quota.status = BudgetStatus.WARNING
        else:
            quota.status = BudgetStatus.ACTIVE

    def get_alerts(self, tenant_id: str | None = None, limit: int = 50) -> list[BudgetAlert]:
        with self._lock:
            alerts = list(self._alerts)
        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]
        return list(reversed(alerts))[:limit]

    def get_budget_report(self, tenant_id: str) -> dict[str, Any]:
        quotas = self.get_tenant_quotas(tenant_id)
        if not quotas:
            return {"tenant_id": tenant_id, "quotas": [], "total_budget": 0.0, "total_spend": 0.0, "overall_status": BudgetStatus.ACTIVE.value}
        total_budget = sum(q.budget_limit_usd for q in quotas)
        total_spend = sum(q.current_spend for q in quotas)
        return {"tenant_id": tenant_id, "quotas": [q.to_dict() for q in quotas], "total_budget": round(total_budget, 6), "total_spend": round(total_spend, 6), "overall_status": max(quotas, key=lambda q: q.percentage_used).status.value}

    @staticmethod
    def _compute_period_bounds(reference: datetime, period: str) -> tuple[datetime, datetime]:
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "daily":
            end = start + timedelta(days=1)
        elif period == "weekly":
            start = start - timedelta(days=start.weekday())
            end = start + timedelta(weeks=1)
        else:
            start = start.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1)
            else:
                end = start.replace(month=start.month + 1, day=1)
        return start, end

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {"quotas_created": self._stats["quotas_created"], "active_quotas": len(self._quotas), "checks_performed": self._stats["checks_performed"], "requests_throttled": self._stats["requests_throttled"], "requests_blocked": self._stats["requests_blocked"], "alerts_generated": self._stats["alerts_generated"], "total_alerts_stored": len(self._alerts)}

    def reset(self) -> None:
        with self._lock:
            self._quotas.clear()
            self._tenant_index.clear()
            self._alerts.clear()
            self._alert_callbacks.clear()
            self._stats = {k: 0 for k in self._stats}
