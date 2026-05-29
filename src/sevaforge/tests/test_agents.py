"""
Tests for agent CRUD and execution endpoints.
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


@pytest.mark.asyncio
async def test_list_agents(client):
    """GET /agents returns pre-registered agents."""
    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    agents = response.json()
    assert isinstance(agents, list)
    assert len(agents) >= 4  # 4 pre-registered agents
    agent_ids = {a["agent_id"] for a in agents}
    assert "code-review" in agent_ids
    assert "doc-writer" in agent_ids
    assert "test-gen" in agent_ids
    assert "security-scan" in agent_ids


@pytest.mark.asyncio
async def test_get_agent(client):
    """GET /agents/{id} returns agent details."""
    response = await client.get("/api/v1/agents/code-review")
    assert response.status_code == 200
    agent = response.json()
    assert agent["agent_id"] == "code-review"
    assert agent["name"] == "Code Review Agent"
    assert "code-analysis" in agent["capabilities"]


@pytest.mark.asyncio
async def test_get_agent_not_found(client):
    """GET /agents/{id} returns 404 for unknown agent."""
    response = await client.get("/api/v1/agents/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_agent(client):
    """POST /agents registers a new agent."""
    new_agent = {
        "agent_id": "test-custom",
        "name": "Custom Test Agent",
        "description": "Agent for testing registration.",
        "capabilities": ["testing"],
    }
    response = await client.post("/api/v1/agents", json=new_agent)
    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == "test-custom"

    # Verify it's in the list
    response = await client.get("/api/v1/agents/test-custom")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_register_duplicate_agent(client):
    """POST /agents returns 409 for duplicate agent_id."""
    response = await client.post(
        "/api/v1/agents",
        json={
            "agent_id": "code-review",
            "name": "Dup",
            "description": "Duplicate",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_execute_agent(client):
    """POST /agents/{id}/execute runs the gateway pipeline."""
    response = await client.post(
        "/api/v1/agents/code-review/execute",
        json={
            "input": "def add(a, b): return a + b",
            "params": {"language": "python"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "code-review"
    assert data["status"] == "succeeded"
    assert "execution_id" in data
    assert "trace_id" in data
    assert data["latency_ms"] > 0


@pytest.mark.asyncio
async def test_execute_agent_not_found(client):
    """POST /agents/{id}/execute returns 404 for unknown agent."""
    response = await client.post(
        "/api/v1/agents/nonexistent/execute",
        json={"input": "test"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_execute_agent_stream(client):
    """POST /agents/{id}/execute with stream=true returns SSE."""
    response = await client.post(
        "/api/v1/agents/code-review/execute",
        json={
            "input": "print('hello')",
            "stream": True,
        },
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    # Verify SSE format
    body = response.text
    assert "event:" in body
    assert "data:" in body
