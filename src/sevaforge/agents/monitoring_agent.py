"""
SevaForge Monitoring Agent

Generates Prometheus configs, alert rules, and Grafana dashboards.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)

_FRAMEWORK_SIGNATURES = {
    "fastapi": {"patterns": [r"FastAPI", r"fastapi"], "port": 8000, "metrics_path": "/metrics"},
    "flask": {"patterns": [r"Flask\(", r"flask"], "port": 5000, "metrics_path": "/metrics"},
    "express": {"patterns": [r"express\(\)"], "port": 3000, "metrics_path": "/metrics"},
}


class MonitoringAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a site reliability engineer specializing in observability, Prometheus, and Grafana."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="monitoring", name="Monitoring Agent",
            description="Generates Prometheus configs, alert rules, and Grafana dashboards",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="generate_prometheus_config", description="Generate Prometheus scrape config"),
                AgentCapability(name="generate_alert_rules", description="Generate PromQL alert rules"),
                AgentCapability(name="generate_grafana_dashboard", description="Generate Grafana dashboard JSON"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["monitoring", "prometheus", "grafana", "alerting"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        app_name = ctx.params.get("app_name", "my-app")
        framework, port, metrics_path = self._detect_framework(code, ctx.params.get("framework"), ctx.params.get("port"), ctx.params.get("metrics_path"))
        try:
            llm_response = await self.call_llm(ctx, f"Recommend monitoring for '{app_name}' ({framework}, port {port}).\n```\n{code[:3000]}\n```")
            return {"app_name": app_name, "framework": framework, "port": port, "llm_recommendations": llm_response.content, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.9}
        except Exception:
            return {"app_name": app_name, "framework": framework, "port": port, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.7}

    def _detect_framework(self, code, override_fw, override_port, override_path):
        if override_fw:
            sig = _FRAMEWORK_SIGNATURES.get(override_fw, {})
            return (override_fw, override_port or sig.get("port", 8000), override_path or sig.get("metrics_path", "/metrics"))
        for fw_name, sig in _FRAMEWORK_SIGNATURES.items():
            for pattern in sig["patterns"]:
                if re.search(pattern, code):
                    return (fw_name, override_port or sig["port"], override_path or sig["metrics_path"])
        return ("generic", override_port or 8000, override_path or "/metrics")
