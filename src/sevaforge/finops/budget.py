"""
SevaForge FinOps — Budget Manager

Budget quotas and spending controls for multi-tenant cost governance.
Supports daily/weekly/monthly budget periods with configurable warning
and critical thresholds, automatic throttling, and hard spending limits.

Architecture:
    BudgetQuota  — per-tenant spending cap for a time period
    BudgetAlert  — immutable notification when a threshold is crossed
    BudgetManager — create/check/enforce quotas, emit alerts

Alert flow:
    record_spend() → _check_thresholds() → BudgetAlert → on_alert callbacks

Designed for drop-in replacement with a persistent backend.
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


# ── Enums ────────────────────────────────────────────────────────────


class BudgetStatus(str, Enum):
    """Current health of a budget quota."""

    ACTIVE = "active"           # Under warning threshold
    WARNING = "warning"         # Past warning, under critical
    CRITICAL = "critical"       # Past critical, under 100%
    EXCEEDED = "exceeded"       # At or past 100% of budget
    SUSPENDED = "suspended"     # Manually or automatically suspended


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class BudgetAlert:
    """Immutable record of a budget threshold being crossed."""

    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    quota_id: str = ""
    tenant_id: str = ""
    alert_type: str = "warning"       # "warning" | "critical" | "exceeded"
    current_spend: float = 0.0
    budget_limit: float = 0.0
    percentage_used: float = 0.0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "quota_id": self.quota_id,
            "tenant_id": self.tenant_id,
            "alert_type": self.alert_type,
            "current_spend": round(self.current_spend, 6),
            "budget_limit": round(self.budget_limit, 6),
            "percentage_used": round(self.percentage_used, 4),
            "message": self.message,
        }


@dataclass
class BudgetQuota:
    """
    A spending cap for a tenant over a rolling time period.

    Thresholds are expressed as fractions of the budget limit:
        warning_threshold=0.8  → alert at 80% spend
        critical_threshold=0.95 → alert at 95% spend
    """

    quota_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = ""
    budget_limit_usd: float = 0.0
    period: str = "monthly"           # "daily" | "weekly" | "monthly"

    # Thresholds (0.0–1.0)
    warning_threshold: float = 0.80
    critical_threshold: float = 0.95

    # Enforcement
    auto_throttle: bool = True        # Gradually reduce throughput when nearing limit
    hard_limit: bool = False          # Reject requests outright when limit is exceeded

    # Runtime state
    current_spend: float = 0.0
    period_start: datetime = field(default_factory=datetime.utcnow)
    period_end: datetime = field(default_factory=datetime.utcnow)
    status: BudgetStatus = BudgetStatus.ACTIVE

    # Bookkeeping
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def percentage_used(self) -> float:
        """Fraction of the budget consumed (0.0–1.0+)."""
        if self.budget_limit_usd <= 0:
            return 0.0
        return self.current_spend / self.budget_limit_usd

    @property
    def remaining_budget(self) -> float:
        """USD remaining before the budget cap is reached."""
        return max(self.budget_limit_usd - self.current_spend, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "quota_id": self.quota_id,
            "tenant_id": self.tenant_id,
            "budget_limit_usd": round(self.budget_limit_usd, 6),
            "period": self.period,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "auto_throttle": self.auto_throttle,
            "hard_limit": self.hard_limit,
            "current_spend": round(self.current_spend, 6),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "status": self.status.value,
            "percentage_used": round(self.percentage_used, 4),
            "remaining_budget": round(self.remaining_budget, 6),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class BudgetCheckResult:
    """Result of a pre-request budget check."""

    allowed: bool = True
    quota_id: str = ""
    remaining_budget: float = 0.0
    status: BudgetStatus = BudgetStatus.ACTIVE
    throttle_factor: float = 1.0      # 1.0 = full speed, 0.0 = fully throttled

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "quota_id": self.quota_id,
            "remaining_budget": round(self.remaining_budget, 6),
            "status": self.status.value,
            "throttle_factor": round(self.throttle_factor, 4),
        }


# ── Budget Manager ───────────────────────────────────────────────────

# Type alias for alert callback functions
AlertCallback = Callable[[BudgetAlert], None]


class BudgetManager:
    """
    Multi-tenant budget governance engine.

    Provides quota CRUD, pre-request budget checks, spend recording
    with automatic threshold alerts, and period-reset logic.

    Thread-safe for concurrent request processing.

    Usage:
        mgr = BudgetManager()
        quota = mgr.create_quota("t-acme", budget_limit_usd=500.0, period="monthly")
        result = mgr.check_budget("t-acme", estimated_cost=0.05)
        if result.allowed:
            # proceed with LLM call
            mgr.record_spend("t-acme", actual_cost)
    """

    def __init__(self) -> None:
        self._quotas: dict[str, BudgetQuota] = {}        # quota_id → quota
        self._tenant_index: dict[str, list[str]] = {}    # tenant_id → [quota_ids]
        self._alerts: list[BudgetAlert] = []
        self._alert_callbacks: list[AlertCallback] = []
        self._lock = threading.RLock()

        # Observability stats
        self._stats = {
            "quotas_created": 0,
            "checks_performed": 0,
            "requests_throttled": 0,
            "requests_blocked": 0,
            "alerts_generated": 0,
        }

    # ── Quota CRUD ───────────────────────────────────────────────────

    def create_quota(
        self,
        tenant_id: str,
        budget_limit_usd: float,
        period: str = "monthly",
        warning_threshold: float = 0.80,
        critical_threshold: float = 0.95,
        auto_throttle: bool = True,
        hard_limit: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetQuota:
        """
        Create a new budget quota for a tenant.

        Args:
            tenant_id: Tenant identifier.
            budget_limit_usd: Maximum spend in USD for the period.
            period: "daily", "weekly", or "monthly".
            warning_threshold: Fraction at which a warning alert fires.
            critical_threshold: Fraction at which a critical alert fires.
            auto_throttle: Gradually reduce throughput near the limit.
            hard_limit: Block requests entirely when the limit is exceeded.
            metadata: Arbitrary key-value pairs for tagging.

        Returns:
            The newly created BudgetQuota.
        """
        now = datetime.utcnow()
        period_start, period_end = self._compute_period_bounds(now, period)

        quota = BudgetQuota(
            tenant_id=tenant_id,
            budget_limit_usd=budget_limit_usd,
            period=period,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
            auto_throttle=auto_throttle,
            hard_limit=hard_limit,
            period_start=period_start,
            period_end=period_end,
            status=BudgetStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        with self._lock:
            self._quotas[quota.quota_id] = quota
            self._tenant_index.setdefault(tenant_id, []).append(quota.quota_id)
            self._stats["quotas_created"] += 1

        logger.info(
            "Budget quota created: tenant=%s limit=$%.2f period=%s quota_id=%s",
            tenant_id,
            budget_limit_usd,
            period,
            quota.quota_id,
        )
        return quota

    def update_quota(
        self,
        quota_id: str,
        budget_limit_usd: float | None = None,
        warning_threshold: float | None = None,
        critical_threshold: float | None = None,
        auto_throttle: bool | None = None,
        hard_limit: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BudgetQuota:
        """
        Update an existing quota's parameters.

        Only the provided arguments are changed; others are left as-is.

        Raises:
            KeyError: If quota_id is not found.
        """
        with self._lock:
            quota = self._quotas.get(quota_id)
            if not quota:
                raise KeyError(f"Quota '{quota_id}' not found")

            if budget_limit_usd is not None:
                quota.budget_limit_usd = budget_limit_usd
            if warning_threshold is not None:
                quota.warning_threshold = warning_threshold
            if critical_threshold is not None:
                quota.critical_threshold = critical_threshold
            if auto_throttle is not None:
                quota.auto_throttle = auto_throttle
            if hard_limit is not None:
                quota.hard_limit = hard_limit
            if metadata is not None:
                quota.metadata.update(metadata)

            quota.updated_at = datetime.utcnow()

            # Recompute status after parameter change
            self._update_status(quota)

        logger.info("Budget quota updated: quota_id=%s", quota_id)
        return quota

    def delete_quota(self, quota_id: str) -> bool:
        """Delete a quota. Returns True if it existed."""
        with self._lock:
            quota = self._quotas.pop(quota_id, None)
            if not quota:
                return False

            tenant_ids = self._tenant_index.get(quota.tenant_id, [])
            if quota_id in tenant_ids:
                tenant_ids.remove(quota_id)
                if not tenant_ids:
                    del self._tenant_index[quota.tenant_id]

        logger.info("Budget quota deleted: quota_id=%s", quota_id)
        return True

    def get_quota(self, quota_id: str) -> BudgetQuota | None:
        """Retrieve a single quota by ID."""
        with self._lock:
            return self._quotas.get(quota_id)

    def get_tenant_quotas(self, tenant_id: str) -> list[BudgetQuota]:
        """Return all quotas for a given tenant."""
        with self._lock:
            quota_ids = self._tenant_index.get(tenant_id, [])
            return [self._quotas[qid] for qid in quota_ids if qid in self._quotas]

    # ── Budget Enforcement ───────────────────────────────────────────

    def check_budget(
        self,
        tenant_id: str,
        estimated_cost: float = 0.0,
    ) -> BudgetCheckResult:
        """
        Pre-request budget check.

        Evaluates all active quotas for the tenant and returns the
        most restrictive result.  If any quota has a hard limit that
        would be exceeded, the request is denied.

        Args:
            tenant_id: Tenant requesting an LLM call.
            estimated_cost: Estimated cost of the upcoming request.

        Returns:
            BudgetCheckResult with allowed flag and throttle factor.
        """
        with self._lock:
            self._stats["checks_performed"] += 1
            quotas = self.get_tenant_quotas(tenant_id)

        if not quotas:
            # No quota means no restrictions
            return BudgetCheckResult(allowed=True, throttle_factor=1.0)

        # Auto-reset any expired periods first
        self._auto_reset_expired()

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

            # Determine effective status for this quota
            if pct >= 1.0:
                status = BudgetStatus.EXCEEDED
            elif pct >= quota.critical_threshold:
                status = BudgetStatus.CRITICAL
            elif pct >= quota.warning_threshold:
                status = BudgetStatus.WARNING
            else:
                status = BudgetStatus.ACTIVE

            # Track worst status
            status_severity = {
                BudgetStatus.ACTIVE: 0,
                BudgetStatus.WARNING: 1,
                BudgetStatus.CRITICAL: 2,
                BudgetStatus.EXCEEDED: 3,
                BudgetStatus.SUSPENDED: 4,
            }
            if status_severity.get(status, 0) > status_severity.get(worst_status, 0):
                worst_status = status
                blocking_quota_id = quota.quota_id

            # Compute throttle factor for this quota
            if quota.auto_throttle and pct >= quota.warning_threshold:
                # Linear ramp-down from warning threshold (1.0) to limit (0.1)
                range_width = 1.0 - quota.warning_threshold
                if range_width > 0:
                    overshoot = min(pct - quota.warning_threshold, range_width) / range_width
                    throttle = max(1.0 - (overshoot * 0.9), 0.1)
                else:
                    throttle = 0.1
                min_throttle = min(min_throttle, throttle)

            # Hard block
            if quota.hard_limit and pct >= 1.0:
                blocked = True
                blocking_quota_id = quota.quota_id

        if blocked:
            with self._lock:
                self._stats["requests_blocked"] += 1
            logger.warning(
                "Budget hard limit: tenant=%s blocked (quota=%s)",
                tenant_id,
                blocking_quota_id,
            )
            return BudgetCheckResult(
                allowed=False,
                quota_id=blocking_quota_id,
                remaining_budget=max(min_remaining, 0.0),
                status=BudgetStatus.EXCEEDED,
                throttle_factor=0.0,
            )

        if min_throttle < 1.0:
            with self._lock:
                self._stats["requests_throttled"] += 1

        return BudgetCheckResult(
            allowed=True,
            quota_id=blocking_quota_id,
            remaining_budget=max(min_remaining, 0.0),
            status=worst_status,
            throttle_factor=min_throttle,
        )

    def record_spend(self, tenant_id: str, amount_usd: float) -> list[BudgetAlert]:
        """
        Record actual spend against all active quotas for a tenant.

        Triggers threshold alerts if any quota crosses warning,
        critical, or exceeded boundaries.

        Returns:
            List of any newly generated alerts.
        """
        # Auto-reset expired periods first
        self._auto_reset_expired()

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

    def _check_thresholds(
        self,
        quota: BudgetQuota,
        previous_pct: float,
    ) -> list[BudgetAlert]:
        """
        Check if the quota has crossed any threshold boundaries
        since the last spend recording.

        Only fires alerts on boundary crossings (not repeatedly).

        Returns:
            List of newly generated BudgetAlert objects.
        """
        alerts: list[BudgetAlert] = []
        current_pct = quota.percentage_used

        # Warning threshold crossing
        if previous_pct < quota.warning_threshold <= current_pct:
            alert = BudgetAlert(
                quota_id=quota.quota_id,
                tenant_id=quota.tenant_id,
                alert_type="warning",
                current_spend=quota.current_spend,
                budget_limit=quota.budget_limit_usd,
                percentage_used=current_pct,
                message=(
                    f"Tenant '{quota.tenant_id}' has reached "
                    f"{current_pct:.0%} of {quota.period} budget "
                    f"(${quota.current_spend:.2f} / ${quota.budget_limit_usd:.2f})"
                ),
            )
            alerts.append(alert)

        # Critical threshold crossing
        if previous_pct < quota.critical_threshold <= current_pct:
            alert = BudgetAlert(
                quota_id=quota.quota_id,
                tenant_id=quota.tenant_id,
                alert_type="critical",
                current_spend=quota.current_spend,
                budget_limit=quota.budget_limit_usd,
                percentage_used=current_pct,
                message=(
                    f"CRITICAL: Tenant '{quota.tenant_id}' at "
                    f"{current_pct:.0%} of {quota.period} budget "
                    f"(${quota.current_spend:.2f} / ${quota.budget_limit_usd:.2f})"
                ),
            )
            alerts.append(alert)

        # Budget exceeded
        if previous_pct < 1.0 <= current_pct:
            alert = BudgetAlert(
                quota_id=quota.quota_id,
                tenant_id=quota.tenant_id,
                alert_type="exceeded",
                current_spend=quota.current_spend,
                budget_limit=quota.budget_limit_usd,
                percentage_used=current_pct,
                message=(
                    f"EXCEEDED: Tenant '{quota.tenant_id}' has exceeded "
                    f"{quota.period} budget — ${quota.current_spend:.2f} / "
                    f"${quota.budget_limit_usd:.2f} ({current_pct:.0%})"
                ),
            )
            alerts.append(alert)

        # Persist and dispatch alerts
        if alerts:
            with self._lock:
                self._alerts.extend(alerts)
                self._stats["alerts_generated"] += len(alerts)

            for alert in alerts:
                logger.warning("Budget alert: %s", alert.message)
                self._dispatch_alert(alert)

        return alerts

    def _update_status(self, quota: BudgetQuota) -> None:
        """Recompute a quota's status based on current spend."""
        pct = quota.percentage_used
        if quota.status == BudgetStatus.SUSPENDED:
            return  # Suspended status is sticky until manually cleared
        if pct >= 1.0:
            quota.status = BudgetStatus.EXCEEDED
        elif pct >= quota.critical_threshold:
            quota.status = BudgetStatus.CRITICAL
        elif pct >= quota.warning_threshold:
            quota.status = BudgetStatus.WARNING
        else:
            quota.status = BudgetStatus.ACTIVE

    # ── Alert System ─────────────────────────────────────────────────

    def on_alert(self, callback: AlertCallback) -> None:
        """
        Register a callback to be invoked whenever a budget alert fires.

        The callback receives a BudgetAlert instance.  Multiple
        callbacks can be registered and will be called in order.
        """
        with self._lock:
            self._alert_callbacks.append(callback)
        logger.debug("Alert callback registered: %s", callback)

    def _dispatch_alert(self, alert: BudgetAlert) -> None:
        """Invoke all registered alert callbacks."""
        with self._lock:
            callbacks = list(self._alert_callbacks)

        for cb in callbacks:
            try:
                cb(alert)
            except Exception:
                logger.exception(
                    "Alert callback failed for alert_id=%s",
                    alert.alert_id,
                )

    def get_alerts(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[BudgetAlert]:
        """
        Retrieve recent budget alerts, newest first.

        Args:
            tenant_id: Filter to a specific tenant (or None for all).
            limit: Maximum number of alerts to return.
        """
        with self._lock:
            alerts = list(self._alerts)

        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]

        # Newest first
        return list(reversed(alerts))[:limit]

    # ── Period Management ────────────────────────────────────────────

    def reset_period(self, quota_id: str) -> BudgetQuota:
        """
        Reset a quota's spend counter and advance the period window.

        Raises:
            KeyError: If quota_id is not found.
        """
        with self._lock:
            quota = self._quotas.get(quota_id)
            if not quota:
                raise KeyError(f"Quota '{quota_id}' not found")

            now = datetime.utcnow()
            quota.current_spend = 0.0
            quota.period_start, quota.period_end = self._compute_period_bounds(
                now, quota.period
            )
            quota.status = BudgetStatus.ACTIVE
            quota.updated_at = now

        logger.info(
            "Budget period reset: quota_id=%s new_period=%s–%s",
            quota_id,
            quota.period_start.isoformat(),
            quota.period_end.isoformat(),
        )
        return quota

    def _auto_reset_expired(self) -> None:
        """Check all quotas and reset any whose period has expired."""
        now = datetime.utcnow()

        with self._lock:
            expired = [
                q for q in self._quotas.values()
                if now >= q.period_end and q.status != BudgetStatus.SUSPENDED
            ]

        for quota in expired:
            try:
                self.reset_period(quota.quota_id)
            except KeyError:
                pass  # Quota was deleted concurrently

    @staticmethod
    def _compute_period_bounds(
        reference: datetime,
        period: str,
    ) -> tuple[datetime, datetime]:
        """
        Compute the start and end timestamps for a budget period
        that contains the reference datetime.
        """
        start = reference.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "daily":
            end = start + timedelta(days=1)
        elif period == "weekly":
            # Align to Monday
            start = start - timedelta(days=start.weekday())
            end = start + timedelta(weeks=1)
        elif period == "monthly":
            start = start.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1)
            else:
                end = start.replace(month=start.month + 1, day=1)
        else:
            # Default to monthly
            start = start.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1)
            else:
                end = start.replace(month=start.month + 1, day=1)

        return start, end

    # ── Reporting ────────────────────────────────────────────────────

    def get_budget_report(self, tenant_id: str) -> dict[str, Any]:
        """
        Generate a comprehensive budget report for a tenant.

        Returns:
            Dict with spend, budget, projections, status, and quota details.
        """
        quotas = self.get_tenant_quotas(tenant_id)
        if not quotas:
            return {
                "tenant_id": tenant_id,
                "quotas": [],
                "total_budget": 0.0,
                "total_spend": 0.0,
                "overall_status": BudgetStatus.ACTIVE.value,
            }

        total_budget = sum(q.budget_limit_usd for q in quotas)
        total_spend = sum(q.current_spend for q in quotas)

        # Overall status is the worst across all quotas
        status_order = [
            BudgetStatus.ACTIVE,
            BudgetStatus.WARNING,
            BudgetStatus.CRITICAL,
            BudgetStatus.EXCEEDED,
            BudgetStatus.SUSPENDED,
        ]
        worst = BudgetStatus.ACTIVE
        for q in quotas:
            if status_order.index(q.status) > status_order.index(worst):
                worst = q.status

        # Per-quota details with projections
        quota_details = []
        for q in quotas:
            now = datetime.utcnow()
            elapsed = max((now - q.period_start).total_seconds(), 1.0)
            total_period = max((q.period_end - q.period_start).total_seconds(), 1.0)
            velocity = q.current_spend / elapsed  # USD per second
            projected_spend = velocity * total_period

            quota_details.append({
                **q.to_dict(),
                "projected_spend": round(projected_spend, 6),
                "projected_overage": round(
                    max(projected_spend - q.budget_limit_usd, 0.0), 6
                ),
                "days_remaining": max(
                    (q.period_end - now).total_seconds() / 86400, 0.0
                ),
            })

        return {
            "tenant_id": tenant_id,
            "quotas": quota_details,
            "total_budget": round(total_budget, 6),
            "total_spend": round(total_spend, 6),
            "overall_percentage": round(
                total_spend / total_budget if total_budget > 0 else 0.0, 4
            ),
            "overall_status": worst.value,
        }

    # ── Observability ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return budget manager statistics for health endpoints."""
        with self._lock:
            return {
                "quotas_created": self._stats["quotas_created"],
                "active_quotas": len(self._quotas),
                "checks_performed": self._stats["checks_performed"],
                "requests_throttled": self._stats["requests_throttled"],
                "requests_blocked": self._stats["requests_blocked"],
                "alerts_generated": self._stats["alerts_generated"],
                "total_alerts_stored": len(self._alerts),
            }

    def reset(self) -> None:
        """Clear all quotas, alerts, and stats. Intended for testing."""
        with self._lock:
            self._quotas.clear()
            self._tenant_index.clear()
            self._alerts.clear()
            self._alert_callbacks.clear()
            self._stats = {
                "quotas_created": 0,
                "checks_performed": 0,
                "requests_throttled": 0,
                "requests_blocked": 0,
                "alerts_generated": 0,
            }
        logger.info("BudgetManager reset")
