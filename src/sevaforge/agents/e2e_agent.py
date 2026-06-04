"""
SevaForge E2E Testing Agent

Generates Playwright and Cypress E2E test setups.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)


class E2ETestingAgent(BaseAgent):
    SYSTEM_PROMPT = "You are an E2E testing expert specialising in Playwright and Cypress."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="e2e-testing", name="E2E Testing Agent",
            description="Generates Playwright and Cypress E2E test setups",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="generate_playwright_setup", description="Generate Playwright config and tests"),
                AgentCapability(name="generate_cypress_setup", description="Generate Cypress config and tests"),
                AgentCapability(name="generate_e2e_workflow", description="Generate CI E2E workflow"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["e2e", "testing", "playwright", "cypress"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        framework = ctx.params.get("framework", "playwright")
        app_name = ctx.params.get("app_name", "my-app")
        port = ctx.params.get("port") or self._detect_port(code)
        try:
            llm_response = await self.call_llm(ctx, f"Generate E2E test scenarios for '{app_name}' using {framework}.\nCode:\n```\n{code[:4000]}\n```")
            return {"framework": framework, "app_name": app_name, "port": port, "llm_scenarios": llm_response.content, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.85}
        except Exception:
            return {"framework": framework, "app_name": app_name, "port": port, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.65}

    def _detect_port(self, code):
        for pattern in [r"port:\s*(\d+)", r"PORT\s*[=:]\s*(\d+)", r"listen\s*\(\s*(\d+)"]:
            match = re.search(pattern, code)
            if match:
                return int(match.group(1))
        return 3000
