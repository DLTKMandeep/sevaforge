"""
SevaForge BasePersona -- Abstract intermediary between BaseAgent and concrete
deployment personas.

Each persona owns a slice of the deployment surface (Dockerfiles, Terraform,
Helm charts, etc.) and produces artifacts driven by a deployment-intent
document.  BasePersona handles:

    * persona_name / owned_paths metadata
    * Loading the intent dict from ``ctx.params``
    * Delegating to the concrete ``_produce_artifacts()`` hook
    * A ``write_artifact()`` helper that returns a tracking dict
"""

from __future__ import annotations

import abc
import logging
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)

logger = logging.getLogger(__name__)


class BasePersona(BaseAgent, abc.ABC):
    """Abstract base for all deployment personas.

    Subclasses must set ``persona_name`` and ``owned_paths`` and implement
    ``_produce_artifacts``.
    """

    # -- Persona metadata (overridden by concrete subclasses) ----------------

    persona_name: str = "base"
    owned_paths: list[str] = []

    # -- Construction --------------------------------------------------------

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        logger.info(
            "Persona '%s' initialised (agent_id=%s, owned_paths=%s)",
            self.persona_name,
            self.agent_id,
            self.owned_paths,
        )

    # -- Public interface ----------------------------------------------------

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """Load the deployment intent and delegate to ``_produce_artifacts``.

        The intent is expected in ``ctx.params["intent"]`` as a plain dict
        (parsed from a YAML deployment-intent document upstream).  If absent
        an empty dict is used, which lets personas produce sensible defaults.

        Returns a structured dict with keys:
            persona   -- persona name
            artifacts -- list of generated file descriptors
            findings  -- list of observations / warnings
            summary   -- human-readable summary string
        """
        intent: dict[str, Any] = ctx.params.get("intent", {})
        params: dict[str, Any] = ctx.params

        logger.info(
            "Persona '%s' executing (execution_id=%s, intent_keys=%s)",
            self.persona_name,
            ctx.execution_id,
            list(intent.keys()),
        )

        try:
            result = await self._produce_artifacts(intent, params)
        except Exception as exc:  # pragma: no cover
            logger.error(
                "Persona '%s' artifact generation failed: %s",
                self.persona_name,
                exc,
                exc_info=True,
            )
            return {
                "persona": self.persona_name,
                "artifacts": [],
                "findings": [f"ERROR: {exc}"],
                "summary": f"Persona {self.persona_name} failed: {exc}",
            }

        artifacts = result.get("artifacts", [])
        findings = result.get("findings", [])

        summary = (
            f"Persona '{self.persona_name}' produced {len(artifacts)} artifact(s) "
            f"with {len(findings)} finding(s)."
        )

        return {
            "persona": self.persona_name,
            "artifacts": artifacts,
            "findings": findings,
            "summary": summary,
        }

    # -- Abstract hook -------------------------------------------------------

    @abc.abstractmethod
    async def _produce_artifacts(
        self,
        intent: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate deployment artifacts from the intent document.

        Must return ``{"artifacts": [...], "findings": [...]}``.
        """
        ...

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def write_artifact(path: str, content: str) -> dict[str, Any]:
        """Return a tracking dict for a generated artifact.

        No actual file I/O is performed -- the caller collects these dicts
        and can persist them later via the platform's file-writing layer.
        """
        return {
            "path": path,
            "content": content,
            "action": "create",
            "size_bytes": len(content.encode()),
        }
