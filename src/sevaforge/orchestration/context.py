"""
SevaForge Context Memory — US-038

Shared state and conversation history for agent chains.
Provides session-scoped memory that persists across agent handoffs,
enabling multi-turn reasoning and context-aware execution.

Architecture:
    Agent A → ContextMemory.store("key", value) → shared state
    Agent B → ContextMemory.get("key") → retrieves value
    Workflow → ContextMemory.get_session(id) → full session context
"""

from __future__ import annotations

import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "user"              # user, assistant, system, agent
    agent_id: str = ""              # Which agent produced this turn
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "role": self.role,
            "agent_id": self.agent_id,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SessionContext:
    """
    Full context for an active session.

    Combines:
    - Key-value shared state (agent outputs, config, intermediate results)
    - Ordered conversation history (multi-turn)
    - Session metadata (user, tenant, created/updated timestamps)
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "anonymous"
    tenant_id: str = "default"
    state: dict[str, Any] = field(default_factory=dict)
    history: list[ConversationTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def turn_count(self) -> int:
        return len(self.history)

    @property
    def agent_ids(self) -> list[str]:
        """Unique agents that contributed to this session."""
        seen = set()
        result = []
        for turn in self.history:
            if turn.agent_id and turn.agent_id not in seen:
                seen.add(turn.agent_id)
                result.append(turn.agent_id)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "state": self.state,
            "history": [t.to_dict() for t in self.history],
            "turn_count": self.turn_count,
            "agent_ids": self.agent_ids,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
        }


# ── Context Memory ───────────────────────────────────────────────────


class ContextMemory:
    """
    In-memory context store for agent sessions.

    Supports:
    - Session CRUD with auto-expiry
    - Key-value shared state per session
    - Conversation history with turn tracking
    - Context window management (sliding window over history)
    - Session search by user, tenant, or tags
    - LRU eviction when max sessions exceeded
    """

    def __init__(
        self,
        max_sessions: int = 10000,
        max_history_per_session: int = 200,
        default_ttl_seconds: int = 86400,
    ):
        self._sessions: OrderedDict[str, SessionContext] = OrderedDict()
        self._max_sessions = max_sessions
        self._max_history = max_history_per_session
        self._default_ttl = default_ttl_seconds
        self._stats = {
            "sessions_created": 0,
            "sessions_expired": 0,
            "total_turns": 0,
            "state_writes": 0,
            "state_reads": 0,
        }

    # ── Session Lifecycle ─────────────────────────────────────────────

    def create_session(
        self,
        user_id: str = "anonymous",
        tenant_id: str = "default",
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        session_id: str | None = None,
    ) -> SessionContext:
        """Create a new context session."""
        # LRU eviction
        while len(self._sessions) >= self._max_sessions:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.debug("ContextMemory: evicted session %s (LRU)", evicted_id)

        session = SessionContext(
            session_id=session_id or str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            metadata=metadata or {},
            tags=tags or [],
        )
        self._sessions[session.session_id] = session
        self._stats["sessions_created"] += 1
        logger.debug("ContextMemory: created session %s", session.session_id)
        return session

    def get_session(self, session_id: str) -> SessionContext | None:
        """Retrieve a session by ID (updates LRU position)."""
        session = self._sessions.get(session_id)
        if session:
            self._sessions.move_to_end(session_id)
        return session

    def delete_session(self, session_id: str) -> bool:
        """Remove a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(
        self,
        user_id: str | None = None,
        tenant_id: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> list[SessionContext]:
        """List sessions with optional filters."""
        sessions = list(self._sessions.values())
        if user_id:
            sessions = [s for s in sessions if s.user_id == user_id]
        if tenant_id:
            sessions = [s for s in sessions if s.tenant_id == tenant_id]
        if tag:
            sessions = [s for s in sessions if tag in s.tags]
        return sessions[-limit:]

    # ── Shared State ──────────────────────────────────────────────────

    def store(self, session_id: str, key: str, value: Any) -> bool:
        """Store a key-value pair in the session's shared state."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.state[key] = value
        session.updated_at = datetime.utcnow()
        self._stats["state_writes"] += 1
        return True

    def get(self, session_id: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from the session's shared state."""
        session = self.get_session(session_id)
        self._stats["state_reads"] += 1
        if not session:
            return default
        return session.state.get(key, default)

    def delete_key(self, session_id: str, key: str) -> bool:
        """Remove a key from the session's shared state."""
        session = self.get_session(session_id)
        if not session or key not in session.state:
            return False
        del session.state[key]
        session.updated_at = datetime.utcnow()
        return True

    def get_state(self, session_id: str) -> dict[str, Any]:
        """Return the full shared state dict for a session."""
        session = self.get_session(session_id)
        return session.state.copy() if session else {}

    def merge_state(self, session_id: str, updates: dict[str, Any]) -> bool:
        """Merge multiple key-value pairs into the session state."""
        session = self.get_session(session_id)
        if not session:
            return False
        session.state.update(updates)
        session.updated_at = datetime.utcnow()
        self._stats["state_writes"] += len(updates)
        return True

    # ── Conversation History ──────────────────────────────────────────

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ConversationTurn | None:
        """Append a conversation turn to the session history."""
        session = self.get_session(session_id)
        if not session:
            return None

        turn = ConversationTurn(
            role=role,
            content=content,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        session.history.append(turn)
        session.updated_at = datetime.utcnow()
        self._stats["total_turns"] += 1

        # Trim if over limit
        if len(session.history) > self._max_history:
            session.history = session.history[-self._max_history:]

        return turn

    def get_history(
        self,
        session_id: str,
        limit: int | None = None,
        agent_id: str | None = None,
    ) -> list[ConversationTurn]:
        """Retrieve conversation history with optional filters."""
        session = self.get_session(session_id)
        if not session:
            return []

        history = session.history
        if agent_id:
            history = [t for t in history if t.agent_id == agent_id]
        if limit:
            history = history[-limit:]
        return history

    def get_context_window(
        self,
        session_id: str,
        max_turns: int = 20,
        include_state: bool = True,
    ) -> dict[str, Any]:
        """
        Build a context window suitable for LLM input.

        Returns the most recent turns plus optionally the shared state,
        formatted for prompt assembly.
        """
        session = self.get_session(session_id)
        if not session:
            return {"history": [], "state": {}}

        recent = session.history[-max_turns:]
        window = {
            "session_id": session.session_id,
            "history": [
                {"role": t.role, "content": t.content, "agent": t.agent_id}
                for t in recent
            ],
        }
        if include_state:
            window["state"] = session.state.copy()
        return window

    # ── Session Fork / Merge ──────────────────────────────────────────

    def fork_session(
        self,
        session_id: str,
        new_user_id: str | None = None,
    ) -> SessionContext | None:
        """Create a copy of a session (for branching workflows)."""
        original = self.get_session(session_id)
        if not original:
            return None

        forked = self.create_session(
            user_id=new_user_id or original.user_id,
            tenant_id=original.tenant_id,
            metadata={**original.metadata, "forked_from": session_id},
            tags=[*original.tags, "forked"],
        )
        forked.state = original.state.copy()
        forked.history = list(original.history)
        return forked

    def merge_sessions(
        self,
        target_id: str,
        source_id: str,
        merge_state: bool = True,
        merge_history: bool = True,
    ) -> bool:
        """Merge source session state/history into target."""
        target = self.get_session(target_id)
        source = self.get_session(source_id)
        if not target or not source:
            return False

        if merge_state:
            for key, value in source.state.items():
                if key not in target.state:
                    target.state[key] = value

        if merge_history:
            target.history.extend(source.history)
            target.history.sort(key=lambda t: t.timestamp)
            if len(target.history) > self._max_history:
                target.history = target.history[-self._max_history:]

        target.updated_at = datetime.utcnow()
        return True

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "active_sessions": len(self._sessions),
            "max_sessions": self._max_sessions,
        }

    def reset(self) -> None:
        """Clear all sessions (for testing)."""
        self._sessions.clear()
        self._stats = {k: 0 for k in self._stats}
