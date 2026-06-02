"""
Tests for Week 5 — MCP Server Framework.

Covers:
  - BaseMCPServer: tool registration, JSON-RPC dispatch, health, info
  - GitHubMCPServer: repos, PRs, issues, code search
  - DeploymentMCPServer: deploy, rollback, status, scale
  - SecurityMCPServer: vulnerability scan, secrets audit, compliance
  - ObservabilityMCPServer: metrics, logs, traces, alerts, dashboard
  - API endpoints: /mcp/ routes
"""

import pytest
from httpx import ASGITransport, AsyncClient

from sevaforge.mcp import (
    BaseMCPServer,
    MCPTool,
    MCPToolParameter,
    MCPRequest,
    MCPResponse,
    GitHubMCPServer,
    DeploymentMCPServer,
    SecurityMCPServer,
    ObservabilityMCPServer,
)
from sevaforge.mcp.base_mcp_server import MCPServerState
from sevaforge.api.app import create_app


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def github_server():
    return GitHubMCPServer()


@pytest.fixture
def deployment_server():
    return DeploymentMCPServer()


@pytest.fixture
def security_server():
    return SecurityMCPServer()


@pytest.fixture
def observability_server():
    return ObservabilityMCPServer()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ══════════════════════════════════════════════════════════════════════
# BaseMCPServer Tests
# ══════════════════════════════════════════════════════════════════════


def test_mcp_server_initialization(github_server):
    """MCP server initializes with correct state."""
    assert github_server.state == MCPServerState.READY
    assert github_server.server_id == "github"
    assert len(github_server.tools) == 10


def test_mcp_server_info(github_server):
    """Server info returns metadata with tool list."""
    info = github_server.info()
    assert info["server_id"] == "github"
    assert info["version"] == "2.0.0"
    assert len(info["tools"]) == 10


def test_mcp_tool_schema(github_server):
    """Tool schema generation produces valid JSON Schema."""
    tool = github_server.tools["list_repos"]
    schema = tool.to_schema()
    assert schema["name"] == "list_repos"
    assert "inputSchema" in schema
    assert "properties" in schema["inputSchema"]
    assert "owner" in schema["inputSchema"]["properties"]
    assert "owner" in schema["inputSchema"]["required"]


@pytest.mark.asyncio
async def test_mcp_tools_list(github_server):
    """tools/list returns all available tools."""
    request = MCPRequest(method="tools/list")
    response = await github_server.handle_request(request)
    assert not response.is_error
    assert len(response.result["tools"]) == 10


@pytest.mark.asyncio
async def test_mcp_server_health(github_server):
    """server/health returns healthy status."""
    request = MCPRequest(method="server/health")
    response = await github_server.handle_request(request)
    assert not response.is_error
    assert response.result["status"] == "healthy"


@pytest.mark.asyncio
async def test_mcp_server_info_method(github_server):
    """server/info returns server metadata."""
    request = MCPRequest(method="server/info")
    response = await github_server.handle_request(request)
    assert not response.is_error
    assert response.result["server_id"] == "github"


@pytest.mark.asyncio
async def test_mcp_method_not_found(github_server):
    """Unknown method returns error."""
    request = MCPRequest(method="unknown/method")
    response = await github_server.handle_request(request)
    assert response.is_error
    assert response.error["code"] == -32601


@pytest.mark.asyncio
async def test_mcp_tool_not_found(github_server):
    """Calling unknown tool returns error."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "nonexistent_tool", "arguments": {}},
    )
    response = await github_server.handle_request(request)
    assert response.is_error


# ══════════════════════════════════════════════════════════════════════
# GitHubMCPServer Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_github_list_repos(github_server):
    """list_repos returns repository list."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "list_repos", "arguments": {"owner": "DLTKMandeep"}},
    )
    response = await github_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["owner"] == "DLTKMandeep"
    assert len(data["repositories"]) > 0


@pytest.mark.asyncio
async def test_github_search_code(github_server):
    """search_code returns matching results."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "search_code", "arguments": {"query": "BaseAgent"}},
    )
    response = await github_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["total_count"] > 0


@pytest.mark.asyncio
async def test_github_create_issue(github_server):
    """create_issue returns new issue with number."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "create_issue", "arguments": {
            "owner": "DLTKMandeep", "repo": "sevaforge",
            "title": "Test issue", "body": "This is a test",
        }},
    )
    response = await github_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert "number" in data
    assert data["state"] == "open"


