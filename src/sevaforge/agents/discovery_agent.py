"""
SevaForge Discovery Agent

Infrastructure and service discovery: scans environments, maps dependencies,
discovers APIs, and inventories cloud resources.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)

_SERVICE_PATTERNS = {
    "http_client": [r"requests\.(get|post|put|delete)\s*\(\s*['\"]([^'\"]+)", r"fetch\s*\(\s*['\"]([^'\"]+)"],
    "database": [r"(?:postgres|mysql|mongodb|redis|sqlite)://[^\s'\"]+", r"create_engine\s*\(\s*['\"]([^'\"]+)"],
    "message_queue": [r"(?:amqp|kafka)://[^\s'\"]+"],
    "cache": [r"redis://[^\s'\"]+"],
    "cloud_service": [r"storage\.googleapis\.com", r"s3\.amazonaws\.com"],
}
_API_ROUTE_PATTERNS = [r"@\w+\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]", r"router\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]"]


class DiscoveryAgent(BaseAgent):
    SYSTEM_PROMPT = "You are an infrastructure architect who excels at service discovery and dependency mapping."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="discovery", name="Discovery Agent",
            description="Infrastructure and service discovery",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="service_discovery", description="Find and catalog running services"),
                AgentCapability(name="dependency_mapping", description="Map inter-service dependencies"),
                AgentCapability(name="api_discovery", description="Discover and catalog API endpoints"),
                AgentCapability(name="resource_inventory", description="Inventory cloud resources"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["discovery", "infrastructure", "dependencies", "api"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        services = self._discover_services(code)
        apis = self._discover_apis(code)
        total = len(services) + len(apis)
        try:
            llm_response = await self.call_llm(ctx, f"Analyze this codebase for service discovery.\n```\n{code[:4000]}\n```")
            return {"services": services, "api_endpoints": apis, "total_findings": total, "analysis": llm_response.content, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.85}
        except Exception:
            return {"services": services, "api_endpoints": apis, "total_findings": total, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.5}

    def _discover_services(self, code):
        services = []
        seen = set()
        for svc_type, patterns in _SERVICE_PATTERNS.items():
            for pattern in patterns:
                for match in re.finditer(pattern, code, re.IGNORECASE):
                    key = f"{svc_type}:{match.group(0)[:50]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    sanitized = re.sub(r"://[^@]+@", "://[REDACTED]@", match.group(0))
                    services.append({"type": svc_type, "identifier": sanitized[:200], "line": code[:match.start()].count("\n") + 1})
        return services

    def _discover_apis(self, code):
        endpoints = []
        seen = set()
        for pattern in _API_ROUTE_PATTERNS:
            for match in re.finditer(pattern, code, re.IGNORECASE):
                groups = match.groups()
                if len(groups) >= 2:
                    method, path = groups[0].upper(), groups[1]
                    key = f"{method}:{path}"
                    if key not in seen:
                        seen.add(key)
                        endpoints.append({"method": method, "path": path, "line": code[:match.start()].count("\n") + 1})
        return sorted(endpoints, key=lambda e: e["path"])
