"""
SevaForge IAM Agent

Generates IAM policies and service account configurations for multi-cloud.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)

_CLOUD_INDICATORS = {"aws": ["aws_", "eks", "ecr", "AWS_"], "gcp": ["google_", "gke", "GCP"], "azure": ["azurerm_", "aks", "AZURE"]}


class IAMAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a cloud security engineer specialising in IAM and least-privilege access."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="iam-policy", name="IAM Policy Agent",
            description="Generates IAM policies and service account configs",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="generate_iam_policies", description="Generate cloud-specific IAM policies"),
                AgentCapability(name="generate_verify_script", description="Generate verification shell script"),
                AgentCapability(name="detect_cloud", description="Auto-detect target cloud"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["iam", "security", "policies", "cloud"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        cloud = ctx.params.get("cloud", "").lower() or self._detect_cloud(code)
        app_name = ctx.params.get("app_name", "my-app")
        try:
            llm_response = await self.call_llm(ctx, f"Review IAM requirements for '{app_name}' on {cloud.upper()}.\n```\n{code[:3000]}\n```")
            return {"cloud": cloud, "app_name": app_name, "llm_recommendations": llm_response.content, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.9}
        except Exception:
            return {"cloud": cloud, "app_name": app_name, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.7}

    def _detect_cloud(self, code):
        scores = {cloud: sum(1 for ind in indicators if ind in code) for cloud, indicators in _CLOUD_INDICATORS.items()}
        return max(scores, key=scores.get) if any(scores.values()) else "aws"
