"""
Tests for gateway management API endpoints.
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
async def test_cache_stats(client):
    """GET /gateway/cache/stats returns cache statistics."""
    response = await client.get("/api/v1/gateway/cache/stats")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "total_entries" in data
    assert "exact_hits" in data
    assert "semantic_hits" in data
    assert "misses" in data
    assert "hit_rate" in data


@pytest.mark.asyncio
async def test_cache_clear(client):
    """POST /gateway/cache/clear clears the cache."""
    response = await client.post("/api/v1/gateway/cache/clear")
    assert response.status_code == 200
    data = response.json()
    assert "cleared" in data


@pytest.mark.asyncio
async def test_cache_evict(client):
    """POST /gateway/cache/evict removes expired entries."""
    response = await client.post("/api/v1/gateway/cache/evict")
    assert response.status_code == 200
    data = response.json()
    assert "evicted" in data


@pytest.mark.asyncio
async def test_list_templates(client):
    """GET /gateway/templates returns loaded templates."""
    response = await client.get("/api/v1/gateway/templates")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_reload_templates(client):
    """POST /gateway/templates/reload reloads templates."""
    response = await client.post("/api/v1/gateway/templates/reload")
    assert response.status_code == 200
    data = response.json()
    assert "reloaded" in data


@pytest.mark.asyncio
async def test_gateway_info(client):
    """GET /gateway/info returns component status."""
    response = await client.get("/api/v1/gateway/info")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert "prompt_engine" in data["components"]
    assert "semantic_cache" in data["components"]
    assert "schema_gate" in data["components"]


@pytest.mark.asyncio
async def test_correlation_id_header(client):
    """Responses include X-Trace-ID and X-Response-Time-Ms."""
    response = await client.get("/api/v1/health")
    assert "x-trace-id" in response.headers
    assert "x-response-time-ms" in response.headers
    assert response.headers["x-trace-id"].startswith("sf-")


@pytest.mark.asyncio
async def test_custom_trace_id(client):
    """Custom X-Trace-ID header is echoed back."""
    response = await client.get(
        "/api/v1/health",
        headers={"X-Trace-ID": "custom-trace-123"},
    )
    assert response.headers["x-trace-id"] == "custom-trace-123"
