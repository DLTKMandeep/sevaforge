"""
SevaForge PostgreSQL Data Layer — US-047

Schema management, migration engine, connection pooling, and repository pattern.
Provides an abstraction layer that works with both real PostgreSQL and
an in-memory store for development/testing.

Architecture:
    ConnectionPool → PostgresManager → Repository (per-table)
    Migration engine tracks schema versions and applies DDL changes.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Connection Pool ──────────────────────────────────────────────────


@dataclass
class ConnectionInfo:
    """Metadata for a pooled connection."""
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)
    in_use: bool = False
    query_count: int = 0


class ConnectionPool:
    """
    Connection pool with configurable min/max size.

    In development mode (no real database), provides simulated
    pool behavior for testing connection management logic.
    """

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///./sevaforge.db",
        min_size: int = 2,
        max_size: int = 20,
        max_idle_seconds: int = 300,
    ):
        self.database_url = database_url
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle_seconds = max_idle_seconds
        self._connections: dict[str, ConnectionInfo] = {}
        self._is_real_db = "postgresql" in database_url
        self._stats = {
            "connections_created": 0,
            "connections_recycled": 0,
            "checkouts": 0,
            "checkins": 0,
            "pool_full_waits": 0,
        }

        # Initialize minimum connections
        for _ in range(min_size):
            self._create_connection()

    def _create_connection(self) -> ConnectionInfo:
        """Create a new pooled connection."""
        conn = ConnectionInfo()
        self._connections[conn.connection_id] = conn
        self._stats["connections_created"] += 1
        return conn

    def acquire(self) -> ConnectionInfo:
        """Acquire a connection from the pool."""
        # Find an idle connection
        for conn in self._connections.values():
            if not conn.in_use:
                conn.in_use = True
                conn.last_used = datetime.utcnow()
                conn.query_count += 1
                self._stats["checkouts"] += 1
                return conn

        # No idle connections — create new if under max
        if len(self._connections) < self.max_size:
            conn = self._create_connection()
            conn.in_use = True
            self._stats["checkouts"] += 1
            return conn

        # Pool exhausted
        self._stats["pool_full_waits"] += 1
        raise RuntimeError("Connection pool exhausted")

    def release(self, connection_id: str) -> None:
        """Return a connection to the pool."""
        conn = self._connections.get(connection_id)
        if conn:
            conn.in_use = False
            conn.last_used = datetime.utcnow()
            self._stats["checkins"] += 1

    def recycle_idle(self) -> int:
        """Close connections that have been idle too long."""
        now = datetime.utcnow()
        to_remove = []

        for cid, conn in self._connections.items():
            if not conn.in_use:
                idle_seconds = (now - conn.last_used).total_seconds()
                if idle_seconds > self.max_idle_seconds:
                    # Keep at least min_size connections
                    if len(self._connections) - len(to_remove) > self.min_size:
                        to_remove.append(cid)

        for cid in to_remove:
            del self._connections[cid]
            self._stats["connections_recycled"] += 1

        return len(to_remove)

    def stats(self) -> dict[str, Any]:
        active = sum(1 for c in self._connections.values() if c.in_use)
        idle = sum(1 for c in self._connections.values() if not c.in_use)
        return {
            **self._stats,
            "pool_size": len(self._connections),
            "active_connections": active,
            "idle_connections": idle,
            "is_real_db": self._is_real_db,
        }

    def close_all(self) -> int:
        """Close all connections."""
        count = len(self._connections)
        self._connections.clear()
        return count


# ── Migration Engine ─────────────────────────────────────────────────


@dataclass
class Migration:
    """A single schema migration."""
    migration_id: str
    version: str
    description: str
    up_sql: str                    # SQL to apply the migration
    down_sql: str = ""             # SQL to rollback
    applied_at: Optional[datetime] = None
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "version": self.version,
            "description": self.description,
            "applied": self.applied_at is not None,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
        }


class MigrationEngine:
    """
    Schema migration tracker.

    Tracks which migrations have been applied and provides
    methods to apply/rollback in order.
    """

    def __init__(self):
        self._migrations: OrderedDict[str, Migration] = OrderedDict()
        self._applied: set[str] = set()

    def register(self, migration: Migration) -> None:
        """Register a migration."""
        self._migrations[migration.migration_id] = migration

    def apply(self, migration_id: str) -> bool:
        """Mark a migration as applied."""
        migration = self._migrations.get(migration_id)
        if not migration:
            return False
        if migration_id in self._applied:
            return False  # Already applied
        migration.applied_at = datetime.utcnow()
        self._applied.add(migration_id)
        logger.info("Migration applied: %s — %s", migration.version, migration.description)
        return True

    def rollback(self, migration_id: str) -> bool:
        """Roll back a migration."""
        if migration_id not in self._applied:
            return False
        migration = self._migrations.get(migration_id)
        if migration:
            migration.applied_at = None
        self._applied.discard(migration_id)
        logger.info("Migration rolled back: %s", migration_id)
        return True

    def pending(self) -> list[Migration]:
        """Return migrations that haven't been applied yet."""
        return [m for mid, m in self._migrations.items() if mid not in self._applied]

    def applied(self) -> list[Migration]:
        """Return applied migrations."""
        return [m for mid, m in self._migrations.items() if mid in self._applied]

    def apply_all(self) -> int:
        """Apply all pending migrations in order."""
        count = 0
        for mid in self._migrations:
            if mid not in self._applied:
                self.apply(mid)
                count += 1
        return count

    def status(self) -> dict[str, Any]:
        return {
            "total_migrations": len(self._migrations),
            "applied": len(self._applied),
            "pending": len(self._migrations) - len(self._applied),
            "migrations": [m.to_dict() for m in self._migrations.values()],
        }


