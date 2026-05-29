"""
Tests for Data Layer (Layer 8): PostgreSQL, Redis, Event Stream.
"""

import time

import pytest

from sevaforge.data.postgres import ConnectionPool, MigrationEngine, Migration, PostgresManager, Repository
from sevaforge.data.redis_client import RedisManager, SessionStore, RateLimiter, PubSubBroker
from sevaforge.data.event_stream import EventBus, Event, EventType


# ══════════════════════════════════════════════════════════════════════
# Connection Pool Tests
# ══════════════════════════════════════════════════════════════════════


class TestConnectionPool:
    def test_create_pool(self):
        pool = ConnectionPool(min_size=2, max_size=5)
        stats = pool.stats()
        assert stats["pool_size"] == 2

    def test_acquire_release(self):
        pool = ConnectionPool(min_size=1, max_size=3)
        conn = pool.acquire()
        assert conn.in_use is True
        pool.release(conn.connection_id)
        stats = pool.stats()
        assert stats["checkouts"] == 1
        assert stats["checkins"] == 1

    def test_pool_exhaustion(self):
        pool = ConnectionPool(min_size=1, max_size=2)
        pool.acquire()
        pool.acquire()
        with pytest.raises(RuntimeError, match="exhausted"):
            pool.acquire()

    def test_recycle_idle(self):
        pool = ConnectionPool(min_size=1, max_size=5, max_idle_seconds=0)
        pool.acquire()  # Creates beyond min_size
        conn2 = pool.acquire()
        pool.release(conn2.connection_id)
        recycled = pool.recycle_idle()
        assert recycled >= 0


# ══════════════════════════════════════════════════════════════════════
# Migration Engine Tests
# ══════════════════════════════════════════════════════════════════════


class TestMigrationEngine:
    def test_register_and_apply(self):
        engine = MigrationEngine()
        engine.register(Migration(migration_id="001", version="1.0", description="Create table", up_sql="CREATE TABLE..."))
        assert len(engine.pending()) == 1
        assert engine.apply("001") is True
        assert len(engine.applied()) == 1
        assert len(engine.pending()) == 0

    def test_apply_idempotent(self):
        engine = MigrationEngine()
        engine.register(Migration(migration_id="001", version="1.0", description="Test", up_sql=""))
        engine.apply("001")
        assert engine.apply("001") is False  # Already applied

    def test_rollback(self):
        engine = MigrationEngine()
        engine.register(Migration(migration_id="001", version="1.0", description="Test", up_sql=""))
        engine.apply("001")
        assert engine.rollback("001") is True
        assert len(engine.pending()) == 1

    def test_apply_all(self):
        engine = MigrationEngine()
        engine.register(Migration(migration_id="001", version="1.0", description="A", up_sql=""))
        engine.register(Migration(migration_id="002", version="1.0", description="B", up_sql=""))
        count = engine.apply_all()
        assert count == 2


# ══════════════════════════════════════════════════════════════════════
# Repository Tests
# ══════════════════════════════════════════════════════════════════════


class TestRepository:
    def test_insert_and_get(self):
        repo = Repository("test_table")
        rid = repo.insert({"name": "Alice", "role": "admin"})
        record = repo.get(rid)
        assert record is not None
        assert record["name"] == "Alice"

    def test_update(self):
        repo = Repository("test_table")
        rid = repo.insert({"name": "Bob"})
        assert repo.update(rid, {"name": "Robert"}) is True
        assert repo.get(rid)["name"] == "Robert"

    def test_delete(self):
        repo = Repository("test_table")
        rid = repo.insert({"x": 1})
        assert repo.delete(rid) is True
        assert repo.get(rid) is None

    def test_upsert(self):
        repo = Repository("test_table")
        repo.upsert("u1", {"name": "first"})
        repo.upsert("u1", {"name": "updated"})
        assert repo.get("u1")["name"] == "updated"
        assert repo.count() == 1

    def test_query_with_filters(self):
        repo = Repository("test_table")
        repo.insert({"status": "active", "team": "alpha"})
        repo.insert({"status": "inactive", "team": "beta"})
        repo.insert({"status": "active", "team": "gamma"})
        results = repo.query(filters={"status": "active"})
        assert len(results) == 2

    def test_query_pagination(self):
        repo = Repository("test_table")
        for i in range(10):
            repo.insert({"idx": i})
        results = repo.query(limit=3, offset=2)
        assert len(results) == 3

    def test_bulk_insert(self):
        repo = Repository("test_table")
        count = repo.bulk_insert([{"a": 1}, {"a": 2}, {"a": 3}])
        assert count == 3
        assert repo.count() == 3


