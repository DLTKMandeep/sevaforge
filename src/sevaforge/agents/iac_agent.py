"""
SevaForge IAC Agent

Generates Infrastructure as Code: Terraform, Dockerfiles, and docker-compose.
"""

from __future__ import annotations

import logging
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)

_DOCKERFILES = {
    "python": "FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nRUN useradd --create-home appuser && chown -R appuser:appuser /app\nUSER appuser\nEXPOSE 8000\nCMD [\"python\", \"-m\", \"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n",
    "javascript": "FROM node:20-alpine\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci --only=production\nCOPY . .\nUSER node\nEXPOSE 3000\nCMD [\"node\", \"index.js\"]\n",
    "go": "FROM golang:1.21-alpine AS builder\nWORKDIR /app\nCOPY go.mod go.sum* ./\nRUN go mod download\nCOPY . .\nRUN CGO_ENABLED=0 go build -o /app/main .\nFROM alpine:3.18\nCOPY --from=builder /app/main /app/main\nEXPOSE 8080\nCMD [\"/app/main\"]\n",
}


class IACAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a cloud infrastructure architect specializing in Terraform, Docker, and Kubernetes."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="infrastructure-as-code", name="IAC Agent",
            description="Generates Terraform, Dockerfiles, and docker-compose",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="generate_terraform", description="Generate cloud-specific Terraform"),
                AgentCapability(name="generate_dockerfile", description="Generate language-specific Dockerfiles"),
                AgentCapability(name="generate_docker_compose", description="Generate docker-compose.yml"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["iac", "terraform", "docker", "infrastructure"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        language = ctx.params.get("language", "python").lower()
        cloud = ctx.params.get("cloud", "aws").lower()
        app_name = ctx.params.get("app_name", "my-app")
        configs = {"dockerfile": _DOCKERFILES.get(language, _DOCKERFILES["python"])}
        try:
            llm_response = await self.call_llm(ctx, f"Recommend infrastructure for '{app_name}' ({language}) on {cloud.upper()}.\n```\n{code[:3000]}\n```")
            return {"configs": configs, "app_name": app_name, "language": language, "cloud": cloud, "llm_recommendations": llm_response.content, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.9}
        except Exception:
            return {"configs": configs, "app_name": app_name, "language": language, "cloud": cloud, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.7}