@pytest.mark.asyncio
async def test_github_list_branches(github_server):
    """list_branches returns branch list."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "list_branches", "arguments": {
            "owner": "DLTKMandeep", "repo": "sevaforge",
        }},
    )
    response = await github_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    branch_names = [b["name"] for b in data["branches"]]
    assert "main" in branch_names


# ══════════════════════════════════════════════════════════════════════
# DeploymentMCPServer Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deployment_deploy(deployment_server):
    """deploy triggers a deployment and returns status."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "deploy", "arguments": {
            "service": "sevaforge", "version": "2.0.0",
            "environment": "staging", "strategy": "canary",
        }},
    )
    response = await deployment_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["service"] == "sevaforge"
    assert data["version"] == "2.0.0"
    assert "deploy_id" in data


@pytest.mark.asyncio
async def test_deployment_rollback(deployment_server):
    """rollback returns rollback plan with steps."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "rollback", "arguments": {
            "service": "sevaforge", "environment": "production",
            "target_version": "1.9.0", "reason": "High error rate",
        }},
    )
    response = await deployment_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["to_version"] == "1.9.0"
    assert len(data["steps_completed"]) > 0


@pytest.mark.asyncio
async def test_deployment_status(deployment_server):
    """deploy_status returns health information."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "deploy_status", "arguments": {
            "service": "sevaforge", "environment": "production",
        }},
    )
    response = await deployment_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["status"] == "healthy"
    assert data["replicas"]["ready"] == 3


@pytest.mark.asyncio
async def test_deployment_scale(deployment_server):
    """scale adjusts replica count."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "scale", "arguments": {
            "service": "sevaforge", "environment": "staging", "replicas": 5,
        }},
    )
    response = await deployment_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["new_replicas"] == 5


# ══════════════════════════════════════════════════════════════════════
# SecurityMCPServer Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_security_scan_vulnerabilities(security_server):
    """scan_vulnerabilities returns findings with severity."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "scan_vulnerabilities", "arguments": {
            "target": "src/app.py", "scan_type": "full",
        }},
    )
    response = await security_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["status"] == "completed"
    assert data["summary"]["total_findings"] > 0


@pytest.mark.asyncio
async def test_security_audit_secrets(security_server):
    """audit_secrets returns secret findings."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "audit_secrets", "arguments": {
            "target": "src/config.py",
        }},
    )
    response = await security_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["summary"]["total_secrets_found"] > 0


@pytest.mark.asyncio
async def test_security_check_dependencies(security_server):
    """check_dependencies returns CVE findings."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "check_dependencies", "arguments": {
            "manifest": "fastapi>=0.115.0\nurllib3==1.26.5",
        }},
    )
    response = await security_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["vulnerable_dependencies"] > 0


@pytest.mark.asyncio
async def test_security_compliance(security_server):
    """verify_compliance returns control assessment."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "verify_compliance", "arguments": {
            "framework": "soc2", "scope": "application",
        }},
    )
    response = await security_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["framework"] == "soc2"
    assert "compliance_score" in data
    assert data["controls_checked"] > 0


@pytest.mark.asyncio
async def test_security_report_incident(security_server):
    """report_incident creates a new incident."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "report_incident", "arguments": {
            "title": "Test Incident",
            "description": "Testing incident reporting",
            "severity": "medium",
        }},
    )
    response = await security_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["title"] == "Test Incident"
    assert data["status"] == "open"


# ══════════════════════════════════════════════════════════════════════
# ObservabilityMCPServer Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_observability_query_metrics(observability_server):
    """query_metrics returns time-series data."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "query_metrics", "arguments": {
            "metric": "http_requests_total", "time_range": "1h",
        }},
    )
    response = await observability_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert len(data["data_points"]) > 0
    assert "summary" in data


@pytest.mark.asyncio
async def test_observability_search_logs(observability_server):
    """search_logs returns matching log entries."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "search_logs", "arguments": {
            "query": "error", "severity": "all",
        }},
    )
    response = await observability_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["total_results"] > 0


