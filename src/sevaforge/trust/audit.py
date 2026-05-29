"""
SevaForge Audit Trail — US-064

Immutable, tamper-evident audit log for enterprise compliance.
Every significant action (create, read, update, delete, execute, grant,
revoke, etc.) is recorded with actor, resource, outcome, and a SHA-256
checksum for integrity verification.

Architecture:
    Action → AuditTrail.record() → AuditEntry (with checksum) → in-memory store
    Query  → AuditTrail.query(filters) → matching entries
    Verify → AuditTrail.verify_integrity(entry) → True/False
    Export → AuditTrail.export_entries(start, end) → JSON-serializable dicts
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class AuditAction(str, Enum):
    """Auditable action types."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"
    GRANT = "grant"
    REVOKE = "revoke"
    EXPORT = "export"
    IMPORT = "import"
    CONFIGURE = "configure"
    ALERT = "alert"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class AuditEntry:
    """
    A single immutable audit log entry.

    Once created, the entry's checksum seals its contents. Any
    subsequent modification will cause verify_integrity() to fail.

    Attributes:
        entry_id: Unique identifier (UUID) for this entry.
        timestamp: When the action occurred (UTC).
        action: The type of action performed.
        actor_id: Identifier of the user, agent, or system that performed the action.
        actor_type: Category of actor — "user", "agent", or "system".
        tenant_id: Multi-tenant isolation identifier.
        resource_type: The type of resource acted upon (e.g., "agent", "workflow").
        resource_id: Identifier of the specific resource.
        details: Free-form dict with action-specific details.
        outcome: Result of the action — "success", "failure", or "error".
        ip_address: IP address of the request origin (if applicable).
        trace_id: Correlation ID linking to the distributed trace.
        checksum: SHA-256 hash of the entry contents for tamper detection.
    """
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: AuditAction = AuditAction.READ
    actor_id: str = ""
    actor_type: str = "user"
    tenant_id: str = "default"
    resource_type: str = ""
    resource_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    outcome: str = "success"
    ip_address: str = ""
    trace_id: str = ""
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "tenant_id": self.tenant_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "outcome": self.outcome,
            "ip_address": self.ip_address,
            "trace_id": self.trace_id,
            "checksum": self.checksum,
        }


# ── Audit Trail ───────────────────────────────────────────────────────


