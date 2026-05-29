"""
SevaForge Event Stream — US-048

Async event bus for decoupled inter-component communication.
Supports typed events, multiple subscribers, event replay,
and dead-letter tracking.

Architecture:
    Producer → EventBus.emit(event) → subscribers
    Consumer → EventBus.subscribe(type, handler)
    Replay  → EventBus.replay(from_id)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class EventType(str, Enum):
    # Execution lifecycle
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    # Agent events
    AGENT_REGISTERED = "agent.registered"
    AGENT_UNREGISTERED = "agent.unregistered"
    AGENT_HANDOFF = "agent.handoff"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_NODE_STARTED = "workflow.node.started"
    WORKFLOW_NODE_COMPLETED = "workflow.node.completed"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"

    # Cache events
    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"
    CACHE_EVICTION = "cache.eviction"

    # Knowledge events
    DOCUMENT_INDEXED = "knowledge.document.indexed"
    SEARCH_EXECUTED = "knowledge.search.executed"

    # System events
    HEALTH_CHECK = "system.health"
    CONFIG_CHANGED = "system.config.changed"
    RATE_LIMIT_HIT = "system.rate_limit"

    # Custom
    CUSTOM = "custom"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class Event:
    """An event in the event stream."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.CUSTOM
    source: str = ""                # Component that emitted this event
    data: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""        # Links related events
    tenant_id: str = "default"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "data": self.data,
            "correlation_id": self.correlation_id,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class EventSubscription:
    """A registered event subscriber."""
    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType | None = None  # None = subscribe to all
    handler_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    events_received: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscription_id": self.subscription_id,
            "event_type": self.event_type.value if self.event_type else "*",
            "handler_name": self.handler_name,
            "events_received": self.events_received,
            "errors": self.errors,
        }


# Type aliases
SyncHandler = Callable[[Event], None]
AsyncHandler = Callable[[Event], Any]  # Actually Awaitable[None]


# ── Event Bus ─────────────────────────────────────────────────────────


