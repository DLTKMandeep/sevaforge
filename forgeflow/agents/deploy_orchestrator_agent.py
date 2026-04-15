#!/usr/bin/env python3
"""
ForgeFlow Deploy Orchestrator Agent
====================================
Runs all 7 persona agents in parallel, collects their results, and produces
a unified deploy-design report. Each persona writes to non-overlapping paths
so concurrent execution is safe.

Architecture:
  forgeflow deploy-design <path> → design_mcp → DeployOrchestratorAgent → personas
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

from .base_agent import BaseAgent
from .personas import (
    InfraArchitectPersona,
    ClusterBuilderPersona,
    AppDeployerPersona,
    SecretsManagerPersona,
    ObservabilityEngineerPersona,
    SecurityAuditorPersona,
    CostGuardianPersona,
)


# Execution order matters only for ordering guarantees: InfraArchitect must
# run before ClusterBuilder because ClusterBuilder references local.app from
# the file InfraArchitect writes. We express this as layers — personas within
# a layer run concurrently, layers execute sequentially.
PERSONA_LAYERS = [
    [InfraArchitectPersona, SecretsManagerPersona],   # foundational
    [ClusterBuilderPersona, AppDeployerPersona],      # compute + app
    [ObservabilityEngineerPersona, SecurityAuditorPersona, CostGuardianPersona],  # cross-cutting
]


class DeployOrchestratorAgent(BaseAgent):
    """Fans out to persona agents, collects results into a single report."""

    def __init__(self):
        super().__init__(
            name="deploy_orchestrator_agent",
            description="Runs all persona agents in parallel layers, aggregates results",
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Params:
            path: project root (required) — must contain .sevaforge/deployment-intent.yaml
            overwrite: bool, whether personas overwrite existing files (default True)
            only: list of persona names to run (optional, default = all)
            skip: list of persona names to skip (optional)

        Returns aggregated result with per-persona breakdown.
        """
        project_path = Path(params["path"]).resolve()
        intent_file = project_path / ".sevaforge" / "deployment-intent.yaml"
        if not intent_file.exists():
            return self.create_result(
                status="error",
                summary="deployment-intent.yaml not found — run deploy-intent first",
            )

        overwrite = bool(params.get("overwrite", True))
        only = set(params.get("only") or [])
        skip = set(params.get("skip") or [])

        persona_params = {"path": str(project_path), "overwrite": overwrite}
        layer_results: List[Dict[str, Any]] = []
        all_actions: List[Dict[str, Any]] = []
        all_findings: List[str] = []

        for layer_idx, layer in enumerate(PERSONA_LAYERS):
            filtered = []
            for cls in layer:
                persona = cls()
                if only and persona.persona_name not in only:
                    continue
                if persona.persona_name in skip:
                    continue
                filtered.append(persona)

            if not filtered:
                continue

            self.log(f"Layer {layer_idx + 1}: running {[p.persona_name for p in filtered]} in parallel")

            layer_result = self._run_layer_parallel(filtered, persona_params)
            layer_results.extend(layer_result)

            for r in layer_result:
                all_actions.extend(r.get("actions", []))
                all_findings.extend(r.get("findings", []))

        # Aggregate status
        statuses = {r.get("status") for r in layer_results}
        if "error" in statuses:
            overall = "error"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "success"

        summary = (
            f"Ran {len(layer_results)} personas — "
            f"{sum(1 for r in layer_results if r.get('status') == 'success')} ok, "
            f"{sum(1 for r in layer_results if r.get('status') == 'warning')} warn, "
            f"{sum(1 for r in layer_results if r.get('status') == 'error')} err. "
            f"{len(all_actions)} artefacts written."
        )

        return self.create_result(
            status=overall,
            summary=summary,
            data={
                "personas": {r.get("data", {}).get("persona", r.get("agent")): r
                             for r in layer_results},
                "total_actions": len(all_actions),
            },
            findings=all_findings,
            actions=all_actions,
        )

    # ---------------------------------------------------------------- helpers

    def _run_layer_parallel(
        self,
        personas: List[Any],
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute a single layer of personas concurrently."""
        results = []
        with ThreadPoolExecutor(max_workers=len(personas)) as pool:
            futures = {pool.submit(p.execute, params): p for p in personas}
            for fut in as_completed(futures):
                persona = futures[fut]
                try:
                    result = fut.result()
                    results.append(result)
                except Exception as e:
                    self.log(f"Persona {persona.persona_name} raised: {e}", level="error")
                    results.append(self.create_result(
                        status="error",
                        summary=f"{persona.persona_name} crashed: {e}",
                        data={"persona": persona.persona_name},
                    ))
        return results