# ══════════════════════════════════════════════════════════════════════
# PostgresManager Tests
# ══════════════════════════════════════════════════════════════════════


class TestPostgresManager:
    def test_initialize(self):
        pg = PostgresManager()
        result = pg.initialize()
        assert result["initialized"] is True
        assert result["migrations_applied"] == 5

    def test_health_check(self):
        pg = PostgresManager()
        pg.initialize()
        health = pg.health_check()
        assert health["status"] == "healthy"
        assert health["initialized"] is True

    def test_get_repository(self):
        pg = PostgresManager()
        repo = pg.get_repository("users")
        assert repo.table_name == "users"
        # Same repo returned on second call
        assert pg.get_repository("users") is repo


# ══════════════════════════════════════════════════════════════════════
# Session Store Tests
# ══════════════════════════════════════════════════════════════════════


class TestSessionStore:
    def test_set_and_get(self):
        store = SessionStore()
        store.set("session-1", "username", "alice")
        assert store.get("session-1", "username") == "alice"

    def test_get_all(self):
        store = SessionStore()
        store.set("s1", "a", 1)
        store.set("s1", "b", 2)
        data = store.get_all("s1")
        assert data == {"a": 1, "b": 2}

    def test_delete_field(self):
        store = SessionStore()
        store.set("s1", "a", 1)
        store.set("s1", "b", 2)
        assert store.delete_field("s1", "a") is True
        assert store.get("s1", "a") is None

    def test_delete_key(self):
        store = SessionStore()
        store.set("s1", "a", 1)
        assert store.delete("s1") is True
        assert store.exists("s1") is False

    def test_keys(self):
        store = SessionStore()
        store.set("user:1", "name", "A")
        store.set("user:2", "name", "B")
        store.set("session:1", "data", "C")
        assert len(store.keys("user:*")) == 2


# ══════════════════════════════════════════════════════════════════════
# Rate Limiter Tests
# ══════════════════════════════════════════════════════════════════════


class TestRateLimiter:
    def test_allow_under_limit(self):
        limiter = RateLimiter(max_tokens=10, refill_rate=0)
        assert limiter.allow("user-1") is True
        assert limiter.remaining("user-1") == 9

    def test_reject_over_limit(self):
        limiter = RateLimiter(max_tokens=2, refill_rate=0)
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-1") is False

    def test_reset_bucket(self):
        limiter = RateLimiter(max_tokens=1, refill_rate=0)
        limiter.allow("user-1")  # exhausts
        limiter.reset("user-1")
        assert limiter.allow("user-1") is True

    def test_stats(self):
        limiter = RateLimiter(max_tokens=5, refill_rate=0)
        limiter.allow("a")
        limiter.allow("a")
        stats = limiter.stats()
        assert stats["total_requests"] == 2
        assert stats["tracked_keys"] == 1


# ══════════════════════════════════════════════════════════════════════
# PubSub Broker Tests
# ══════════════════════════════════════════════════════════════════════


