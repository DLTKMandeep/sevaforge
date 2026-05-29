"""
SevaForge Auth Layer — Rate Limiter & Circuit Breaker

Token-bucket rate limiter and circuit breaker for downstream service protection.

Rate Limiter:
    Classic token-bucket algorithm keyed per API key, tenant, or IP.
    Tokens refill at a configurable rate.  Once the bucket is empty,
    requests are rejected until tokens accumulate.

Circuit Breaker:
    Three-state machine (CLOSED → OPEN → HALF_OPEN → CLOSED) that
    wraps callables and short-circuits when failures exceed a threshold.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from sevaforge.config import get_settings

logger = logging.getLogger(__name__)


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class RateLimitResult:
    """Outcome of a rate-limit check."""

    allowed: bool
    remaining: int          # Tokens left in the bucket
    reset_at: float         # Epoch time when the bucket fully refills
    retry_after: float      # Seconds until at least one token is available (0 if allowed)


@dataclass
class _TokenBucket:
    """Internal state for a single rate-limit key."""

    tokens: float
    max_tokens: int
    refill_rate: float           # Tokens added per second
    last_refill: float = field(default_factory=time.time)
    last_access: float = field(default_factory=time.time)


# ── Rate Limiter ─────────────────────────────────────────────────────


class RateLimiter:
    """
    Token-bucket rate limiter keyed by arbitrary string (API key, tenant, IP, etc.).

    Each key gets its own bucket with ``max_tokens`` capacity that refills
    at ``refill_rate`` tokens per second.

    Usage::

        limiter = RateLimiter(max_tokens=100, refill_rate=10.0)
        result = limiter.consume("tenant-42")
        if not result.allowed:
            raise HTTPException(429, headers={"Retry-After": str(result.retry_after)})
    """

    def __init__(
        self,
        max_tokens: int | None = None,
        refill_rate: float | None = None,
        stale_bucket_seconds: float = 3600.0,
    ):
        settings = get_settings()
        self._max_tokens = max_tokens or settings.redis_rate_limit_max
        self._refill_rate = refill_rate or settings.redis_rate_limit_refill
        self._stale_seconds = stale_bucket_seconds

        # Keyed buckets
        self._buckets: dict[str, _TokenBucket] = {}

        # Observability
        self._stats = {
            "total_checks": 0,
            "total_allowed": 0,
            "total_rejected": 0,
            "active_buckets": 0,
            "stale_cleanups": 0,
        }

    # ── Public API ───────────────────────────────────────────────────

    def check(self, key: str) -> bool:
        """
        Quick boolean check — is the key allowed to proceed?

        Does **not** consume a token.  Use :meth:`consume` for the full result.
        """
        bucket = self._get_or_create(key)
        self._refill(bucket)
        return bucket.tokens >= 1.0

    def consume(self, key: str, tokens: int = 1) -> RateLimitResult:
        """
        Attempt to consume ``tokens`` from the bucket for ``key``.

        Returns a :class:`RateLimitResult` indicating whether the request
        is allowed, how many tokens remain, and when to retry if rejected.
        """
        bucket = self._get_or_create(key)
        self._refill(bucket)
        self._stats["total_checks"] += 1

        if bucket.tokens >= tokens:
            bucket.tokens -= tokens
            bucket.last_access = time.time()
            self._stats["total_allowed"] += 1
            logger.debug("Rate limit OK: key=%s remaining=%.0f", key, bucket.tokens)
            return RateLimitResult(
                allowed=True,
                remaining=int(bucket.tokens),
                reset_at=self._next_full_refill(bucket),
                retry_after=0.0,
            )

        # Rejected — calculate retry delay
        deficit = tokens - bucket.tokens
        retry_after = deficit / self._refill_rate if self._refill_rate > 0 else 0.0
        self._stats["total_rejected"] += 1
        logger.debug(
            "Rate limit EXCEEDED: key=%s tokens=%.1f needed=%d retry_after=%.1fs",
            key, bucket.tokens, tokens, retry_after,
        )
        return RateLimitResult(
            allowed=False,
            remaining=int(bucket.tokens),
            reset_at=self._next_full_refill(bucket),
            retry_after=round(retry_after, 2),
        )

    def remaining(self, key: str) -> int:
        """Return the current token count for ``key`` without consuming."""
        bucket = self._buckets.get(key)
        if bucket is None:
            return self._max_tokens
        self._refill(bucket)
        return int(bucket.tokens)

    def cleanup_stale(self) -> int:
        """
        Remove buckets that have not been accessed within ``stale_bucket_seconds``.

        Returns the number of buckets removed.
        """
        now = time.time()
        stale_keys = [
            k for k, b in self._buckets.items()
            if (now - b.last_access) > self._stale_seconds
        ]
        for k in stale_keys:
            del self._buckets[k]

        if stale_keys:
            self._stats["stale_cleanups"] += len(stale_keys)
            logger.info("Rate limiter: cleaned up %d stale buckets", len(stale_keys))

        self._stats["active_buckets"] = len(self._buckets)
        return len(stale_keys)

    # ── Stats & Admin ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return rate limiter statistics."""
        self._stats["active_buckets"] = len(self._buckets)
        return {
            **self._stats,
            "max_tokens": self._max_tokens,
            "refill_rate": self._refill_rate,
        }

    def reset(self) -> None:
        """Clear all state — for testing only."""
        self._buckets.clear()
        self._stats = {k: 0 for k in self._stats}

    # ── Internal ─────────────────────────────────────────────────────

    def _get_or_create(self, key: str) -> _TokenBucket:
        """Retrieve or lazily create a bucket for the given key."""
        if key not in self._buckets:
            self._buckets[key] = _TokenBucket(
                tokens=float(self._max_tokens),
                max_tokens=self._max_tokens,
                refill_rate=self._refill_rate,
            )
            self._stats["active_buckets"] = len(self._buckets)
        return self._buckets[key]

    def _refill(self, bucket: _TokenBucket) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.time()
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return
        added = elapsed * bucket.refill_rate
        bucket.tokens = min(bucket.tokens + added, float(bucket.max_tokens))
        bucket.last_refill = now

    def _next_full_refill(self, bucket: _TokenBucket) -> float:
        """Epoch time when the bucket will be completely full."""
        deficit = float(bucket.max_tokens) - bucket.tokens
        if deficit <= 0:
            return time.time()
        seconds_to_full = deficit / bucket.refill_rate if bucket.refill_rate > 0 else 0.0
        return time.time() + seconds_to_full


