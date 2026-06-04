"""
SevaForge Auth Layer — Rate Limiter & Circuit Breaker

Token-bucket rate limiter and circuit breaker for downstream service protection.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from sevaforge.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_at: float
    retry_after: float


@dataclass
class _TokenBucket:
    tokens: float
    max_tokens: int
    refill_rate: float
    last_refill: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)


class RateLimiter:
    def __init__(self, max_tokens: int | None = None, refill_rate: float | None = None, stale_bucket_seconds: float = 3600.0):
        settings = get_settings()
        self._max_tokens = max_tokens or settings.redis_rate_limit_max
        self._refill_rate = refill_rate or settings.redis_rate_limit_refill
        self._stale_seconds = stale_bucket_seconds
        self._buckets: dict[str, _TokenBucket] = {}
        self._stats = {"total_checks": 0, "total_allowed": 0, "total_rejected": 0, "active_buckets": 0, "stale_cleanups": 0}

    def check(self, key: str) -> bool:
        bucket = self._get_or_create(key)
        self._refill(bucket)
        return bucket.tokens >= 1.0

    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        bucket = self._get_or_create(key)
        self._refill(bucket)
        self._stats["total_checks"] += 1
        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            bucket.last_access = time.time()
            self._stats["total_allowed"] += 1
            return RateLimitResult(allowed=True, remaining=int(bucket.tokens), reset_at=self._next_full_refill(bucket), retry_after=0.0)
        deficit = tokens - bucket.tokens
        retry_after = deficit / self._refill_rate if self._refill_rate > 0 else 0.0
        self._stats["total_rejected"] += 1
        return RateLimitResult(allowed=False, remaining=int(bucket.tokens), reset_at=self._next_full_refill(bucket), retry_after=round(retry_after, 2))

    def remaining(self, key: str) -> int:
        bucket = self._buckets.get(key)
        if bucket is None:
            return self._max_tokens
        self._refill(bucket)
        return int(bucket.tokens)

    def cleanup_stale(self) -> int:
        now = time.time()
        stale_keys = [k for k, b in self._buckets.items() if (now - b.last_access) > self._stale_seconds]
        for k in stale_keys:
            del self._buckets[k]
        if stale_keys:
            self._stats["stale_cleanups"] += len(stale_keys)
        self._stats["active_buckets"] = len(self._buckets)
        return len(stale_keys)

    def stats(self) -> dict[str, Any]:
        self._stats["active_buckets"] = len(self._buckets)
        return {**self._stats, "max_tokens": self._max_tokens, "refill_rate": self._refill_rate}

    def reset(self) -> None:
        self._buckets.clear()
        self._stats = {k: 0 for k in self._stats}

    def _get_or_create(self, key: str) -> _TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = _TokenBucket(tokens=float(self._max_tokens), max_tokens=self._max_tokens, refill_rate=self._refill_rate)
            self._stats["active_buckets"] = len(self._buckets)
        return self._buckets[key]

    def _refill(self, bucket: _TokenBucket) -> None:
        now = time.time()
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return
        added = elapsed * bucket.refill_rate
        bucket.tokens = min(bucket.tokens + added, float(bucket.max_tokens))
        bucket.last_refill = now

    def _next_full_refill(self, bucket: _TokenBucket) -> float:
        deficit = float(bucket.max_tokens) - bucket.tokens
        if deficit <= 0:
            return time.time()
        seconds_to_full = deficit / bucket.refill_rate if bucket.refill_rate > 0 else 0.0
        return time.time() + seconds_to_full


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    pass


class CircuitBreaker:
    def __init__(self, name: str = "default", failure_threshold: int = 5, recovery_timeout: float = 30.0, half_open_max_calls: int = 3):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._stats = {"total_calls": 0, "total_successes": 0, "total_failures": 0, "total_rejected": 0, "times_opened": 0, "half_open_successes": 0, "half_open_failures": 0}

    @property
    def state(self) -> CircuitBreakerState:
        if self._state == CircuitBreakerState.OPEN:
            if time.time() - self._opened_at >= self._recovery_timeout:
                self._transition(CircuitBreakerState.HALF_OPEN)
        return self._state

    @property
    def name(self) -> str:
        return self._name

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        current_state = self.state
        self._stats["total_calls"] += 1
        if current_state == CircuitBreakerState.OPEN:
            self._stats["total_rejected"] += 1
            raise CircuitBreakerError(f"Circuit breaker '{self._name}' is open")
        if current_state == CircuitBreakerState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                self._stats["total_rejected"] += 1
                raise CircuitBreakerError(f"Circuit breaker '{self._name}' half-open call limit reached")
            self._half_open_calls += 1
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise

    def record_success(self) -> None:
        self._stats["total_successes"] += 1
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._stats["half_open_successes"] += 1
            self._success_count += 1
            if self._success_count >= self._half_open_max_calls:
                self._transition(CircuitBreakerState.CLOSED)
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._stats["total_failures"] += 1
        self._last_failure_time = time.time()
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._stats["half_open_failures"] += 1
            self._transition(CircuitBreakerState.OPEN)
        else:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._transition(CircuitBreakerState.OPEN)

    def stats(self) -> dict[str, Any]:
        return {"name": self._name, "state": self.state.value, "failure_count": self._failure_count, "failure_threshold": self._failure_threshold, "recovery_timeout": self._recovery_timeout, "half_open_max_calls": self._half_open_max_calls, **self._stats}

    def reset(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0
        self._stats = {k: 0 for k in self._stats}

    def _transition(self, new_state: CircuitBreakerState) -> None:
        old_state = self._state
        self._state = new_state
        logger.info("Circuit '%s': %s -> %s", self._name, old_state.value, new_state.value)
        if new_state == CircuitBreakerState.OPEN:
            self._opened_at = time.time()
            self._stats["times_opened"] += 1
        elif new_state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0

    def _seconds_until_half_open(self) -> float:
        if self._state != CircuitBreakerState.OPEN:
            return 0.0
        elapsed = time.time() - self._opened_at
        remaining = self._recovery_timeout - elapsed
        return max(0.0, remaining)