class TestPubSubBroker:
    def test_subscribe_and_publish(self):
        received = []
        broker = PubSubBroker()
        broker.subscribe("alerts", lambda ch, data: received.append(data))
        broker.publish("alerts", {"level": "warning"})
        assert len(received) == 1
        assert received[0]["level"] == "warning"

    def test_publish_returns_subscriber_count(self):
        broker = PubSubBroker()
        broker.subscribe("ch", lambda c, d: None)
        broker.subscribe("ch", lambda c, d: None)
        count = broker.publish("ch", "hello")
        assert count == 2

    def test_unsubscribe(self):
        handler = lambda c, d: None
        broker = PubSubBroker()
        broker.subscribe("ch", handler)
        assert broker.unsubscribe("ch", handler) is True
        assert broker.publish("ch", "test") == 0

    def test_history(self):
        broker = PubSubBroker()
        broker.publish("ch1", "msg1")
        broker.publish("ch2", "msg2")
        all_history = broker.history()
        assert len(all_history) == 2
        ch1_history = broker.history("ch1")
        assert len(ch1_history) == 1


# ══════════════════════════════════════════════════════════════════════
# Redis Manager Tests
# ══════════════════════════════════════════════════════════════════════


class TestRedisManager:
    def test_health_check(self):
        redis = RedisManager()
        health = redis.health_check()
        assert health["status"] == "healthy"

    def test_flush_all(self):
        redis = RedisManager()
        redis.sessions.set("k", "f", "v")
        result = redis.flush_all()
        assert result["sessions_cleared"] == 1


# ══════════════════════════════════════════════════════════════════════
# Event Bus Tests
# ══════════════════════════════════════════════════════════════════════


class TestEventBus:
    def test_emit_and_subscribe(self):
        received = []
        bus = EventBus()
        bus.subscribe(EventType.EXECUTION_STARTED, lambda e: received.append(e))
        event = Event(event_type=EventType.EXECUTION_STARTED, data={"agent": "test"})
        delivered = bus.emit(event)
        assert delivered == 1
        assert len(received) == 1
        assert received[0].data["agent"] == "test"

    def test_wildcard_subscriber(self):
        received = []
        bus = EventBus()
        bus.subscribe(None, lambda e: received.append(e))  # Subscribe to all
        bus.emit(Event(event_type=EventType.CACHE_HIT))
        bus.emit(Event(event_type=EventType.EXECUTION_FAILED))
        assert len(received) == 2

    def test_unsubscribe(self):
        bus = EventBus()
        sub = bus.subscribe(EventType.HEALTH_CHECK, lambda e: None)
        assert bus.unsubscribe(sub.subscription_id) is True

    def test_history(self):
        bus = EventBus()
        bus.emit(Event(event_type=EventType.CACHE_HIT, source="cache"))
        bus.emit(Event(event_type=EventType.CACHE_MISS, source="cache"))
        history = bus.get_history(event_type=EventType.CACHE_HIT)
        assert len(history) == 1

    def test_dead_letters(self):
        bus = EventBus()
        bus.subscribe(EventType.CUSTOM, lambda e: 1/0)  # Will raise ZeroDivisionError
        bus.emit(Event(event_type=EventType.CUSTOM))
        letters = bus.dead_letters()
        assert len(letters) == 1

    def test_replay(self):
        replayed = []
        bus = EventBus()
        e1 = Event(event_type=EventType.EXECUTION_STARTED)
        e2 = Event(event_type=EventType.EXECUTION_COMPLETED)
        bus.emit(e1)
        bus.emit(e2)
        count = bus.replay(e1.event_id, lambda e: replayed.append(e))
        assert count == 2

    def test_correlation_id_filter(self):
        bus = EventBus()
        bus.emit(Event(event_type=EventType.WORKFLOW_STARTED, correlation_id="wf-1"))
        bus.emit(Event(event_type=EventType.WORKFLOW_COMPLETED, correlation_id="wf-1"))
        bus.emit(Event(event_type=EventType.WORKFLOW_STARTED, correlation_id="wf-2"))
        events = bus.get_history(correlation_id="wf-1")
        assert len(events) == 2

    def test_stats(self):
        bus = EventBus()
        bus.subscribe(EventType.CUSTOM, lambda e: None)
        bus.emit(Event(event_type=EventType.CUSTOM))
        stats = bus.stats()
        assert stats["events_emitted"] == 1
        assert stats["events_delivered"] == 1
        assert stats["total_subscriptions"] == 1
