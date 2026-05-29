"""
SevaForge A2A (Agent-to-Agent) Protocol — US-036

Message-based communication framework for inter-agent coordination.
Supports point-to-point, broadcast, and topic-based pub/sub patterns.

Architecture:
    AgentA → A2AProtocol.send() → message queue → A2AProtocol.deliver() → AgentB
    AgentC ← A2AProtocol.subscribe("topic") ← broadcast
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class MessageType(str, Enum):
    """Types of inter-agent messages."""
    REQUEST = "request"          # Ask another agent to do something
    RESPONSE = "response"        # Reply to a request
    EVENT = "event"              # Fire-and-forget notification
    BROADCAST = "broadcast"      # Fan-out to all subscribers
    HANDOFF = "handoff"          # Transfer execution context
    HEARTBEAT = "heartbeat"      # Liveness signal


class MessagePriority(str, Enum):
    """Message delivery priority."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class DeliveryStatus(str, Enum):
    """Delivery tracking states."""
    QUEUED = "queued"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    EXPIRED = "expired"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class AgentMessage:
    """
    Envelope for agent-to-agent communication.

    Every message has a unique ID, source/target agent identifiers,
    typed payload, and delivery metadata.
    """
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_agent: str = ""
    target_agent: str = ""           # Empty = broadcast
    message_type: MessageType = MessageType.EVENT
    priority: MessagePriority = MessagePriority.NORMAL
    topic: str = ""                  # For pub/sub routing
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str = ""         # Links request/response pairs
    reply_to: str = ""               # Message ID this responds to
    ttl_seconds: int = 300           # Expires after 5 min
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: DeliveryStatus = DeliveryStatus.QUEUED
    metadata: dict[str, Any] = field(default_factory=dict)

    def create_reply(self, payload: dict[str, Any], source: str) -> AgentMessage:
        """Create a response message linked to this request."""
        return AgentMessage(
            source_agent=source,
            target_agent=self.source_agent,
            message_type=MessageType.RESPONSE,
            priority=self.priority,
            topic=self.topic,
            payload=payload,
            correlation_id=self.correlation_id or self.message_id,
            reply_to=self.message_id,
        )


@dataclass
class AgentEndpoint:
    """Registered agent in the A2A network."""
    agent_id: str
    name: str
    capabilities: list[str] = field(default_factory=list)
    subscriptions: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=datetime.utcnow)
    is_active: bool = True


# Type alias for message handlers
MessageHandler = Callable[[AgentMessage], Any]


# ── A2A Protocol ─────────────────────────────────────────────────────