@pytest.mark.asyncio
async def test_observability_get_trace(observability_server):
    """get_trace returns span details."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "get_trace", "arguments": {
            "trace_id": "sf-abc123def",
        }},
    )
    response = await observability_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert len(data["spans"]) > 0
    assert data["trace_id"] == "sf-abc123def"


@pytest.mark.asyncio
async def test_observability_create_alert_rule(observability_server):
    """create_alert_rule creates a new alert rule."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "create_alert_rule", "arguments": {
            "name": "High CPU Alert",
            "metric": "cpu_usage",
            "condition": "> 90",
            "severity": "critical",
        }},
    )
    response = await observability_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["name"] == "High CPU Alert"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_observability_dashboard(observability_server):
    """get_dashboard returns service overview."""
    request = MCPRequest(
        method="tools/call",
        params={"name": "get_dashboard", "arguments": {
            "service": "sevaforge",
        }},
    )
    response = await observability_server.handle_request(request)
    assert not response.is_error
    data = response.result["data"]
    assert data["service"] == "sevaforge"
    assert data["summary"]["status"] == "healthy"


# ══════════════════════════════════════════════════════════════════════
# MCP Stats
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mcp_stats_tracking(github_server):
    """Stats track requests correctly."""
    await github_server.handle_request(MCPRequest(method="server/health"))
    stats = github_server.stats()
    assert stats["total_requests"] >= 1
    assert stats["successful_requests"] >= 1


# ══════════════════════════════════════════════════════════════════════
# MCP API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_list_mcp_servers(client):
    """GET /mcp/servers returns all MCP servers."""
    response = await client.get("/api/v1/mcp/servers")
    assert response.status_code == 200
    data = response.json()
    assert data["total_servers"] == 4
    server_ids = [s["server_id"] for s in data["servers"]]
    assert "github" in server_ids
    assert "deployment" in server_ids
    assert "security" in server_ids
    assert "observability" in server_ids


@pytest.mark.asyncio
async def test_api_get_mcp_server(client):
    """GET /mcp/servers/{server_id} returns server info."""
    response = await client.get("/api/v1/mcp/servers/github")
    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == "github"
    assert len(data["tools"]) == 10


@pytest.mark.asyncio
async def test_api_get_mcp_server_not_found(client):
    """GET /mcp/servers/{server_id} returns 404 for unknown server."""
    response = await client.get("/api/v1/mcp/servers/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_list_server_tools(client):
    """GET /mcp/servers/{server_id}/tools returns tool schemas."""
    response = await client.get("/api/v1/mcp/servers/deployment/tools")
    assert response.status_code == 200
    data = response.json()
    tool_names = [t["name"] for t in data["tools"]]
    assert "deploy" in tool_names
    assert "rollback" in tool_names


@pytest.mark.asyncio
async def test_api_call_mcp_tool(client):
    """POST /mcp/servers/{server_id}/call executes a tool."""
    response = await client.post("/api/v1/mcp/servers/github/call", json={
        "tool_name": "list_repos",
        "arguments": {"owner": "DLTKMandeep"},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == "github"
    assert data["tool_name"] == "list_repos"
    assert "result" in data


@pytest.mark.asyncio
async def test_api_call_mcp_tool_not_found(client):
    """POST /mcp/servers/{server_id}/call returns 404 for unknown tool."""
    response = await client.post("/api/v1/mcp/servers/github/call", json={
        "tool_name": "nonexistent_tool",
        "arguments": {},
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_mcp_server_health(client):
    """GET /mcp/servers/{server_id}/health returns health status."""
    response = await client.get("/api/v1/mcp/servers/observability/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_api_list_all_tools(client):
    """GET /mcp/tools returns tools across all servers."""
    response = await client.get("/api/v1/mcp/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["total_tools"] == 29  # 10 + 6 + 6 + 7


@pytest.mark.asyncio
async def test_api_mcp_stats(client):
    """GET /mcp/stats returns MCP subsystem statistics."""
    response = await client.get("/api/v1/mcp/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_servers"] == 4
    assert data["total_tools"] == 29
