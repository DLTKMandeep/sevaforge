"""
BasePersona — shared scaffolding for deployment persona agents.

A persona is a BaseAgent subclass that:
  1. Reads the shared deployment-intent.yaml
  2. Produces a defined set of artifacts under well-known paths
  3. Optionally contributes additional secret declarations back to the intent
  4. Runs independently of other personas (no cross-persona coordination at
     runtime — the orchestrator handles ordering & merging)
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from ..base_agent import BaseAgent


class BasePersona(BaseAgent):
    """Common helpers for every persona agent."""

    # Subclasses override these
    persona_name: str = "base"
    owned_paths: List[str] = []  # glob-relative paths the persona writes into

    def __init__(self, name: str, description: str):
        super().__init__(name=name, description=description)
        self._intent: Optional[Dict[str, Any]] = None
        self._project_path: Optional[Path] = None

    # ----------------------------------------------------------------- loading

    def load_intent(self, project_path: Path) -> Dict[str, Any]:
        """Load the deployment intent from the canonical location."""
        intent_file = project_path / ".sevaforge" / "deployment-intent.yaml"
        if not intent_file.exists():
            raise FileNotFoundError(
                f"Deployment intent not found at {intent_file}. "
                f"Run `forgeflow deploy-intent` first."
            )
        self._project_path = project_path
        self._intent = yaml.safe_load(intent_file.read_text())
        return self._intent

    @property
    def intent(self) -> Dict[str, Any]:
        if self._intent is None:
            raise RuntimeError("load_intent() must be called before accessing intent")
        return self._intent

    @property
    def project_path(self) -> Path:
        if self._project_path is None:
            raise RuntimeError("load_intent() must be called before accessing project_path")
        return self._project_path

    # ---------------------------------------------------------------- helpers

    def relpath(self, absolute: Path) -> str:
        """Return a path relative to project root for action logging."""
        try:
            return str(absolute.relative_to(self.project_path))
        except ValueError:
            return str(absolute)

    def write_file(
        self,
        rel_path: str,
        content: str,
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """Write a file under project_path. Returns an action dict."""
        target = self.project_path / rel_path
        return self._safe_write(target, content, overwrite=overwrite)

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Common execute pattern:
          1. load intent
          2. call produce_artifacts() implemented by subclass
          3. return standard result with actions
        """
        project_path = Path(params["path"]).resolve()
        self.load_intent(project_path)

        overwrite = bool(params.get("overwrite", True))
        try:
            actions, findings, extra = self.produce_artifacts(overwrite=overwrite)
        except Exception as e:
            self.log(f"{self.persona_name} failed: {e}", level="error")
            return self.create_result(
                status="error",
                summary=f"{self.persona_name} persona failed: {e}",
            )

        status = "success" if actions else "warning"
        return self.create_result(
            status=status,
            summary=f"{self.persona_name} produced {len(actions)} artifact(s)",
            data={"persona": self.persona_name, **(extra or {})},
            findings=findings,
            actions=actions,
        )

    # ------------------------------------------------------------ subclass API

    def produce_artifacts(
        self,
        overwrite: bool = True,
    ) -> tuple[List[Dict[str, Any]], List[str], Optional[Dict[str, Any]]]:
        """
        Subclasses implement this. Must return (actions, findings, extra_data).
        Should write files under self.project_path and return the action list.
        """
        raise NotImplementedError