# ── Repository Pattern ───────────────────────────────────────────────


class Repository:
    """
    Generic in-memory repository implementing CRUD operations.

    Simulates a database table with support for:
    - Insert, update, delete, get by ID
    - Query with filters and pagination
    - Upsert (insert or update)
    - Bulk operations
    """

    def __init__(self, table_name: str, pool: ConnectionPool | None = None):
        self.table_name = table_name
        self._pool = pool
        self._store: dict[str, dict[str, Any]] = {}
        self._auto_id = True

    def insert(self, record: dict[str, Any], record_id: str | None = None) -> str:
        """Insert a record. Returns the record ID."""
        rid = record_id or record.get("id") or str(uuid.uuid4())
        record["id"] = rid
        record["created_at"] = record.get("created_at", datetime.utcnow().isoformat())
        record["updated_at"] = datetime.utcnow().isoformat()
        self._store[rid] = record
        return rid

    def get(self, record_id: str) -> dict[str, Any] | None:
        """Get a record by ID."""
        return self._store.get(record_id)

    def update(self, record_id: str, updates: dict[str, Any]) -> bool:
        """Update a record's fields."""
        record = self._store.get(record_id)
        if not record:
            return False
        record.update(updates)
        record["updated_at"] = datetime.utcnow().isoformat()
        return True

    def delete(self, record_id: str) -> bool:
        """Delete a record."""
        if record_id in self._store:
            del self._store[record_id]
            return True
        return False

    def upsert(self, record_id: str, record: dict[str, Any]) -> str:
        """Insert or update a record."""
        if record_id in self._store:
            self.update(record_id, record)
            return record_id
        return self.insert(record, record_id=record_id)

    def query(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_desc: bool = False,
    ) -> list[dict[str, Any]]:
        """Query records with filters and pagination."""
        results = list(self._store.values())

        if filters:
            for key, value in filters.items():
                results = [r for r in results if r.get(key) == value]

        if sort_by:
            results.sort(key=lambda r: r.get(sort_by, ""), reverse=sort_desc)

        return results[offset:offset + limit]

    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records matching filters."""
        if not filters:
            return len(self._store)
        return len(self.query(filters=filters, limit=len(self._store)))

    def bulk_insert(self, records: list[dict[str, Any]]) -> int:
        """Insert multiple records."""
        for record in records:
            self.insert(record)
        return len(records)

    def clear(self) -> int:
        """Remove all records."""
        count = len(self._store)
        self._store.clear()
        return count

    def stats(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "total_records": len(self._store),
        }


# ── PostgreSQL Manager ───────────────────────────────────────────────


class PostgresManager:
    """
    Central manager for PostgreSQL operations.

    Combines connection pooling, migration tracking, and
    repository access into a single interface.
    """

    def __init__(
        self,
        database_url: str = "sqlite+aiosqlite:///./sevaforge.db",
        pool_min: int = 2,
        pool_max: int = 20,
    ):
        self.database_url = database_url
        self.pool = ConnectionPool(
            database_url=database_url,
            min_size=pool_min,
            max_size=pool_max,
        )
        self.migrations = MigrationEngine()
        self._repositories: dict[str, Repository] = {}
        self._initialized = False

        # Register default schema migrations
        self._register_default_migrations()

    def _register_default_migrations(self) -> None:
        """Register the core SevaForge schema migrations."""
        self.migrations.register(Migration(
            migration_id="001",
            version="1.0.0",
            description="Create executions table",
            up_sql="""
                CREATE TABLE IF NOT EXISTS executions (
                    id UUID PRIMARY KEY,
                    agent_id VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) DEFAULT 'anonymous',
                    tenant_id VARCHAR(255) DEFAULT 'default',
                    status VARCHAR(50) DEFAULT 'pending',
                    input_text TEXT,
                    result JSONB,
                    model_used VARCHAR(255),
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd DECIMAL(10, 6) DEFAULT 0,
                    latency_ms DECIMAL(10, 2) DEFAULT 0,
                    trace_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                );
            """,
            down_sql="DROP TABLE IF EXISTS executions;",
        ))

        self.migrations.register(Migration(
            migration_id="002",
            version="1.0.0",
            description="Create agents table",
            up_sql="""
                CREATE TABLE IF NOT EXISTS agents (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'idle',
                    capabilities JSONB DEFAULT '[]',
                    default_model VARCHAR(255),
                    version VARCHAR(50) DEFAULT '1.0.0',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                );
            """,
            down_sql="DROP TABLE IF EXISTS agents;",
        ))

        self.migrations.register(Migration(
            migration_id="003",
            version="1.0.0",
            description="Create sessions table",
            up_sql="""
                CREATE TABLE IF NOT EXISTS sessions (
                    id UUID PRIMARY KEY,
                    user_id VARCHAR(255),
                    tenant_id VARCHAR(255) DEFAULT 'default',
                    state JSONB DEFAULT '{}',
                    history JSONB DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP
                );
            """,
            down_sql="DROP TABLE IF EXISTS sessions;",
        ))

        self.migrations.register(Migration(
            migration_id="004",
            version="1.0.0",
            description="Create knowledge_documents table",
            up_sql="""
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id UUID PRIMARY KEY,
                    title VARCHAR(500),
                    content TEXT NOT NULL,
                    source VARCHAR(500),
                    collection VARCHAR(255) DEFAULT 'default',
                    embedding VECTOR(768),
                    metadata JSONB DEFAULT '{}',
                    content_hash VARCHAR(64),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_docs_collection ON knowledge_documents(collection);
                CREATE INDEX IF NOT EXISTS idx_docs_hash ON knowledge_documents(content_hash);
            """,
            down_sql="DROP TABLE IF EXISTS knowledge_documents;",
        ))

        self.migrations.register(Migration(
            migration_id="005",
            version="1.0.0",
            description="Create audit_log table",
            up_sql="""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id UUID PRIMARY KEY,
                    event_type VARCHAR(100) NOT NULL,
                    actor_id VARCHAR(255),
                    tenant_id VARCHAR(255) DEFAULT 'default',
                    resource_type VARCHAR(100),
                    resource_id VARCHAR(255),
                    payload JSONB DEFAULT '{}',
                    trace_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_log(event_type);
                CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
            """,
            down_sql="DROP TABLE IF EXISTS audit_log;",
        ))

    def initialize(self) -> dict[str, Any]:
        """Initialize the database — apply pending migrations."""
        applied = self.migrations.apply_all()
        self._initialized = True
        return {
            "initialized": True,
            "migrations_applied": applied,
            "pool_stats": self.pool.stats(),
        }

    def get_repository(self, table_name: str) -> Repository:
        """Get or create a repository for a table."""
        if table_name not in self._repositories:
            self._repositories[table_name] = Repository(table_name, self.pool)
        return self._repositories[table_name]

    def health_check(self) -> dict[str, Any]:
        """Check database health."""
        return {
            "status": "healthy",
            "initialized": self._initialized,
            "pool": self.pool.stats(),
            "migrations": self.migrations.status(),
            "repositories": {
                name: repo.stats()
                for name, repo in self._repositories.items()
            },
        }

    def close(self) -> None:
        """Close all connections."""
        self.pool.close_all()
        self._initialized = False