class A2AProtocol:
    """
    Agent-to-Agent communication bus.

    Supports:
    - Point-to-point: send(target_agent, message)
    - Topic pub/sub: subscribe(topic), publish(topic, message)
    - Broadcast: broadcast(message)
    - Request/reply: request(target, payload) → response
    - Message history and delivery tracking
    """

    def __init__(self, max_history: int = 10000):
        self._agents: dict[str, AgentEndpoint] = {}
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._topic_subscribers: dict[str, set[str]] = defaultdict(set)
        self._inbox: dict[str, list[AgentMessage]] = defaultdict(list)
        self._history: list[AgentMessage] = []
        self._max_history = max_history
        self._pending_requests: dict[str, AgentMessage] = {}
        self._stats = {
            "messages_sent": 0,
            "messages_delivered": 0,
            "messages_failed": 0,
            "broadcasts": 0,
        }

    # ── Agent Registration ────────────────────────────────────────────

    def register_agent(
        self,
        agent_id: str,
        name: str,
        capabilities: list[str] | None = None,
        handler: MessageHandler | None = None,
    ) -> AgentEndpoint:
        """Register an agent on the communication bus."""
        endpoint = AgentEndpoint(
            agent_id=agent_id,
            name=name,
            capabilities=capabilities or [],
        )
        self._agents[agent_id] = endpoint
        if handler:
            self._handlers[agent_id].append(handler)
        logger.info("A2A: registered agent '%s' (%s)", agent_id, name)
        return endpoint

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the bus."""
        if agent_id in self._agents:
            self._agents[agent_id].is_active = False
            # Unsubscribe from all topics
            for topic, subs in self._topic_subscribers.items():
                subs.discard(agent_id)
            del self._agents[agent_id]
            logger.info("A2A: unregistered agent '%s'", agent_id)
            return True
        return False

    def list_agents(self) -> list[AgentEndpoint]:
        """Return all registered agents."""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> AgentEndpoint | None:
        """Lookup a specific agent."""
        return self._agents.get(agent_id)

    # ── Point-to-Point Messaging ──────────────────────────────────────

    def send(
        self,
        source: str,
        target: str,
        payload: dict[str, Any],
        message_type: MessageType = MessageType.EVENT,
        priority: MessagePriority = MessagePriority.NORMAL,
        topic: str = "",
        correlation_id: str = "",
    ) -> AgentMessage:
        """Send a message from one agent to another."""
        msg = AgentMessage(
            source_agent=source,
            target_agent=target,
            message_type=message_type,
            priority=priority,
            topic=topic,
            payload=payload,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        return self._enqueue(msg)

    def _enqueue(self, msg: AgentMessage) -> AgentMessage:
        """Put message in target inbox and invoke handlers."""
        target = msg.target_agent

        if target and target not in self._agents:
            msg.status = DeliveryStatus.FAILED
            self._stats["messages_failed"] += 1
            logger.warning("A2A: target '%s' not found, message %s failed", target, msg.message_id)
        else:
            self._inbox[target].append(msg)
            msg.status = DeliveryStatus.DELIVERED
            self._stats["messages_sent"] += 1
            self._stats["messages_delivered"] += 1

            # Invoke registered handlers
            for handler in self._handlers.get(target, []):
                try:
                    handler(msg)
                    msg.status = DeliveryStatus.ACKNOWLEDGED
                except Exception as e:
                    logger.error("A2A: handler error for '%s': %s", target, e)

        self._record(msg)
        return msg

    def receive(self, agent_id: str, limit: int = 50) -> list[AgentMessage]:
        """Drain inbox for an agent (oldest first)."""
        messages = self._inbox[agent_id][:limit]
        self._inbox[agent_id] = self._inbox[agent_id][limit:]
        return messages

    def peek(self, agent_id: str) -> int:
        """Return the number of pending messages for an agent."""
        return len(self._inbox.get(agent_id, []))

    # ── Pub/Sub ───────────────────────────────────────────────────────

    def subscribe(self, agent_id: str, topic: str) -> bool:
        """Subscribe an agent to a topic."""
        if agent_id not in self._agents:
            return False
        self._topic_subscribers[topic].add(agent_id)
        if topic not in self._agents[agent_id].subscriptions:
            self._agents[agent_id].subscriptions.append(topic)
        logger.debug("A2A: '%s' subscribed to '%s'", agent_id, topic)
        return True

    def unsubscribe(self, agent_id: str, topic: str) -> bool:
        """Unsubscribe an agent from a topic."""
        self._topic_subscribers[topic].discard(agent_id)
        if agent_id in self._agents and topic in self._agents[agent_id].subscriptions:
            self._agents[agent_id].subscriptions.remove(topic)
        return True

    def publish(
        self,
        source: str,
        topic: str,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> list[AgentMessage]:
        """Publish a message to all subscribers of a topic."""
        subscribers = self._topic_subscribers.get(topic, set())
        messages = []
        for sub_id in subscribers:
            if sub_id != source:  # Don't send to self
                msg = self.send(
                    source=source,
                    target=sub_id,
                    payload=payload,
                    message_type=MessageType.EVENT,
                    priority=priority,
                    topic=topic,
                )
                messages.append(msg)
        return messages

    def broadcast(
        self,
        source: str,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> list[AgentMessage]:
        """Send a message to ALL registered agents (except sender)."""
        messages = []
        self._stats["broadcasts"] += 1
        for agent_id in self._agents:
            if agent_id != source:
                msg = self.send(
                    source=source,
                    target=agent_id,
                    payload=payload,
                    message_type=MessageType.BROADCAST,
                    priority=priority,
                )
                messages.append(msg)
        return messages

    # ── Request / Reply ───────────────────────────────────────────────

    def request(
        self,
        source: str,
        target: str,
        payload: dict[str, Any],
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> AgentMessage:
        """Send a request and track it for reply matching."""
        msg = self.send(
            source=source,
            target=target,
            payload=payload,
            message_type=MessageType.REQUEST,
            priority=priority,
        )
        self._pending_requests[msg.correlation_id] = msg
        return msg

    def reply(
        self,
        original: AgentMessage,
        source: str,
        payload: dict[str, Any],
    ) -> AgentMessage:
        """Send a reply to a request message."""
        reply_msg = original.create_reply(payload=payload, source=source)
        self._enqueue(reply_msg)
        # Clear pending request
        self._pending_requests.pop(original.correlation_id, None)
        return reply_msg

    # ── Handoff ───────────────────────────────────────────────────────

    def handoff(
        self,
        source: str,
        target: str,
        context: dict[str, Any],
        reason: str = "",
    ) -> AgentMessage:
        """Transfer execution context from one agent to another."""
        return self.send(
            source=source,
            target=target,
            payload={"context": context, "reason": reason},
            message_type=MessageType.HANDOFF,
            priority=MessagePriority.HIGH,
        )

    # ── History & Stats ───────────────────────────────────────────────

    def _record(self, msg: AgentMessage) -> None:
        """Store message in history buffer."""
        self._history.append(msg)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(
        self,
        agent_id: str | None = None,
        topic: str | None = None,
        limit: int = 100,
    ) -> list[AgentMessage]:
        """Query message history with optional filters."""
        filtered = self._history
        if agent_id:
            filtered = [
                m for m in filtered
                if m.source_agent == agent_id or m.target_agent == agent_id
            ]
        if topic:
            filtered = [m for m in filtered if m.topic == topic]
        return filtered[-limit:]

    def stats(self) -> dict[str, Any]:
        """Return protocol-level statistics."""
        return {
            **self._stats,
            "registered_agents": len(self._agents),
            "active_topics": len(self._topic_subscribers),
            "pending_requests": len(self._pending_requests),
            "history_size": len(self._history),
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._agents.clear()
        self._handlers.clear()
        self._topic_subscribers.clear()
        self._inbox.clear()
        self._history.clear()
        self._pending_requests.clear()
        self._stats = {k: 0 for k in self._stats}
