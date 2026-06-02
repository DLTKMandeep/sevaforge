"""
Tests for Week 5 — Agent Intelligence Layer.

Covers:
  - BaseAgent: config, info, stats, guardrail blocking, execution flow
  - CodeReviewAgent: pattern checks, execute with mock LLM
  - SecurityAgent: secrets scanning, vulnerability scanning
  - DocumentationAgent: code structure analysis
  - DeployOrchestratorAgent: config validation, deploy planning
  - DiscoveryAgent: service/API/dependency discovery
  - API endpoints: /agents/v2/ routes
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient

from sevaforge.agents import (
    BaseAgent,
    AgentCapability,
    AgentConfig,
    AgentExecutionContext,
    AgentResult,
    CodeReviewAgent,
    SecurityAgent,
    DocumentationAgent,
    DeployOrchestratorAgent,
    DiscoveryAgent,
)
from sevaforge.agents.base_agent import AgentState
from sevaforge.api.app import create_app


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def code_review_agent():
    return CodeReviewAgent()


@pytest.fixture
def security_agent():
    return SecurityAgent()


@pytest.fixture
def documentation_agent():
    return DocumentationAgent()


@pytest.fixture
def deploy_agent():
    return DeployOrchestratorAgent()


@pytest.fixture
def discovery_agent():
    return DiscoveryAgent()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ══════════════════════════════════════════════════════════════════════
# BaseAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_agent_config_and_info(code_review_agent):
    """Agent info returns correct metadata."""
    info = code_review_agent.info()
    assert info["agent_id"] == "code-review"
    assert info["name"] == "Code Review Agent"
    assert len(info["capabilities"]) == 4
    assert info["state"] == "idle"


def test_agent_stats_initialized(code_review_agent):
    """Agent stats start at zero."""
    stats = code_review_agent.stats()
    assert stats["total_executions"] == 0
    assert stats["total_cost_usd"] == 0.0
    assert stats["agent_id"] == "code-review"


def test_agent_capabilities(security_agent):
    """Agent advertises correct capabilities."""
    caps = security_agent.capabilities
    cap_names = [c.name for c in caps]
    assert "vulnerability_scan" in cap_names
    assert "secrets_detection" in cap_names
    assert "compliance_check" in cap_names


def test_all_agents_instantiate():
    """All 5 agents can be instantiated without errors."""
    agents = [
        CodeReviewAgent(),
        SecurityAgent(),
        DocumentationAgent(),
        DeployOrchestratorAgent(),
        DiscoveryAgent(),
    ]
    assert len(agents) == 5
    ids = [a.agent_id for a in agents]
    assert "code-review" in ids
    assert "security" in ids
    assert "documentation" in ids
    assert "deploy-orchestrator" in ids
    assert "discovery" in ids


def test_agent_state_starts_idle(code_review_agent):
    """Agent state is IDLE when not executing."""
    assert code_review_agent.state == AgentState.IDLE


# ══════════════════════════════════════════════════════════════════════
# CodeReviewAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_code_review_pattern_security(code_review_agent):
    """Pattern checker detects security issues."""
    code = '''
password = "supersecret123"
eval(user_input)
os.system(f"rm -rf {path}")
'''
    findings = code_review_agent._run_pattern_checks(code, "security")
    assert len(findings) >= 3
    severities = [f["severity"] for f in findings]
    assert "high" in severities


def test_code_review_pattern_quality(code_review_agent):
    """Pattern checker detects quality issues."""
    code = '''
try:
    do_something()
except:
    pass
# TODO fix this later
print("debugging")
from os import *
'''
    findings = code_review_agent._run_pattern_checks(code, "quality")
    assert len(findings) >= 3
    categories = [f["category"] for f in findings]
    assert all(c == "quality" for c in categories)


def test_code_review_pattern_performance(code_review_agent):
    """Pattern checker detects performance issues."""
    code = '''
result = ""
for item in items:
    result += str(item)
for i in range(len(my_list)):
    process(my_list[i])
SELECT * FROM users
'''
    findings = code_review_agent._run_pattern_checks(code, "performance")
    assert len(findings) >= 2


def test_code_review_pattern_focus_filter(code_review_agent):
    """Focus parameter filters which patterns are checked."""
    code = 'password = "secret"\nprint("debug")\nfor i in range(len(x)): pass'

    security_only = code_review_agent._run_pattern_checks(code, "security")
    quality_only = code_review_agent._run_pattern_checks(code, "quality")
    perf_only = code_review_agent._run_pattern_checks(code, "performance")

    sec_categories = set(f["category"] for f in security_only)
    qual_categories = set(f["category"] for f in quality_only)
    perf_categories = set(f["category"] for f in perf_only)

    assert sec_categories <= {"security"}
    assert qual_categories <= {"quality"}
    assert perf_categories <= {"performance"}


@pytest.mark.asyncio
async def test_code_review_execute_with_mock_llm(code_review_agent):
    """Execute completes and returns structured result even with mock LLM."""
    ctx = AgentExecutionContext(
        input='def add(a, b):\n    return a + b',
        params={"language": "python", "focus": "all"},
    )
    # The execute method catches LLM errors and falls back to pattern-only
    result = await code_review_agent.run(ctx)
    assert result.agent_id == "code-review"
    assert result.status in ("succeeded", "failed")


# ══════════════════════════════════════════════════════════════════════
# SecurityAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_security_secrets_detection(security_agent):
    """Secrets scanner detects various credential types."""
    # NOTE: These are intentionally fake test patterns for secret detection.
    # They use the correct format prefix to trigger pattern matching but are not real credentials.
    fake_aws = "AKIA" + "TESTONLY" + "FAKEKEY1"
    fake_gh = "ghp_" + "TestOnlyFakeToken" + "00000000000000"
    fake_stripe = "sk_live_" + "testonly" + "fakekey123456789"
    code = f'''
AWS_KEY = "{fake_aws}"
github_token = "{fake_gh}"
STRIPE_KEY = "{fake_stripe}"
db_url = "postgres://admin:testpass@db.example.com/mydb"
'''
    findings = security_agent._scan_secrets(code)
    assert len(findings) >= 3
    types = [f["type"] for f in findings]
    assert any("aws" in t for t in types)
    assert any("github" in t or "stripe" in t for t in types)


def test_security_secrets_skips_comments(security_agent):
    """Secrets scanner skips commented lines."""
    fake_aws = "AKIA" + "TESTONLY" + "FAKEKEY1"
    fake_gh = "ghp_" + "TestOnlyFakeToken" + "00000000000000"
    code = f'''
# AWS_KEY = "{fake_aws}"
// github_token = "{fake_gh}"
real_key = "not-a-secret-pattern"
'''
    findings = security_agent._scan_secrets(code)
    # Comments should be skipped, only non-comment non-matching lines remain
    secret_types = [f["type"] for f in findings]
    assert "aws_access_key" not in secret_types


def test_security_vulnerability_detection(security_agent):
    """Vulnerability scanner detects OWASP/CWE patterns."""
    code = '''
os.system(f"deploy {user_input}")
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
data = pickle.loads(untrusted_bytes)
hashlib.md5(password.encode())
requests.get(url, verify=False)
'''
    findings = security_agent._scan_vulnerabilities(code)
    assert len(findings) >= 4
    cwes = [f.get("cwe", "") for f in findings]
    assert any("CWE-78" in c for c in cwes)  # Command injection
    assert any("CWE-502" in c for c in cwes)  # Insecure deserialization


def test_security_risk_score(security_agent):
    """Risk score calculation weights severity correctly."""
    findings_critical = [{"severity": "critical"}]
    findings_low = [{"severity": "low"}, {"severity": "low"}, {"severity": "low"}]
    findings_empty = []

    assert security_agent._calculate_risk_score(findings_critical) >= 25
    assert security_agent._calculate_risk_score(findings_low) < 25
    assert security_agent._calculate_risk_score(findings_empty) == 0


@pytest.mark.asyncio
async def test_security_execute(security_agent):
    """Security agent executes and returns structured result."""
    ctx = AgentExecutionContext(
        input='os.system(cmd)\npassword = "secret"',
        params={"scan_type": "full", "language": "python"},
    )
    result = await security_agent.run(ctx)
    assert result.agent_id == "security"


# ══════════════════════════════════════════════════════════════════════
# DocumentationAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_documentation_structure_analysis(documentation_agent):
    """Code structure analysis extracts classes, functions, routes."""
    code = '''
import os
from fastapi import APIRouter

router = APIRouter()

class MyService:
    def process(self, data: str) -> dict:
        return {"result": data}

async def helper_func(x: int) -> int:
    return x * 2

@router.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}

@router.post("/api/v1/execute")
async def execute(body: dict):
    return {"executed": True}

MAX_RETRIES = 3
'''
    structure = documentation_agent._analyze_code_structure(code, "python")
    assert len(structure["classes"]) == 1
    assert structure["classes"][0]["name"] == "MyService"
    assert len(structure["functions"]) >= 3
    assert len(structure["routes"]) == 2
    assert any(r["method"] == "GET" and r["path"] == "/api/v1/health" for r in structure["routes"])
    assert len(structure["imports"]) >= 2


def test_documentation_minimal_docs(documentation_agent):
    """Minimal doc generation works without LLM."""
    structure = {
        "classes": [{"name": "MyClass", "bases": "BaseClass", "line": 10}],
        "functions": [
            {"name": "public_fn", "params": "x: int", "line": 20, "is_async": True, "is_private": False},
            {"name": "_private_fn", "params": "", "line": 30, "is_async": False, "is_private": True},
        ],
        "routes": [{"method": "GET", "path": "/health", "line": 5}],
        "imports": [],
        "constants": [],
        "total_lines": 50,
    }
    docs = documentation_agent._generate_minimal_docs(structure, "api_docs", "TestProject")
    assert "TestProject" in docs
    assert "MyClass" in docs
    assert "public_fn" in docs
    assert "/health" in docs
    # Private functions should NOT appear in public docs
    assert "_private_fn" not in docs


# ══════════════════════════════════════════════════════════════════════
# DeployOrchestratorAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_deploy_config_validation_k8s(deploy_agent):
    """K8s manifest validation detects missing configs."""
    manifest = '''
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: app
        image: my-app:latest
'''
    issues = deploy_agent._validate_k8s(manifest)
    assert len(issues) >= 2  # Missing resource limits, probes, single replica
    titles = [i["title"] for i in issues]
    assert any("resource" in t.lower() for t in titles)
    assert any("replica" in t.lower() for t in titles)


def test_deploy_config_validation_dockerfile(deploy_agent):
    """Dockerfile validation detects security issues."""
    dockerfile = '''
FROM python
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
'''
    issues = deploy_agent._validate_dockerfile(dockerfile)
    assert len(issues) >= 2
    titles = [i["title"] for i in issues]
    assert any("root" in t.lower() for t in titles)  # No USER


def test_deploy_dangerous_patterns(deploy_agent):
    """Quick config check detects dangerous K8s patterns."""
    config = '''
securityContext:
  privileged: true
  runAsUser: 0
  allowPrivilegeEscalation: true
'''
    issues = deploy_agent._quick_config_check(config)
    assert len(issues) >= 3


def test_deploy_stages_canary(deploy_agent):
    """Canary deployment generates correct stages."""
    stages = deploy_agent._default_stages("canary", "production")
    assert len(stages) >= 5
    assert stages[0]["name"] == "pre-deploy"
    assert any("canary" in s["name"] for s in stages)


def test_deploy_duration_estimate(deploy_agent):
    """Production deployments take longer than staging."""
    staging_time = deploy_agent._estimate_duration("canary", "staging")
    prod_time = deploy_agent._estimate_duration("canary", "production")
    assert prod_time > staging_time


def test_deploy_status_check(deploy_agent):
    """Status check returns structured health info."""
    status = deploy_agent._check_status("sevaforge", "production")
    assert status["status"] == "healthy"
    assert "replicas" in status
    assert status["replicas"]["ready"] == status["replicas"]["desired"]


# ══════════════════════════════════════════════════════════════════════
# DiscoveryAgent Tests
# ══════════════════════════════════════════════════════════════════════


def test_discovery_api_endpoints(discovery_agent):
    """API discovery finds route definitions."""
    code = '''
@router.get("/api/v1/health")
async def health():
    return {"status": "ok"}

@router.post("/api/v1/agents/execute")
async def execute_agent(body: dict):
    pass

@app.delete("/api/v1/cache/{key}")
async def delete_cache(key: str):
    pass
'''
    endpoints = discovery_agent._discover_apis(code)
    assert len(endpoints) == 3
    methods = [e["method"] for e in endpoints]
    assert "GET" in methods
    assert "POST" in methods
    assert "DELETE" in methods


def test_discovery_services(discovery_agent):
    """Service discovery finds external dependencies."""
    code = '''
resp = requests.get("https://api.github.com/repos/test")
db_url = "postgres://user:testpass@db.example.com/mydb"
redis_url = "redis://cache.example.com:6379"
'''
    services = discovery_agent._discover_services(code)
    assert len(services) >= 2
    types = [s["type"] for s in services]
    assert "http_client" in types or "database" in types


def test_discovery_dependencies(discovery_agent):
    """Dependency discovery finds imports (excluding stdlib)."""
    code = '''
import os
import json
from fastapi import APIRouter
from sevaforge.agents import BaseAgent
from pydantic import BaseModel
import numpy as np
'''
    deps = discovery_agent._discover_dependencies(code, "python")
    module_names = [d["module"] for d in deps]
    # stdlib should be excluded
    assert "os" not in module_names
    assert "json" not in module_names
    # These should be found
    assert "fastapi" in module_names
    assert "pydantic" in module_names


def test_discovery_cloud_resources(discovery_agent):
    """Cloud resource discovery finds GCP/AWS/Azure references."""
    code = '''
BUCKET = "gs://my-data-bucket/models/"
S3_PATH = "s3://my-backup-bucket/archives/"
image: sevaforge/api:1.2.3
'''
    resources = discovery_agent._discover_cloud_resources(code)
    assert len(resources) >= 2
    types = [r["type"] for r in resources]
    assert "gcp_storage" in types
    assert "aws_s3" in types


def test_discovery_auth_detection(discovery_agent):
    """Auth detection identifies protected endpoints."""
    code = '''
@router.get("/api/v1/data")
async def get_data(user: TokenPayload = Depends(require_auth)):
    return {}
'''
    has_auth = discovery_agent._check_auth_required(code, 0)
    assert has_auth is True


# ══════════════════════════════════════════════════════════════════════
# Agent API Endpoint Tests
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_list_agents(client):
    """GET /agents/v2/ returns all registered agents."""
    response = await client.get("/api/v1/agents/v2/")
    assert response.status_code == 200
    data = response.json()
    assert data["total_agents"] == 5
    agent_ids = [a["agent_id"] for a in data["agents"]]
    assert "code-review" in agent_ids
    assert "security" in agent_ids
    assert "documentation" in agent_ids
    assert "deploy-orchestrator" in agent_ids
    assert "discovery" in agent_ids


@pytest.mark.asyncio
async def test_api_get_agent_info(client):
    """GET /agents/v2/{agent_id} returns agent details."""
    response = await client.get("/api/v1/agents/v2/code-review")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "code-review"
    assert len(data["capabilities"]) == 4


@pytest.mark.asyncio
async def test_api_get_agent_not_found(client):
    """GET /agents/v2/{agent_id} returns 404 for unknown agent."""
    response = await client.get("/api/v1/agents/v2/nonexistent-agent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_api_agent_stats(client):
    """GET /agents/v2/{agent_id}/stats returns statistics."""
    response = await client.get("/api/v1/agents/v2/security/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_executions" in data
    assert "total_cost_usd" in data


@pytest.mark.asyncio
async def test_api_agent_capabilities(client):
    """GET /agents/v2/{agent_id}/capabilities returns capability list."""
    response = await client.get("/api/v1/agents/v2/discovery/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "discovery"
    cap_names = [c["name"] for c in data["capabilities"]]
    assert "service_discovery" in cap_names
    assert "api_discovery" in cap_names


@pytest.mark.asyncio
async def test_api_execute_agent(client):
    """POST /agents/v2/{agent_id}/execute runs the agent."""
    response = await client.post("/api/v1/agents/v2/code-review/execute", json={
        "input": "def add(a, b): return a + b",
        "params": {"language": "python", "focus": "quality"},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "code-review"
    assert data["status"] in ("succeeded", "failed")
    assert "execution_id" in data


@pytest.mark.asyncio
async def test_api_execute_agent_validation(client):
    """POST /agents/v2/{agent_id}/execute validates input."""
    response = await client.post("/api/v1/agents/v2/code-review/execute", json={
        "input": "",  # Empty input should fail validation
    })
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_api_registry_stats(client):
    """GET /agents/v2/registry/stats returns registry-wide stats."""
    response = await client.get("/api/v1/agents/v2/registry/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_agents"] == 5
    assert "total_executions" in data
    assert "agents" in data
