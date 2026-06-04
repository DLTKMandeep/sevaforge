"""
SevaForge Lifecycle Agent

Generates chained CI / Test / CD workflow definitions for GitHub Actions.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent, AgentConfig, AgentCapability, AgentExecutionContext,
)

logger = logging.getLogger(__name__)

_CI_TEMPLATES = {
    "python": "name: CI\non:\n  push:\n    branches: [main, develop]\n  pull_request:\n    branches: [main]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - run: pip install -e '.[dev]'\n      - run: ruff check .\n      - run: mypy src/\n",
    "node": "name: CI\non:\n  push:\n    branches: [main, develop]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: '20'\n      - run: npm ci\n      - run: npm run lint\n      - run: npm run build\n",
}


class LifecycleAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a DevOps engineer who designs CI/CD pipelines for GitHub Actions."

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="lifecycle", name="Lifecycle Agent",
            description="Generates chained CI/Test/CD workflows for GitHub Actions",
            version="1.0.0",
            capabilities=[
                AgentCapability(name="generate_ci_workflow", description="Create CI pipeline"),
                AgentCapability(name="generate_test_workflow", description="Create test pipeline"),
                AgentCapability(name="generate_cd_workflow", description="Create CD pipeline"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["ci", "cd", "lifecycle", "github-actions"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        language = ctx.params.get("language", "python")
        workflows = {"ci.yml": _CI_TEMPLATES.get(language, _CI_TEMPLATES["python"])}
        try:
            llm_response = await self.call_llm(ctx, f"Optimise these GitHub Actions workflows for a {language} project.\n{workflows}")
            return {"workflows": workflows, "optimisations": llm_response.content, "language": language, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.85}
        except Exception:
            return {"workflows": workflows, "language": language, "model_used": "template-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.7}