class AuditTrail:
    """
    Immutable audit trail with checksum-based tamper detection.

    Supports:
    - Recording auditable actions with full context
    - SHA-256 checksums for integrity verification
    - Querying by actor, action, resource, tenant, and time range
    - Actor and resource history lookups
    - Compliance export in JSON-serializable format
    - In-memory storage with configurable capacity and LRU eviction

    Usage:
        audit = AuditTrail()
        entry = audit.record(
            action=AuditAction.EXECUTE,
            actor_id="user-123",
            actor_type="user",
            resource_type="agent",
            resource_id="code-review",
            details={"input_length": 500},
        )
        assert audit.verify_integrity(entry)
    """

    def __init__(self, max_entries: int = 100_000):
        self._entries: list[AuditEntry] = []
        self._index_by_id: dict[str, AuditEntry] = {}
        self._index_by_actor: dict[str, list[str]] = defaultdict(list)
        self._index_by_resource: dict[str, list[str]] = defaultdict(list)
        self._max_entries = max_entries

        self._stats = {
            "total_entries": 0,
            "entries_by_action": {a.value: 0 for a in AuditAction},
            "entries_by_outcome": {"success": 0, "failure": 0, "error": 0},
            "integrity_checks": 0,
        }

    # ── Recording ─────────────────────────────────────────────────────

    def record(
        self,
        action: AuditAction,
        actor_id: str,
        actor_type: str = "user",
        resource_type: str = "",
        resource_id: str = "",
        details: dict[str, Any] | None = None,
        outcome: str = "success",
        tenant_id: str = "default",
        ip_address: str = "",
        trace_id: str = "",
    ) -> AuditEntry:
        """
        Record an auditable action.

        Creates an AuditEntry with a SHA-256 checksum computed from
        the entry's content fields. The entry is stored in the in-memory
        log and indexed for fast lookups.

        Args:
            action: The type of action being recorded.
            actor_id: Who performed the action.
            actor_type: Category of actor ("user", "agent", "system").
            resource_type: What type of resource was acted upon.
            resource_id: Which specific resource.
            details: Additional action-specific details.
            outcome: "success", "failure", or "error".
            tenant_id: Tenant identifier for multi-tenancy.
            ip_address: Origin IP address.
            trace_id: Distributed trace correlation ID.

        Returns:
            The created AuditEntry with its sealed checksum.
        """
        entry = AuditEntry(
            action=action,
            actor_id=actor_id,
            actor_type=actor_type,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            outcome=outcome,
            ip_address=ip_address,
            trace_id=trace_id,
        )

        # Seal the entry with a checksum
        entry.checksum = self._compute_checksum(entry)

        # Store
        self._entries.append(entry)
        self._index_by_id[entry.entry_id] = entry
        self._index_by_actor[entry.actor_id].append(entry.entry_id)

        resource_key = f"{resource_type}:{resource_id}"
        self._index_by_resource[resource_key].append(entry.entry_id)

        # Update stats
        self._stats["total_entries"] += 1
        self._stats["entries_by_action"][action.value] = (
            self._stats["entries_by_action"].get(action.value, 0) + 1
        )
        self._stats["entries_by_outcome"][outcome] = (
            self._stats["entries_by_outcome"].get(outcome, 0) + 1
        )

        # Evict oldest entries if over capacity
        if len(self._entries) > self._max_entries:
            self._evict(len(self._entries) - self._max_entries)

        logger.debug(
            "Audit: recorded %s by %s (%s) on %s/%s → %s",
            action.value, actor_id, actor_type, resource_type, resource_id, outcome,
        )

        return entry

    # ── Checksum ──────────────────────────────────────────────────────

    @staticmethod
    def _compute_checksum(entry: AuditEntry) -> str:
        """
        Compute a SHA-256 checksum of the entry's content fields.

        The checksum covers all content fields except the checksum itself,
        providing tamper detection. The fields are serialized in a
        deterministic order with sorted JSON keys.
        """
        content = {
            "entry_id": entry.entry_id,
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action.value,
            "actor_id": entry.actor_id,
            "actor_type": entry.actor_type,
            "tenant_id": entry.tenant_id,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "details": entry.details,
            "outcome": entry.outcome,
            "ip_address": entry.ip_address,
            "trace_id": entry.trace_id,
        }
        serialized = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def verify_integrity(self, entry: AuditEntry) -> bool:
        """
        Verify that an audit entry has not been tampered with.

        Recomputes the SHA-256 checksum and compares it to the stored
        value. Returns True if the entry is intact.

        Args:
            entry: The AuditEntry to verify.

        Returns:
            True if the recomputed checksum matches the stored checksum.
        """
        self._stats["integrity_checks"] += 1
        expected = self._compute_checksum(entry)
        is_valid = expected == entry.checksum

        if not is_valid:
            logger.warning(
                "Audit: integrity check FAILED for entry %s "
                "(expected=%s, actual=%s)",
                entry.entry_id, expected[:16], entry.checksum[:16],
            )

        return is_valid

    # ── Querying ──────────────────────────────────────────────────────

    def query(
        self,
        actor_id: str | None = None,
        action: AuditAction | None = None,
        resource_type: str | None = None,
        tenant_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """
        Query audit entries with optional filters.

        All filters are AND-combined. Results are returned in reverse
        chronological order (most recent first), up to `limit`.

        Args:
            actor_id: Filter by actor.
            action: Filter by action type.
            resource_type: Filter by resource type.
            tenant_id: Filter by tenant.
            start_time: Only entries at or after this time.
            end_time: Only entries at or before this time.
            outcome: Filter by outcome ("success", "failure", "error").
            limit: Maximum number of entries to return.

        Returns:
            List of matching AuditEntry objects.
        """
        results = self._entries

        if actor_id is not None:
            entry_ids = set(self._index_by_actor.get(actor_id, []))
            results = [e for e in results if e.entry_id in entry_ids]
        if action is not None:
            results = [e for e in results if e.action == action]
        if resource_type is not None:
            results = [e for e in results if e.resource_type == resource_type]
        if tenant_id is not None:
            results = [e for e in results if e.tenant_id == tenant_id]
        if outcome is not None:
            results = [e for e in results if e.outcome == outcome]
        if start_time is not None:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time is not None:
            results = [e for e in results if e.timestamp <= end_time]

        # Return most recent first
        return list(reversed(results[-limit:]))

    def get_entry(self, entry_id: str) -> AuditEntry | None:
        """
        Look up a single audit entry by its ID.

        Args:
            entry_id: The UUID of the entry.

        Returns:
            The AuditEntry, or None if not found.
        """
        return self._index_by_id.get(entry_id)

    def get_actor_history(
        self,
        actor_id: str,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """
        Retrieve the action history for a specific actor.

        Args:
            actor_id: The actor whose history to retrieve.
            limit: Maximum number of entries.

        Returns:
            List of AuditEntry objects, most recent first.
        """
        entry_ids = self._index_by_actor.get(actor_id, [])
        entries = [
            self._index_by_id[eid]
            for eid in entry_ids
            if eid in self._index_by_id
        ]
        return list(reversed(entries[-limit:]))

    def get_resource_history(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """
        Retrieve the action history for a specific resource.

        Args:
            resource_type: The type of resource.
            resource_id: The specific resource identifier.
            limit: Maximum number of entries.

        Returns:
            List of AuditEntry objects, most recent first.
        """
        resource_key = f"{resource_type}:{resource_id}"
        entry_ids = self._index_by_resource.get(resource_key, [])
        entries = [
            self._index_by_id[eid]
            for eid in entry_ids
            if eid in self._index_by_id
        ]
        return list(reversed(entries[-limit:]))

    # ── Export ────────────────────────────────────────────────────────

    def export_entries(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict[str, Any]]:
        """
        Export audit entries within a time range for compliance reporting.

        Returns entries as JSON-serializable dicts suitable for archival
        or external compliance systems.

        Args:
            start_time: Start of the export window (inclusive).
            end_time: End of the export window (inclusive).

        Returns:
            List of serialized audit entry dicts.
        """
        entries = [
            e for e in self._entries
            if start_time <= e.timestamp <= end_time
        ]

        logger.info(
            "Audit: exporting %d entries from %s to %s",
            len(entries), start_time.isoformat(), end_time.isoformat(),
        )

        return [entry.to_dict() for entry in entries]

    # ── Eviction ──────────────────────────────────────────────────────

    def _evict(self, count: int) -> None:
        """
        Remove the oldest `count` entries to stay within capacity.

        Cleans up both the main list and all indexes.
        """
        evicted = self._entries[:count]
        self._entries = self._entries[count:]

        for entry in evicted:
            # Remove from ID index
            self._index_by_id.pop(entry.entry_id, None)

            # Remove from actor index
            actor_ids = self._index_by_actor.get(entry.actor_id, [])
            if entry.entry_id in actor_ids:
                actor_ids.remove(entry.entry_id)
            if not actor_ids:
                self._index_by_actor.pop(entry.actor_id, None)

            # Remove from resource index
            resource_key = f"{entry.resource_type}:{entry.resource_id}"
            resource_ids = self._index_by_resource.get(resource_key, [])
            if entry.entry_id in resource_ids:
                resource_ids.remove(entry.entry_id)
            if not resource_ids:
                self._index_by_resource.pop(resource_key, None)

        logger.debug("Audit: evicted %d oldest entries", count)

    # ── Stats & Reset ─────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return audit trail statistics."""
        return {
            **self._stats,
            "stored_entries": len(self._entries),
            "max_entries": self._max_entries,
            "unique_actors": len(self._index_by_actor),
            "unique_resources": len(self._index_by_resource),
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._entries.clear()
        self._index_by_id.clear()
        self._index_by_actor.clear()
        self._index_by_resource.clear()
        self._stats = {
            "total_entries": 0,
            "entries_by_action": {a.value: 0 for a in AuditAction},
            "entries_by_outcome": {"success": 0, "failure": 0, "error": 0},
            "integrity_checks": 0,
        }
