"""
SevaForge Discovery Agent

Infrastructure and service discovery: scans environments, maps dependencies,
discovers APIs, and inventories cloud resources.

Capabilities:
  - service_discovery:   Find and catalog running services and endpoints
  - dependency_mapping:  Map inter-service dependencies from code and configs
  - api_discovery:       Discover and catalog API endpoints from code
  - resource_inventory:  Inventory cloud resources (GCP, AWS, Azure)
  - health_monitoring:   Monitor discovered services for health status
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability,
    AgentConfig,
    AgentExecutionContext,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# ── Discovery Patterns ──────────────────────────────────────────────

_SERVICE_PATTERNS = {
    "http_client": [
        r"requests\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)",
        r"httpx\.\w+\s*\(\s*['\"]([^'\"]+)",
        r"aiohttp\.ClientSession\(\)\.(?:get|post)\s*\(\s*['\"]([^'\"]+)",
        r"fetch\s*\(\s*['\"]([^'\"]+)",
    ],
    "database": [
        r"(?:postgres|mysql|mongodb|redis|sqlite)://[^\s'\"]+",
        r"(?:DATABASE|DB)_URL\s*[=:]\s*['\"]([^'\"]+)",
        r"create_engine\s*\(\s*['\"]([^'\"]+)",
    ],
    "message_queue": [
        r"(?:amqp|kafka)://[^\s'\"]+",
        r"(?:KAFKA|RABBIT|AMQP)_(?:URL|HOST|BROKER)\s*[=:]",
    ],
    "cache": [
        r"redis://[^\s'\"]+",
        r"memcached://[^\s'\"]+",
        r"REDIS_URL\s*[=:]",
    ],
    "cloud_service": [
        r"storage\.googleapis\.com",
        r"s3\.amazonaws\.com",
        r"blob\.core\.windows\.net",
        r"pubsub\.googleapis\.com",
        r"sqs\..*\.amazonaws\.com",
    ],
}

_API_ROUTE_PATTERNS = [
    r"@\w+\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    r"router\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    r"app\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
]

_IMPORT_DEPENDENCY_PATTERNS = [
    r"from\s+([\w.]+)\s+import",
    r"import\s+([\w.]+)",
    r"require\s*\(\s*['\"]([^'\"]+)['\"]",
]


class DiscoveryAgent(BaseAgent):
    """
    Infrastructure and service discovery agent.

    Scans code, configs, and environments to build a complete
    map of services, dependencies, APIs, and resources.
    """

    SYSTEM_PROMPT = """You are an infrastructure architect who excels at service discovery
and dependency mapping.

When analyzing code and configurations, identify:
1. All external service dependencies (APIs, databases, caches, queues)
2. Internal service-to-service communication patterns
3. Cloud resource dependencies (storage, compute, networking)
4. API surface area (all endpoints exposed)
5. Configuration dependencies (env vars, config files, secrets)
6. Potential single points of failure