# ── Circuit Breaker ──────────────────────────────────────────────────


class CircuitBreakerState(str, Enum):
    """Circuit breaker FSM states."""

    CLOSED = "closed"           # Normal — requests pass through
    OPEN = "open"               # Tripped — requests short-circuit
    HALF_OPEN = "half_open"     # Probing — limited requests allowed


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and a call is rejected."""


class CircuitBreaker:
    """
    Circuit breaker that wraps callables and prevents cascading failures.

    State machine::

        CLOSED  ──(failures >= threshold)──▶ OPEN
        OPEN    ──(recovery_timeout elapsed)──▶ HALF_OPEN
        HALF_OPEN ──(success)──▶ CLOSED
        HALF_OPEN ──(failure)──▶ OPEN

    Usage::

        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        try:
            result = cb.call(unreliable_function, arg1, arg2)
        except CircuitBreakerError:
            # Fallback logic
            ...
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        # State
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0

        # Observability
        self._stats = {
            "total_calls": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_rejected": 0,
            "times_opened": 0,
            "half_open_successes": 0,
            "half_open_failures": 0,
        }

    # ── Properties ───────────────────────────────────────────────────

    @property
    def state(self) -> CircuitBreakerState:
        """Current circuit state, with automatic OPEN → HALF_OPEN transition."""
        if self._state == CircuitBreakerState.OPEN:
            if time.time() - self._opened_at >= self._recovery_timeout:
                self._transition(CircuitBreakerState.HALF_OPEN)
        return self._state

    @property
    def name(self) -> str:
        return self._name

    # ── Core Call Wrapper ────────────────────────────────────────────

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute ``fn`` through the circuit breaker.

        Args:
            fn:     The callable to protect.
            *args:  Positional arguments forwarded to ``fn``.
            **kwargs: Keyword arguments forwarded to ``fn``.

        Returns:
            The return value of ``fn`` on success.

        Raises:
            CircuitBreakerError: If the circuit is OPEN.
            Exception:           Re-raises the original exception from ``fn``
                                 after recording the failure.
        """
        current_state = self.state  # triggers auto-transition check
        self._stats["total_calls"] += 1

        if current_state == CircuitBreakerState.OPEN:
            self._stats["total_rejected"] += 1
            logger.warning(
                "Circuit '%s' is OPEN — rejecting call (retry after %.1fs)",
                self._name, self._seconds_until_half_open(),
            )
            raise CircuitBreakerError(
                f"Circuit breaker '{self._name}' is open — "
                f"retry after {self._seconds_until_half_open():.1f}s"
            )

        if current_state == CircuitBreakerState.HALF_OPEN:
            if self._half_open_calls >= self._half_open_max_calls:
                self._stats["total_rejected"] += 1
                raise CircuitBreakerError(
                    f"Circuit breaker '{self._name}' half-open call limit reached"
                )
            self._half_open_calls += 1

        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure()
            raise

    # ── Manual Recording ─────────────────────────────────────────────

    def record_success(self) -> None:
        """Record a successful call — may close the circuit."""
        self._stats["total_successes"] += 1

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._stats["half_open_successes"] += 1
            self._success_count += 1
            logger.info(
                "Circuit '%s' HALF_OPEN success (%d/%d)",
                self._name, self._success_count, self._half_open_max_calls,
            )
            # After enough successes in half-open, close the circuit
            if self._success_count >= self._half_open_max_calls:
                self._transition(CircuitBreakerState.CLOSED)
        else:
            # In CLOSED state, reset consecutive failure counter
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call — may open the circuit."""
        self._stats["total_failures"] += 1
        self._last_failure_time = time.time()

        if self._state == CircuitBreakerState.HALF_OPEN:
            self._stats["half_open_failures"] += 1
            logger.warning("Circuit '%s' HALF_OPEN failure — reopening", self._name)
            self._transition(CircuitBreakerState.OPEN)
        else:
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                logger.warning(
                    "Circuit '%s' failure threshold reached (%d/%d) — opening",
                    self._name, self._failure_count, self._failure_threshold,
                )
                self._transition(CircuitBreakerState.OPEN)

    # ── Stats & Admin ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return circuit breaker statistics."""
        return {
            "name": self._name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout,
            "half_open_max_calls": self._half_open_max_calls,
            **self._stats,
        }

    def reset(self) -> None:
        """Reset to initial CLOSED state — for testing only."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0
        self._stats = {k: 0 for k in self._stats}

    # ── Internal ─────────────────────────────────────────────────────

    def _transition(self, new_state: CircuitBreakerState) -> None:
        """Transition to a new state with proper bookkeeping."""
        old_state = self._state
        self._state = new_state
        logger.info("Circuit '%s': %s → %s", self._name, old_state.value, new_state.value)

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
        """Seconds remaining before the circuit transitions to HALF_OPEN."""
        if self._state != CircuitBreakerState.OPEN:
            return 0.0
        elapsed = time.time() - self._opened_at
        remaining = self._recovery_timeout - elapsed
        return max(0.0, remaining)
