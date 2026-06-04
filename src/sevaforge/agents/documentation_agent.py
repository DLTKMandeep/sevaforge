"""
SevaForge Documentation Agent

Generates comprehensive documentation from code.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability, AgentConfig, AgentExecutionContext, BaseAgent,
)

logger = logging.getLogger(__name__)


class DocumentationAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a technical writer who creates clear, comprehensive documentation for enterprise software."

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="documentation", name="Documentation Agent",
            description="Generates API docs, READMEs, docstrings, and architecture documentation",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="api_docs", description="Generate API documentation"),
                AgentCapability(name="readme_gen", description="Generate README.md files"),
                AgentCapability(name="docstring_gen", description="Generate function docstrings"),
                AgentCapability(name="changelog_gen", description="Generate changelog entries"),
                AgentCapability(name="arch_overview", description="Generate architecture documentation"),
            ],
            system_prompt=self.SYSTEM_PROMPT, default_model="claude-sonnet-4-20250514",
            tags=["documentation", "api", "readme", "docstring"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        doc_type = ctx.params.get("doc_type", "api_docs")
        project_name = ctx.params.get("project_name", "SevaForge")
        language = ctx.params.get("language", "python")
        structure = self._analyze_code_structure(code, language)
        prompt = f"Generate {doc_type} documentation for this {language} code from {project_name}.\n```{language}\n{code}\n```"
        try:
            llm_response = await self.call_llm(ctx, prompt)
            return {"documentation": llm_response.content, "doc_type": doc_type, "project_name": project_name, "structure": structure, "model_used": llm_response.model, "input_tokens": llm_response.input_tokens, "output_tokens": llm_response.output_tokens, "confidence": 0.85}
        except Exception:
            minimal = f"# {project_name}\n\n## Classes: {len(structure['classes'])}\n## Functions: {len(structure['functions'])}"
            return {"documentation": minimal, "doc_type": doc_type, "project_name": project_name, "structure": structure, "model_used": "template-only", "input_tokens": 0, "output_tokens": 0, "confidence": 0.4}

    def _analyze_code_structure(self, code, language):
        structure = {"classes": [], "functions": [], "imports": [], "routes": [], "total_lines": len(code.splitlines())}
        if language != "python":
            return structure
        for line_num, line in enumerate(code.splitlines(), 1):
            stripped = line.strip()
            cm = re.match(r"class\s+(\w+)(?:\(([^)]*)\))?:", stripped)
            if cm:
                structure["classes"].append({"name": cm.group(1), "line": line_num})
            fm = re.match(r"(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", stripped)
            if fm:
                structure["functions"].append({"name": fm.group(1), "line": line_num, "is_private": fm.group(1).startswith("_")})
        return structure