Present findings as a clear service map with:
- Service name and type
- Connection details (sanitized — no credentials)
- Dependency direction (who calls whom)
- Health/availability status (if determinable)
- Risk assessment for each dependency"""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="discovery",
            name="Discovery Agent",
            description="Infrastructure and service discovery — maps dependencies, APIs, and resources",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="service_discovery", description="Find and catalog running services"),
                AgentCapability(name="dependency_mapping", description="Map inter-service dependencies from code"),
                AgentCapability(name="api_discovery", description="Discover and catalog API endpoints"),
                AgentCapability(name="resource_inventory", description="Inventory cloud resources"),
                AgentCapability(name="health_monitoring", description="Monitor discovered services for health"),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["discovery", "infrastructure", "dependencies", "api", "cloud"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute discovery scan.

        ctx.input: code, config files, or infrastructure description
        ctx.params:
          - scan_type: "full" | "services" | "apis" | "dependencies" | "resources"
          - project_name: str
          - language: str
        """
        code = ctx.input
        scan_type = ctx.params.get("scan_type", "full")
        project_name = ctx.params.get("project_name", "SevaForge")
        language = ctx.params.get("language", "python")

        discovery_result: dict[str, Any] = {
            "project_name": project_name,
            "scan_type": scan_type,
        }

        # ── Pattern-Based Discovery ──
        if scan_type in ("full", "services"):
            discovery_result["services"] = self._discover_services(code)

        if scan_type in ("full", "apis"):
            discovery_result["api_endpoints"] = self._discover_apis(code)

        if scan_type in ("full", "dependencies"):
            discovery_result["dependencies"] = self._discover_dependencies(code, language)

        if scan_type in ("full", "resources"):
            discovery_result["cloud_resources"] = self._discover_cloud_resources(code)

        # ── LLM Deep Analysis ──
        total_findings = sum(
            len(v) for k, v in discovery_result.items()
            if isinstance(v, list)
        )

        prompt = self._build_discovery_prompt(
            code, scan_type, project_name, language, discovery_result,
        )

        try:
            llm_response = await self.call_llm(ctx, prompt)

            discovery_result.update({
                "analysis": llm_response.content,
                "total_findings": total_findings,
                "architecture_notes": self._extract_architecture_notes(llm_response.content),
                "risk_areas": self._extract_risks(llm_response.content),
                "model_used": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "confidence": 0.85,
            })

        except Exception as exc:
            logger.warning("LLM analysis unavailable for discovery: %s", exc)
            discovery_result.update({
                "analysis": None,
                "total_findings": total_findings,
                "architecture_notes": [],
                "risk_areas": [],
                "model_used": "pattern-only",
                "input_tokens": 0,
                "output_tokens": 0,
                "confidence": 0.5,
            })

        return discovery_result

    # ── Service Discovery ────────────────────────────────────────────

    def _discover_services(self, code: str) -> list[dict[str, Any]]:
        """Discover external service dependencies from code patterns."""
        services = []
        seen = set()

        for service_type, patterns in _SERVICE_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.IGNORECASE):
                    # Use the full match as identifier to deduplicate
                    match_key = f"{service_type}:{match.group(0)[:50]}"
                    if match_key in seen:
                        continue
                    seen.add(match_key)

                    # Extract URL or identifier
                    groups = match.groups()
                    identifier = groups[-1] if groups else match.group(0)

                    # Sanitize — remove credentials
                    sanitized = re.sub(r"://[^@]+@", "://[REDACTED]@", str(identifier))

                    services.append({
                        "type": service_type,
                        "identifier": sanitized[:200],
                        "line": code[:match.start()].count("\n") + 1,
                        "status": "discovered",
                    })

        return services

    # ── API Discovery ────────────────────────────────────────────────

    def _discover_apis(self, code: str) -> list[dict[str, Any]]:
        """Discover API endpoints defined in code."""
        endpoints = []
        seen = set()

        for pattern in _API_ROUTE_PATTERNS:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                groups = match.groups()
                if len(groups) >= 2:
                    method = groups[0].upper()
                    path = groups[1]
                else:
                    continue

                key = f"{method}:{path}"
                if key in seen:
                    continue
                seen.add(key)

                # Find the function name on the next line
                line_num = code[:match.start()].count("\n") + 1
                func_name = "unknown"
                remaining = code[match.end():]
                func_match = re.search(r"(?:async\s+)?def\s+(\w+)", remaining[:200])
                if func_match:
                    func_name = func_match.group(1)

                endpoints.append({
                    "method": method,
                    "path": path,
                    "handler": func_name,
                    "line": line_num,
                    "auth_required": self._check_auth_required(code, match.start()),
                })

        return sorted(endpoints, key=lambda e: e["path"])

    # ── Dependency Discovery ─────────────────────────────────────────

    def _discover_dependencies(self, code: str, language: str) -> list[dict[str, Any]]:
        """Discover code dependencies (imports and requires)."""
        deps = []
        seen = set()

        for pattern in _IMPORT_DEPENDENCY_PATTERNS:
            for match in re.finditer(pattern, code):
                module = match.group(1)

                # Skip stdlib
                if module.split(".")[0] in _PYTHON_STDLIB:
                    continue

                if module in seen:
                    continue
                seen.add(module)

                dep_type = "internal" if module.startswith(("sevaforge", "forgeflow")) else "external"

                deps.append({
                    "module": module,
                    "type": dep_type,
                    "line": code[:match.start()].count("\n") + 1,
                })

        return deps

    # ── Cloud Resource Discovery ─────────────────────────────────────

    def _discover_cloud_resources(self, code: str) -> list[dict[str, Any]]:
        """Discover cloud resource references."""
        resources = []
        seen = set()

        cloud_patterns = {
            "gcp_storage": (r"gs://[\w\-./]+", "GCP Cloud Storage bucket"),
            "aws_s3": (r"s3://[\w\-./]+", "AWS S3 bucket"),
            "azure_blob": (r"https://\w+\.blob\.core\.windows\.net", "Azure Blob Storage"),
            "gcp_project": (r"projects/[\w\-]+", "GCP Project reference"),
            "aws_arn": (r"arn:aws:[\w\-:/*]+", "AWS ARN reference"),
            "docker_image": (r"(?:FROM|image:)\s+([\w\-./]+:[\w\-.]+)", "Docker image"),
        }

        for resource_type, (pattern, description) in cloud_patterns.items():
            for match in re.finditer(pattern, code):
                value = match.group(0)
                if value in seen:
                    continue
                seen.add(value)

                resources.append({
                    "type": resource_type,
                    "identifier": value[:200],
                    "description": description,
                    "line": code[:match.start()].count("\n") + 1,
                })

        return resources

    # ── Helpers ──────────────────────────────────────────────────────

    def _check_auth_required(self, code: str, route_pos: int) -> bool:
        """Check if an API route requires authentication."""
        # Look at surrounding context for auth dependencies
        context = code[max(0, route_pos - 200):route_pos + 500]
        auth_indicators = ["require_auth", "require_role", "Depends(", "Bearer", "jwt", "token"]
        return any(indicator in context for indicator in auth_indicators)

    def _build_discovery_prompt(
        self, code: str, scan_type: str, project_name: str,
        language: str, current_findings: dict[str, Any],
    ) -> str:
        """Build the LLM discovery prompt."""
        findings_summary = []
        for key, value in current_findings.items():
            if isinstance(value, list) and value:
                findings_summary.append(f"- {key}: {len(value)} items found")

        return f"""Analyze this {language} codebase for {project_name} and provide a comprehensive service discovery report.

Pattern-based scanning found:
{chr(10).join(findings_summary) if findings_summary else 'No pattern-based findings.'}

```{language}
{code[:4000]}
```

Provide:
1. Service architecture overview (what this code does and how it fits together)
2. Any dependencies the pattern scanner may have missed
3. Data flow analysis (how data moves between components)
4. Potential single points of failure
5. Recommendations for improving observability and resilience"""

    def _extract_architecture_notes(self, text: str) -> list[str]:
        """Extract architecture-relevant notes from LLM output."""
        notes = []
        for line in text.split("\n"):
            line = line.strip()
            if line and len(line) > 20 and any(
                kw in line.lower()
                for kw in ["architecture", "pattern", "design", "component", "service", "layer"]
            ):
                notes.append(line.lstrip("- #*").strip()[:200])
                if len(notes) >= 10:
                    break
        return notes

    def _extract_risks(self, text: str) -> list[str]:
        """Extract risk areas from LLM output."""
        risks = []
        for line in text.split("\n"):
            line = line.strip()
            if line and any(
                kw in line.lower()
                for kw in ["risk", "failure", "vulnerability", "single point", "bottleneck", "concern"]
            ):
                risks.append(line.lstrip("- #*").strip()[:200])
                if len(risks) >= 10:
                    break
        return risks


# ── Python stdlib modules (for filtering dependencies) ──────────────

_PYTHON_STDLIB = {
    "abc", "asyncio", "base64", "collections", "contextlib", "copy",
    "dataclasses", "datetime", "decimal", "enum", "functools", "hashlib",
    "hmac", "http", "importlib", "inspect", "io", "itertools", "json",
    "logging", "math", "os", "pathlib", "pickle", "platform", "pprint",
    "queue", "random", "re", "secrets", "shutil", "signal", "socket",
    "sqlite3", "ssl", "string", "struct", "subprocess", "sys",
    "tempfile", "textwrap", "threading", "time", "traceback", "typing",
    "unittest", "urllib", "uuid", "warnings", "xml", "zipfile",
}
