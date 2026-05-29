"""
SevaForge Redis Client — US-048

Session state management, pub/sub messaging, and rate limiting.
Provides an in-memory implementation that mirrors Redis semantics
for development and testing without a running Redis instance.

Architecture:
    RedisManager → SessionStore (hash-based session data)
                 → RateLimiter (token bucket per key)
                 → PubSubBroker (channel-based messaging)
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Session Store ────────────────────────────────────────────────────


class SessionStore:
    """
    Redis-like hash-based session storage.

    Simulates Redis HSET/HGET/HDEL/HGETALL with TTL support.
    Each session is a hash (dict of fields), identified by a key.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._store: dict[str, dict[str, Any]] = {}
        self._ttls: dict[str, float] = {}  # key → expiry timestamp
        self._default_ttl = default_ttl_seconds

    def set(self, key: str, field_name: str, value: Any, ttl: int | None = None) -> None:
        """Set a field in a session hash (HSET)."""
        if key not in self._store:
            self._store[key] = {}
        self._store[key][field_name] = value
        self._ttls[key] = time.time() + (ttl or self._default_ttl)

    def get(self, key: str, field_name: str) -> Any | None:
        """Get a field from a session hash (HGET)."""
        if self._is_expired(key):
            self._expire(key)
            return None
        return self._store.get(key, {}).get(field_name)

    def get_all(self, key: str) -> dict[str, Any]:
        """Get all fields of a session hash (HGETALL)."""
        if self._is_expired(key):
            self._expire(key)
            return {}
        return dict(self._store.get(key, {}))

    def delete_field(self, key: str, field_name: str) -> bool:
        """Delete a field from a session hash (HDEL)."""
        if key in self._store and field_name in self._store[key]:
            del self._store[key][field_name]
            return True
        return False

    def delete(self, key: str) -> bool:
        """Delete an entire session hash (DEL)."""
        if key in self._store:
            del self._store[key]
            self._ttls.pop(key, None)
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if a key exists and hasn't expired."""
        if self._is_expired(key):
            self._expire(key)
            return False
        return key in self._store

    def set_ttl(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on a key (EXPIRE)."""
        if key in self._store:
            self._ttls[key] = time.time() + ttl_seconds
            return True
        return False

    def ttl(self, key: str) -> float:
        """Get remaining TTL in seconds."""
        if key not in self._ttls:
            return -1
        remaining = self._ttls[key] - time.time()
        return max(0, remaining)

    def keys(self, pattern: str = "*") -> list[str]:
        """List keys matching pattern (simplified KEYS)."""
        self._cleanup_expired()
        if pattern == "*":
            return list(self._store.keys())
        # Simple prefix match
        prefix = pattern.rstrip("*")
        return [k for k in self._store.keys() if k.startswith(prefix)]

    def _is_expired(self, key: str) -> bool:
        return key in self._ttls and time.time() > self._ttls[key]

    def _expire(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttls.pop(key, None)

    def _cleanup_expired(self) -> int:
        expired = [k for k in list(self._ttls) if self._is_expired(k)]
        for k in expired:
            self._expire(k)
        return len(expired)

    def flush(self) -> int:
        """Clear all data (FLUSHDB)."""
        count = len(self._store)
        self._store.clear()
        self._ttls.clear()
        return count

    def stats(self) -> dict[str, Any]:
        self._cleanup_expired()
        return {
            "total_keys": len(self._store),
            "total_fields": sum(len(v) for v in self._store.values()),
        }


# ── Rate Limiter ─────────────────────────────────────────────────────


@dataclass
class RateLimitEntry:
    """Tracking state for a rate-limited key."""
    tokens: float
    last_refill: float
    total_requests: int = 0
    total_rejected: int = 0


class RateLimiter:
    """
    Token bucket rate limiter.

    Each key (e.g., user_id, API key, IP) gets a bucket with
    a maximum capacity that refills at a constant rate.
    """

    def __init__(
        self,
        max_tokens: int = 100,
        refill_rate: float = 10.0,   # tokens per second
        window_seconds: int = 60,
    ):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.window_seconds = window_seconds
        self._buckets: dict[str, RateLimitEntry] = {}

    def allow(self, key: str, cost: int = 1) -> bool:
        """
        Check if a request is allowed under the rate limit.

        Returns True if allowed (tokens consumed), False if rate limited.
        """
        now = time.time()
        entry = self._get_or_create(key, now)
        self._refill(entry, now)

        entry.total_requests += 1
        if entry.tokens >= cost:
            entry.tokens -= cost
            return True

        entry.total_rejected += 1
        return False

    def remaining(self, key: str) -> int:
        """Return remaining tokens for a key."""
        now = time.time()
        entry = self._get_or_create(key, now)
        self._refill(entry, now)
        return int(entry.tokens)

    def reset(self, key: str) -> None:
        """Reset a key's bucket to full."""
        self._buckets[key] = RateLimitEntry(
            tokens=float(self.max_tokens),
            last_refill=time.time(),
        )

    def _get_or_create(self, key: str, now: float) -> RateLimitEntry:
        if key not in self._buckets:
            self._buckets[key] = RateLimitEntry(
                tokens=float(self.max_tokens),
                last_refill=now,
            )
        return self._buckets[key]

    def _refill(self, entry: RateLimitEntry, now: float) -> None:
        elapsed = now - entry.last_refill
        entry.tokens = min(
            float(self.max_tokens),
            entry.tokens + elapsed * self.refill_rate,
        )
        entry.last_refill = now

    def stats(self) -> dict[str, Any]:
        total_req = sum(e.total_requests for e in self._buckets.values())
        total_rej = sum(e.total_rejected for e in self._buckets.values())
        return {
            "tracked_keys": len(self._buckets),
            "total_requests": total_req,
            "total_rejected": total_rej,
            "rejection_rate": total_rej / max(total_req, 1),
            "max_tokens": self.max_tokens,
            "refill_rate": self.refill_rate,
        }

    def flush(self) -> None:
        self._buckets.clear()


# ── Pub/Sub Broker ───────────────────────────────────────────────────


MessageCallback = Callable[[str, Any], None]


@dataclass
class PubSubMessage:
    """A published message."""
    channel: str
    data: Any
    published_at: float = field(default_factory=time.time)
    publisher: str = ""


class PubSubBroker:
    """
    Redis-like publish/subscribe message broker.

    Supports channel-based messaging with pattern subscriptions.
    """

    def __init__(self, max_history: int = 1000):
        self._subscribers: dict[str, list[MessageCallback]] = defaultdict(list)
        self._history: list[PubSubMessage] = []
        self._max_history = max_history
        self._stats = {
            "messages_published": 0,
            "messages_delivered": 0,
            "total_subscribers": 0,
        }

    def subscribe(self, channel: str, callback: MessageCallback) -> None:
        """Subscribe to a channel."""
        self._subscribers[channel].append(callback)
        self._stats["total_subscribers"] += 1

    def unsubscribe(self, channel: str, callback: MessageCallback) -> bool:
        """Unsubscribe from a channel."""
        if callback in self._subscribers.get(channel, []):
            self._subscribers[channel].remove(callback)
            return True
        return False

    def publish(self, channel: str, data: Any, publisher: str = "") -> int:
        """
        Publish a message to a channel.
        Returns the number of subscribers that received it.
        """
        msg = PubSubMessage(channel=channel, data=data, publisher=publisher)
        self._history.append(msg)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._stats["messages_published"] += 1
        delivered = 0

        for callback in self._subscribers.get(channel, []):
            try:
                callback(channel, data)
                delivered += 1
            except Exception as e:
                logger.error("PubSub delivery error on '%s': %s", channel, e)

        self._stats["messages_delivered"] += delivered
        return delivered

    def channels(self) -> list[str]:
        """List active channels (with subscribers)."""
        return [ch for ch, subs in self._subscribers.items() if subs]

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, []))

    def history(self, channel: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Get message history."""
        msgs = self._history
        if channel:
            msgs = [m for m in msgs if m.channel == channel]
        return [
            {"channel": m.channel, "data": m.data, "publisher": m.publisher}
            for m in msgs[-limit:]
        ]

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "active_channels": len(self.channels()),
            "history_size": len(self._history),
        }

    def flush(self) -> None:
        self._subscribers.clear()
        self._history.clear()
        self._stats = {k: 0 for k in self._stats}


# ── Redis Manager ────────────────────────────────────────────────────


class RedisManager:
    """
    Central Redis manager combining session store, rate limiter, and pub/sub.

    In development mode (no real Redis), everything runs in-memory.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        session_ttl: int = 3600,
        rate_limit_max: int = 100,
        rate_limit_refill: float = 10.0,
    ):
        self.redis_url = redis_url
        self._is_real_redis = redis_url.startswith("redis://") and "localhost" not in redis_url
        self.sessions = SessionStore(default_ttl_seconds=session_ttl)
        self.rate_limiter = RateLimiter(
            max_tokens=rate_limit_max,
            refill_rate=rate_limit_refill,
        )
        self.pubsub = PubSubBroker()

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "is_real_redis": self._is_real_redis,
            "sessions": self.sessions.stats(),
            "rate_limiter": self.rate_limiter.stats(),
            "pubsub": self.pubsub.stats(),
        }

    def flush_all(self) -> dict[str, int]:
        """Clear all data."""
        return {
            "sessions_cleared": self.sessions.flush(),
            "rate_limits_cleared": 0,  # flush doesn't return count
            "pubsub_cleared": 0,
        }
