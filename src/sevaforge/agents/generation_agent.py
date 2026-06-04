"""
SevaForge Generation Agent

Orchestrator facade that coordinates code generation across specialist agents.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent, AgentConfig, AgentCapability, AgentExecutionContext,
)

logger = logging.getLogger(__name__)

_LANGUAGE_INDICATORS = {"python": [r"\.py\b", r"import\s+\w+"], "node": [r"package\.json", r"require\s*\("], "go": [r"go\.mod", r"func\s+\w+"], "java": [r"pom\.xml", r"public\s+class"]}
_CLOUD_INDICATORS = {"aws": [r"aws", r"s3", r"ec2"], "gcp": [r"gcp", r"google", r"gke"], "azure": [r"azure", r"aks"]}


class GenerationAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a principal DevOps architect who coordinates infrastructure and CI/CD generation."

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="generation", name="Generation Agent",
            description="Orchestrator facade for full-stack generation",
            version="1.0.0",
            capabilities=[
                AgentCapability(name="generate_full_stack", description="Generate IaC + CI + CD from project description"),
                AgentCapability(name="generate_iac_only", description="Generate infrastructure-as-code only"),
                AgentCapability(name="generate_cicd_only", description="Generate CI/CD pipelines only"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["generation", "orchestrator", "iac", "cicd"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        description = ctx.input
        analysis = self._analyze_project(description)
        cloud = ctx.params.get("cloud", analysis["cloud"])
        language = ctx.params.get("language", analysis["language"])
        try:
            llm_response = await self.call_llm(ctx, f"Create a generation plan for a {language} project on {cloud.upper()}.\nDescription: {description[:2000]}")
            return {"analysis": analysis, "plan": llm_response.content, "language": language, "cloud": cloud, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.8}
        except Exception:
            return {"analysis": analysis, "plan": f"Standard generation for {language} on {cloud}", "language": language, "cloud": cloud, "model_used": "template-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.5}

    def _analyze_project(self, description):
        text = description.lower()
        lang_scores = {lang: sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns) for lang, patterns in _LANGUAGE_INDICATORS.items()}
        language = max(lang_scores, key=lambda k: lang_scores[k]) if any(lang_scores.values()) else "python"
        cloud_scores = {cloud: sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns) for cloud, patterns in _CLOUD_INDICATORS.items()}
        cloud = max(cloud_scores, key=lambda k: cloud_scores[k]) if any(cloud_scores.values()) else "aws"
        return {"language": language, "cloud": cloud}
