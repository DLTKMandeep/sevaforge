"""
Tests for Week 2 API endpoints: Orchestration, Knowledge, Data.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from sevaforge.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ══════════════════════════════════════════════════════════════════════
# A2A Protocol API Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_a2a_register_agent(client):
    response = await client.post("/api/v1/a2a/agents", json={
        "agent_id": "test-agent", "name": "Test Agent", "capabilities": ["scan"]
    })
    assert response.status_code == 200
    assert response.json()["registered"] is True


@pytest.mark.asyncio
async def test_a2a_list_agents(client):
    await client.post("/api/v1/a2a/agents", json={"agent_id": "a1", "name": "A"})
    response = await client.get("/api/v1/a2a/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_a2a_send_message(client):
    await client.post("/api/v1/a2a/agents", json={"agent_id": "src", "name": "Src"})
    await client.post("/api/v1/a2a/agents", json={"agent_id": "tgt", "name": "Tgt"})
    response = await client.post("/api/v1/a2a/send", json={
        "source": "src", "target": "tgt", "payload": {"action": "test"}
    })
    assert response.status_code == 200
    assert response.json()["status"] == "delivered"


@pytest.mark.asyncio
async def test_a2a_stats(client):
    response = await client.get("/api/v1/a2a/stats")
    assert response.status_code == 200
    assert "messages_sent" in response.json()


# ══════════════════════════════════════════════════════════════════════
# Workflow Engine API Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_workflow(client):
    response = await client.post("/api/v1/workflows", json={
        "name": "test-workflow",
        "nodes": [
            {"node_id": "a", "agent_id": "agent-1"},
            {"node_id": "b", "agent_id": "agent-2"},
        ],
        "edges": [{"source": "a", "target": "b"}],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-workflow"
    assert data["nodes"] == 2


@pytest.mark.asyncio
async def test_execute_workflow(client):
    # Create workflow
    create_resp = await client.post("/api/v1/workflows", json={
        "name": "exec-test",
        "nodes": [{"node_id": "step1", "agent_id": "x"}],
        "edges": [],
    })
    wf_id = create_resp.json()["workflow_id"]

    # Execute
    response = await client.post(f"/api/v1/workflows/{wf_id}/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"


@pytest.mark.asyncio
async def test_list_workflows(client):
    response = await client.get("/api/v1/workflows")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_workflow_cycle_rejected(client):
    response = await client.post("/api/v1/workflows", json={
        "name": "cyclic",
        "nodes": [
            {"node_id": "a", "agent_id": "x"},
            {"node_id": "b", "agent_id": "y"},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "a"},
        ],
    })
    assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════
# Context Memory API Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_session(client):
    response = await client.post("/api/v1/context/sessions", json={
        "user_id": "testuser", "tenant_id": "acme"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "testuser"


@pytest.mark.asyncio
async def test_session_state(client):
    # Create session
    create_resp = await client.post("/api/v1/context/sessions", json={})
    sid = create_resp.json()["session_id"]

    # Store state
    await client.post(f"/api/v1/context/sessions/{sid}/state", json={
        "key": "result", "value": {"score": 0.9}
    })

    # Retrieve state
    response = await client.get(f"/api/v1/context/sessions/{sid}/state")
    assert response.status_code == 200
    assert response.json()["result"]["score"] == 0.9


@pytest.mark.asyncio
async def test_session_turns(client):
    create_resp = await client.post("/api/v1/context/sessions", json={})
    sid = create_resp.json()["session_id"]

    await client.post(f"/api/v1/context/sessions/{sid}/turns", json={
        "role": "user", "content": "Hello"
    })
    response = await client.get(f"/api/v1/context/sessions/{sid}/history")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_context_window(client):
    create_resp = await client.post("/api/v1/context/sessions", json={})
    sid = create_resp.json()["session_id"]
    await client.post(f"/api/v1/context/sessions/{sid}/turns", json={
        "role": "user", "content": "test"
    })
    response = await client.get(f"/api/v1/context/sessions/{sid}/window")
    assert response.status_code == 200
    assert "history" in response.json()


# ══════════════════════════════════════════════════════════════════════
# Knowledge Layer API Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_index_and_search(client):
    # Index document
    await client.post("/api/v1/search/index", json={
        "title": "Terraform Guide",
        "content": "Terraform is an infrastructure as code tool",
        "collection": "docs",
    })
    # Search
    response = await client.post("/api/v1/search/query", json={
        "query": "Terraform infrastructure", "mode": "bm25"
    })
    assert response.status_code == 200
    assert response.json()["total_results"] >= 1


@pytest.mark.asyncio
async def test_list_collections(client):
    await client.post("/api/v1/search/index", json={
        "content": "test", "collection": "testcol"
    })
    response = await client.get("/api/v1/search/collections")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_knowledge_graph_crud(client):
    # Add entities
    e1 = await client.post("/api/v1/graph/entities", json={
        "name": "ServiceA", "entity_type": "service"
    })
    e2 = await client.post("/api/v1/graph/entities", json={
        "name": "ServiceB", "entity_type": "service"
    })
    eid1 = e1.json()["entity_id"]
    eid2 = e2.json()["entity_id"]

    # Add relationship
    response = await client.post("/api/v1/graph/relationships", json={
        "source_id": eid1, "target_id": eid2, "relationship_type": "depends_on"
    })
    assert response.status_code == 200

    # Get neighbors
    response = await client.get(f"/api/v1/graph/entities/{eid1}/neighbors?depth=1")
    assert response.status_code == 200
    assert response.json()["total_nodes_visited"] >= 2


@pytest.mark.asyncio
async def test_entity_extraction_api(client):
    response = await client.post("/api/v1/graph/extract", json={
        "text": "The PromptEngine uses PostgreSQL for storage"
    })
    assert response.status_code == 200
    assert response.json()["extracted"] >= 1


@pytest.mark.asyncio
async def test_rerank_api(client):
    response = await client.post("/api/v1/rerank", json={
        "query": "Python web development",
        "candidates": [
            {"doc_id": "d1", "content": "Python Django web framework", "title": "Django", "score": 0.8, "rank": 1},
            {"doc_id": "d2", "content": "Cooking Italian food", "title": "Recipes", "score": 0.7, "rank": 2},
        ],
        "top_k": 5,
    })
    assert response.status_code == 200
    assert response.json()["total_reranked"] >= 1


# ══════════════════════════════════════════════════════════════════════
# Data Layer API Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_db_health(client):
    response = await client.get("/api/v1/db/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_db_crud(client):
    # Insert
    resp = await client.post("/api/v1/db/test_table/records", json={
        "data": {"name": "Alice", "role": "admin"}
    })
    assert resp.status_code == 200
    rid = resp.json()["id"]

    # Get
    resp = await client.get(f"/api/v1/db/test_table/records/{rid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alice"

    # Update
    resp = await client.put(f"/api/v1/db/test_table/records/{rid}", json={
        "updates": {"name": "Bob"}
    })
    assert resp.status_code == 200

    # Delete
    resp = await client.delete(f"/api/v1/db/test_table/records/{rid}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_redis_session(client):
    # Set
    await client.post("/api/v1/redis/sessions/set", json={
        "key": "sess-1", "field_name": "user", "value": "alice"
    })
    # Get
    response = await client.get("/api/v1/redis/sessions/sess-1")
    assert response.status_code == 200
    assert response.json()["data"]["user"] == "alice"


@pytest.mark.asyncio
async def test_rate_limiting(client):
    response = await client.post("/api/v1/redis/rate-limit/check", json={
        "key": "test-key", "cost": 1
    })
    assert response.status_code == 200
    assert response.json()["allowed"] is True


@pytest.mark.asyncio
async def test_event_emit(client):
    response = await client.post("/api/v1/events/emit", json={
        "event_type": "custom", "source": "test", "data": {"msg": "hello"}
    })
    assert response.status_code == 200
    assert "event_id" in response.json()


@pytest.mark.asyncio
async def test_event_history(client):
    await client.post("/api/v1/events/emit", json={
        "event_type": "custom", "source": "test", "data": {}
    })
    response = await client.get("/api/v1/events/history?source=test")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
