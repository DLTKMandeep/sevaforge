"""
SevaForge Diagram Agent

Generates architecture diagrams and system visualizations from code
analysis. Produces Mermaid syntax for flowcharts, sequence diagrams,
and C4 diagrams.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent, AgentConfig, AgentCapability, AgentExecutionContext,
)

logger = logging.getLogger(__name__)

_SERVICE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "api_gateway": [re.compile(r"(?:FastAPI|Flask|Express|Gin|Spring)\s*\("), re.compile(r"@app\.(get|post|put|delete|patch)\s*\(")],
    "database": [re.compile(r"(?:postgres|mysql|mongodb|sqlite)://", re.IGNORECASE), re.compile(r"create_engine\s*\(")],
    "cache": [re.compile(r"redis://", re.IGNORECASE), re.compile(r"Redis\s*\(")],
    "message_queue": [re.compile(r"(?:amqp|kafka)://", re.IGNORECASE)],
    "object_storage": [re.compile(r"(?:s3|gs|wasb)://")],
    "auth_service": [re.compile(r"(?:JWT|OAuth|OIDC)", re.IGNORECASE)],
    "monitoring": [re.compile(r"(?:Prometheus|Grafana|Datadog)", re.IGNORECASE)],
}


class DiagramAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a software architect who creates clear, informative system diagrams using Mermaid syntax."

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="diagram", name="Diagram Agent",
            description="Generates architecture diagrams from code analysis",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="generate_architecture_diagram", description="Generate C4-style architecture diagram"),
                AgentCapability(name="generate_flow_diagram", description="Generate request flow sequence diagram"),
                AgentCapability(name="generate_deployment_diagram", description="Generate deployment topology diagram"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["diagram", "architecture", "mermaid", "visualization"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        diagram_type = ctx.params.get("diagram_type", "architecture")
        project_name = ctx.params.get("project_name", "System")
        detected = self._detect_components(code)
        mermaid = self._generate_architecture_diagram(detected, project_name)

        try:
            llm_response = await self.call_llm(ctx, f"Improve this {diagram_type} diagram for {project_name}.\nBase diagram:\n```mermaid\n{mermaid}\n```\nCode sample:\n```\n{code[:2500]}\n```")
            enhanced = self._extract_mermaid(llm_response.content)
            if enhanced:
                mermaid = enhanced
            return {"mermaid": mermaid, "diagram_type": diagram_type, "project_name": project_name, "detected_services": detected, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.8}
        except Exception:
            return {"mermaid": mermaid, "diagram_type": diagram_type, "project_name": project_name, "detected_services": detected, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.55}

    def _detect_components(self, code):
        components = []
        seen = set()
        for svc_type, patterns in _SERVICE_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(code):
                    key = f"{svc_type}:{match.group(0)[:40]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    components.append({"type": svc_type, "match": match.group(0)[:80], "line": code[:match.start()].count("\n") + 1})
        return components

    def _generate_architecture_diagram(self, components, project_name):
        lines = ["graph TD", f'    User(("{project_name} User"))']
        by_type = {}
        for comp in components:
            by_type.setdefault(comp["type"], []).append(comp)
        node_id = 0
        type_nodes = {}
        for svc_type, items in by_type.items():
            node_id += 1
            nid = f"S{node_id}"
            label = svc_type.replace("_", " ").title()
            lines.append(f'    {nid}["{label}"]')
            type_nodes[svc_type] = nid
        if "api_gateway" in type_nodes:
            lines.append(f'    User --> {type_nodes["api_gateway"]}')
            for dep in ["database", "cache", "message_queue", "auth_service"]:
                if dep in type_nodes:
                    lines.append(f'    {type_nodes["api_gateway"]} --> {type_nodes[dep]}')
        return "\n".join(lines)

    @staticmethod
    def _extract_mermaid(text):
        m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
        return m.group(1).strip() if m else ""