class EventBus:
    """
    In-memory event bus with typed subscriptions.

    Supports:
    - Typed event subscriptions (or wildcard)
    - Sync and async handlers
    - Event history with configurable retention
    - Dead-letter tracking for failed deliveries
    - Event replay from a specific point
    - Event filtering and querying
    """

    def __init__(self, max_history: int = 10000):
        self._sync_handlers: dict[str, list[tuple[EventSubscription, SyncHandler]]] = defaultdict(list)
        self._async_handlers: dict[str, list[tuple[EventSubscription, AsyncHandler]]] = defaultdict(list)
        self._history: list[Event] = []
        self._dead_letters: list[tuple[Event, str]] = []  # (event, error_msg)
        self._max_history = max_history
        self._stats = {
            "events_emitted": 0,
            "events_delivered": 0,
            "delivery_errors": 0,
        }

    # ── Subscribe ─────────────────────────────────────────────────────

    def subscribe(
        self,
        event_type: EventType | None,
        handler: SyncHandler,
        handler_name: str = "",
    ) -> EventSubscription:
        """Register a synchronous event handler."""
        sub = EventSubscription(
            event_type=event_type,
            handler_name=handler_name or handler.__name__,
        )
        key = event_type.value if event_type else "*"
        self._sync_handlers[key].append((sub, handler))
        return sub

    def subscribe_async(
        self,
        event_type: EventType | None,
        handler: AsyncHandler,
        handler_name: str = "",
    ) -> EventSubscription:
        """Register an asynchronous event handler."""
        sub = EventSubscription(
            event_type=event_type,
            handler_name=handler_name or getattr(handler, "__name__", "async_handler"),
        )
        key = event_type.value if event_type else "*"
        self._async_handlers[key].append((sub, handler))
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by ID."""
        for key in list(self._sync_handlers.keys()):
            self._sync_handlers[key] = [
                (sub, h) for sub, h in self._sync_handlers[key]
                if sub.subscription_id != subscription_id
            ]
        for key in list(self._async_handlers.keys()):
            self._async_handlers[key] = [
                (sub, h) for sub, h in self._async_handlers[key]
                if sub.subscription_id != subscription_id
            ]
        return True

    # ── Emit ──────────────────────────────────────────────────────────

    def emit(self, event: Event) -> int:
        """
        Emit an event synchronously.
        Returns the number of handlers that processed it.
        """
        self._record(event)
        self._stats["events_emitted"] += 1
        delivered = 0

        # Deliver to type-specific handlers
        key = event.event_type.value
        for sub, handler in self._sync_handlers.get(key, []):
            delivered += self._deliver_sync(event, sub, handler)

        # Deliver to wildcard handlers
        for sub, handler in self._sync_handlers.get("*", []):
            delivered += self._deliver_sync(event, sub, handler)

        self._stats["events_delivered"] += delivered
        return delivered

    async def emit_async(self, event: Event) -> int:
        """
        Emit an event asynchronously.
        Invokes both sync and async handlers.
        """
        self._record(event)
        self._stats["events_emitted"] += 1
        delivered = 0

        key = event.event_type.value

        # Sync handlers
        for sub, handler in self._sync_handlers.get(key, []):
            delivered += self._deliver_sync(event, sub, handler)
        for sub, handler in self._sync_handlers.get("*", []):
            delivered += self._deliver_sync(event, sub, handler)

        # Async handlers
        for sub, handler in self._async_handlers.get(key, []):
            delivered += await self._deliver_async(event, sub, handler)
        for sub, handler in self._async_handlers.get("*", []):
            delivered += await self._deliver_async(event, sub, handler)

        self._stats["events_delivered"] += delivered
        return delivered

    def _deliver_sync(self, event: Event, sub: EventSubscription, handler: SyncHandler) -> int:
        try:
            handler(event)
            sub.events_received += 1
            return 1
        except Exception as e:
            sub.errors += 1
            self._stats["delivery_errors"] += 1
            self._dead_letters.append((event, str(e)))
            logger.error("Event delivery error (%s): %s", sub.handler_name, e)
            return 0

    async def _deliver_async(self, event: Event, sub: EventSubscription, handler: AsyncHandler) -> int:
        try:
            await handler(event)
            sub.events_received += 1
            return 1
        except Exception as e:
            sub.errors += 1
            self._stats["delivery_errors"] += 1
            self._dead_letters.append((event, str(e)))
            logger.error("Async event delivery error (%s): %s", sub.handler_name, e)
            return 0

    # ── History & Replay ──────────────────────────────────────────────

    def _record(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(
        self,
        event_type: EventType | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query event history with filters."""
        events = self._history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if source:
            events = [e for e in events if e.source == source]
        if correlation_id:
            events = [e for e in events if e.correlation_id == correlation_id]
        return events[-limit:]

    def replay(
        self,
        from_event_id: str,
        handler: SyncHandler,
    ) -> int:
        """Replay events from a specific event ID onwards."""
        replaying = False
        count = 0
        for event in self._history:
            if event.event_id == from_event_id:
                replaying = True
            if replaying:
                try:
                    handler(event)
                    count += 1
                except Exception as e:
                    logger.error("Replay error at %s: %s", event.event_id, e)
        return count

    def dead_letters(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get failed delivery events."""
        return [
            {"event": e.to_dict(), "error": err}
            for e, err in self._dead_letters[-limit:]
        ]

    # ── Stats ─────────────────────────────────────────────────────────

    def subscriptions(self) -> list[dict[str, Any]]:
        """List all active subscriptions."""
        subs = []
        for handlers in self._sync_handlers.values():
            subs.extend(sub.to_dict() for sub, _ in handlers)
        for handlers in self._async_handlers.values():
            subs.extend(sub.to_dict() for sub, _ in handlers)
        return subs

    def stats(self) -> dict[str, Any]:
        sync_count = sum(len(h) for h in self._sync_handlers.values())
        async_count = sum(len(h) for h in self._async_handlers.values())
        return {
            **self._stats,
            "total_subscriptions": sync_count + async_count,
            "sync_handlers": sync_count,
            "async_handlers": async_count,
            "history_size": len(self._history),
            "dead_letters": len(self._dead_letters),
        }

    def reset(self) -> None:
        """Clear all state."""
        self._sync_handlers.clear()
        self._async_handlers.clear()
        self._history.clear()
        self._dead_letters.clear()
        self._stats = {k: 0 for k in self._stats}
