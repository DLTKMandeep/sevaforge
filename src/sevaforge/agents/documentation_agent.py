"""
SevaForge Documentation Agent

Generates comprehensive documentation from code: API docs, README files,
architecture overviews, inline docstrings, and change logs.

Capabilities:
  - api_docs:        Generate API documentation from route definitions
  - readme_gen:      Generate or update README.md files
  - docstring_gen:   Generate/improve function and class docstrings
  - changelog_gen:   Generate changelog entries from git commits
  - arch_overview:   Generate architecture documentation
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


class DocumentationAgent(BaseAgent):
    """
    Enterprise documentation generation agent.

    Analyzes code structure and generates professional documentation
    using LLM for natural language quality.
    """

    SYSTEM_PROMPT = """You are a technical writer who creates clear, comprehensive documentation
for enterprise software.

Your documentation should:
- Be concise but complete
- Use consistent formatting (Markdown)
- Include code examples where helpful
- Follow the Diátaxis framework: tutorials, how-to guides, reference, explanation
- Use active voice and present tense
- Include parameter descriptions and return types
- Note any caveats, limitations, or prerequisites

Audience: senior developers who are new to this codebase."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="documentation",
            name="Documentation Agent",
            description="Generates API docs, READMEs, docstrings, and architecture documentation",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="api_docs", description="Generate API documentation from route definitions"),
                AgentCapability(name="readme_gen", description="Generate or update README.md files"),
                AgentCapability(name="docstring_gen", description="Generate/improve function and class docstrings"),
                AgentCapability(name="changelog_gen", description="Generate changelog entries from git commits"),
                AgentCapability(name="arch_overview", description="Generate architecture documentation"),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["documentation", "api", "readme", "docstring"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Generate documentation.

        ctx.input: source code or content to document
        ctx.params:
          - doc_type: "api_docs" | "readme" | "docstring" | "changelog" | "arch_overview"
          - project_name: str
          - language: str
          - existing_docs: str (current docs to update)
        """
        code = ctx.input
        doc_type = ctx.params.get("doc_type", "api_docs")
        project_name = ctx.params.get("project_name", "SevaForge")
        language = ctx.params.get("language", "python")

        # Extract structural info from code
        code_structure = self._analyze_code_structure(code, language)

        # Build doc-type-specific prompt
        prompt = self._build_doc_prompt(code, doc_type, project_name, language, code_structure, ctx.params)

        try:
            llm_response = await self.call_llm(ctx, prompt)
            documentation = llm_response.content

            return {
                "documentation": documentation,
                "doc_type": doc_type,
                "project_name": project_name,
                "language": language,
                "structure": code_structure,
                "word_count": len(documentation.split()),
                "model_used": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "confidence": 0.85,
            }

        except Exception as exc:
            logger.warning("LLM unavailable, generating minimal docs: %s", exc)
            minimal = self._generate_minimal_docs(code_structure, doc_type, project_name)
            return {
                "documentation": minimal,
                "doc_type": doc_type,
                "project_name": project_name,
                "language": language,
                "structure": code_structure,
                "word_count": len(minimal.split()),
                "model_used": "template-only",
                "input_tokens": 0,
                "output_tokens": 0,
                "confidence": 0.4,
            }

    # ── Code Structure Analysis ──────────────────────────────────────

    def _analyze_code_structure(self, code: str, language: str) -> dict[str, Any]:
        """Extract structural information from code."""
        structure: dict[str, Any] = {
            "classes": [],
            "functions": [],
            "imports": [],
            "routes": [],
            "constants": [],
            "total_lines": len(code.splitlines()),
        }

        if language != "python":
            return structure

        for line_num, line in enumerate(code.splitlines(), 1):
            stripped = line.strip()

            # Classes
            class_match = re.match(r"class\s+(\w+)(?:\(([^)]*)\))?:", stripped)
            if class_match:
                structure["classes"].append({
                    "name": class_match.group(1),
                    "bases": class_match.group(2) or "",
                    "line": line_num,
                })

            # Functions/Methods
            func_match = re.match(r"(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", stripped)
            if func_match:
                structure["functions"].append({
                    "name": func_match.group(1),
                    "params": func_match.group(2),
                    "line": line_num,
                    "is_async": stripped.startswith("async"),
                    "is_private": func_match.group(1).startswith("_"),
                })

            # Imports
            if stripped.startswith("import ") or stripped.startswith("from "):
                structure["imports"].append(stripped)

            # FastAPI routes
            route_match = re.match(r"@\w+\.(get|post|put|patch|delete)\s*\(['\"]([^'\"]+)", stripped)
            if route_match:
                structure["routes"].append({
                    "method": route_match.group(1).upper(),
                    "path": route_match.group(2),
                    "line": line_num,
                })

            # Constants
            const_match = re.match(r"([A-Z_]{2,})\s*[=:]", stripped)
            if const_match and not stripped.startswith("#"):
                structure["constants"].append(const_match.group(1))

        return structure

    # ── Prompt Building ──────────────────────────────────────────────

    def _build_doc_prompt(
        self, code: str, doc_type: str, project_name: str,
        language: str, structure: dict[str, Any], params: dict[str, Any],
    ) -> str:
        """Build a doc-type-specific prompt."""

        if doc_type == "api_docs":
            return f"""Generate API reference documentation for this {language} code from {project_name}.

The code has {len(structure['routes'])} API routes, {len(structure['classes'])} classes,
and {len(structure['functions'])} functions.

```{language}
{code}
```

For each route, document:
- HTTP method and path
- Request body / query parameters
- Response format with example
- Error codes
- Authentication requirements

For each public class/function, document:
- Purpose and usage
- Parameters with types
- Return values
- Exceptions raised
- Code example"""

        elif doc_type == "readme":
            return f"""Generate a comprehensive README.md for {project_name}.

Code structure:
- {len(structure['classes'])} classes
- {len(structure['functions'])} functions
- {len(structure['routes'])} API routes

```{language}
{code}
```

Include sections:
1. Project title and description
2. Features (bullet list)
3. Quick Start (installation + first run)
4. Configuration
5. API Reference (summary table)
6. Architecture Overview
7. Contributing guidelines
8. License"""

        elif doc_type == "docstring":
            return f"""Add or improve Python docstrings for all public classes and functions in this code.

```{language}
{code}
```

Use Google-style docstrings with:
- One-line summary
- Extended description (if needed)
- Args section with types
- Returns section with type
- Raises section (if applicable)
- Example usage (if the function is complex)

Return the complete code with improved docstrings."""

        elif doc_type == "changelog":
            existing = params.get("existing_docs", "")
            return f"""Generate changelog entries based on the code changes below.

Previous documentation:
{existing[:2000] if existing else 'No previous docs.'}

Current code:
```{language}
{code}
```

Use Keep a Changelog format:
## [Version] - YYYY-MM-DD
### Added / Changed / Fixed / Removed"""

        else:  # arch_overview
            return f"""Generate an architecture overview document for {project_name}.

```{language}
{code}
```

Cover:
1. System overview and purpose
2. Component architecture (classes and their relationships)
3. Data flow
4. Key design decisions and patterns used
5. Extension points
6. Dependencies"""

    # ── Fallback Minimal Docs ────────────────────────────────────────

    def _generate_minimal_docs(
        self, structure: dict[str, Any], doc_type: str, project_name: str,
    ) -> str:
        """Generate minimal template-based docs when LLM is unavailable."""
        lines = [f"# {project_name}\n"]

        if doc_type == "api_docs" and structure["routes"]:
            lines.append("## API Endpoints\n")
            lines.append("| Method | Path | Line |")
            lines.append("|--------|------|------|")
            for route in structure["routes"]:
                lines.append(f"| {route['method']} | `{route['path']}` | {route['line']} |")
            lines.append("")

        if structure["classes"]:
            lines.append("## Classes\n")
            for cls in structure["classes"]:
                bases = f" ({cls['bases']})" if cls["bases"] else ""
                lines.append(f"- **{cls['name']}**{bases} — line {cls['line']}")
            lines.append("")

        if structure["functions"]:
            public_funcs = [f for f in structure["functions"] if not f["is_private"]]
            if public_funcs:
                lines.append("## Public Functions\n")
                for func in public_funcs:
                    async_prefix = "async " if func["is_async"] else ""
                    lines.append(f"- `{async_prefix}{func['name']}({func['params']})` — line {func['line']}")
                lines.append("")

        return "\n".join(lines)
