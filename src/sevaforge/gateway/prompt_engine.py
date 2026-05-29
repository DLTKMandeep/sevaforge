"""
SevaForge AI Gateway — Prompt Assembly Engine
Assembles structured prompts from Jinja2 templates + variables.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from sevaforge.config import get_settings
from sevaforge.models.schemas import AssembledPrompt, PromptMessage

logger = logging.getLogger(__name__)


class PromptTemplate:
    """Loaded prompt template with metadata."""

    def __init__(self, template_id: str, raw: dict[str, Any]):
        self.template_id = template_id
        self.version = raw.get("version", "1.0.0")
        self.description = raw.get("description", "")
        self.model_hint = raw.get("model_hint", "")
        self.max_tokens = raw.get("max_tokens", 4096)
        self.messages: list[dict[str, str]] = raw.get("messages", [])
        self.variables: list[str] = raw.get("variables", [])


class PromptEngine:
    """
    Assembles structured prompts from YAML template files.

    Each template is a YAML file with:
      - version, description, model_hint
      - messages: list of {role, content} where content is Jinja2
      - variables: list of expected variable names

    Usage:
        engine = PromptEngine()
        prompt = engine.assemble("code-review", {"code": "...", "language": "python"})
    """

    def __init__(self, template_dir: str | None = None):
        settings = get_settings()
        self._template_dir = Path(template_dir or settings.prompt_template_dir)
        self._templates: dict[str, PromptTemplate] = {}
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=False,
            keep_trailing_newline=True,
        )
        self._load_templates()

    def _load_templates(self) -> None:
        """Discover and load all YAML templates from the template directory."""
        if not self._template_dir.exists():
            logger.warning("Template directory does not exist: %s", self._template_dir)
            return

        for path in sorted(self._template_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    raw = yaml.safe_load(f)
                if raw and isinstance(raw, dict):
                    template_id = path.stem
                    self._templates[template_id] = PromptTemplate(template_id, raw)
                    logger.info("Loaded prompt template: %s (v%s)", template_id, raw.get("version", "?"))
            except Exception as e:
                logger.error("Failed to load template %s: %s", path.name, e)

    def list_templates(self) -> list[dict[str, str]]:
        """Return metadata for all loaded templates."""
        return [
            {
                "template_id": t.template_id,
                "version": t.version,
                "description": t.description,
                "variables": t.variables,
            }
            for t in self._templates.values()
        ]

    def assemble(self, template_id: str, variables: dict[str, Any] | None = None) -> AssembledPrompt:
        """
        Render a template with the given variables into an AssembledPrompt.

        Args:
            template_id: The template name (YAML filename without extension).
            variables: Dict of variables to inject into the Jinja2 template.

        Returns:
            AssembledPrompt with rendered messages and metadata.

        Raises:
            KeyError: If template_id is not found.
        """
        variables = variables or {}

        if template_id not in self._templates:
            raise KeyError(f"Prompt template not found: {template_id}")

        template = self._templates[template_id]

        # Validate required variables
        missing = [v for v in template.variables if v not in variables]
        if missing:
            logger.warning("Missing variables for template '%s': %s", template_id, missing)

        # Render each message through Jinja2
        messages: list[PromptMessage] = []
        for msg in template.messages:
            try:
                rendered_content = self._jinja_env.from_string(msg["content"]).render(**variables)
            except Exception as e:
                logger.error("Failed to render message in %s: %s", template_id, e)
                rendered_content = msg["content"]

            messages.append(PromptMessage(role=msg["role"], content=rendered_content.strip()))

        # Estimate token count (rough: 1 token ~ 4 chars)
        total_chars = sum(len(m.content) for m in messages)
        estimated_tokens = total_chars // 4

        return AssembledPrompt(
            messages=messages,
            template_id=template_id,
            template_version=template.version,
            variables=variables,
            estimated_tokens=estimated_tokens,
        )

    def hash_prompt(self, prompt: AssembledPrompt) -> str:
        """Generate a deterministic hash for cache keying."""
        content = "|".join(f"{m.role}:{m.content}" for m in prompt.messages)
        return hashlib.sha256(content.encode()).hexdigest()

    def reload(self) -> None:
        """Hot-reload all templates from disk."""
        self._templates.clear()
        self._load_templates()
        logger.info("Prompt templates reloaded (%d loaded)", len(self._templates))
