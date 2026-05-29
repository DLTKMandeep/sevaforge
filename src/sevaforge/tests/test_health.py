"""
Tests for health and readiness endpoints.
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
async def test_root(client):
    """Root endpoint returns welcome message."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "SevaForge" in data["message"]
    assert data["docs"] == "/docs"


@pytest.mark.asyncio
async def test_health(client):
    """Health endpoint returns healthy status."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["environment"] == "development"
    assert "uptime_seconds" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness(client):
    """Readiness probe returns gateway status."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "cache_enabled" in data
    assert "templates_loaded" in data
