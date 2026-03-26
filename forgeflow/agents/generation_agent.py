#!/usr/bin/env python3
"""
Generation Agent - One-shot infrastructure generation facade.
Mapped to: generate command → deployment_mcp

Role: orchestrates IACAgent + CDAgent + CIAgent in a single call so users
can run `forgeflow generate` and get Terraform + K8s/ArgoCD + CI pipelines
without invoking each step manually.

All business logic lives in the delegated agents — this file contains
no templates and no duplication.
"""
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent
from .iac_agent import IACAgent
from .cd_agent import CDAgent
from .ci_agent import CIAgent


class GenerationAgent(BaseAgent):
    """
    Facade that delegates to IACAgent, CDAgent, and CIAgent.

    Params (all passed through to each sub-agent):
        path            : repo path
        cloud           : aws | gcp | azure  (default: aws)
        greenfield      : overwrite existing files  (default: False)
        include_pulumi  : also generate Pulumi  (default: False)
        include_gitlab  : also generate GitLab CI  (default: True)
        include_dependabot : generate Dependabot config  (default: True)
        include_helm    : generate Helm chart  (default: False)
        include_fluxcd  : generate FluxCD manifests  (default: False)
        skip            : list of agents to skip, e.g. ['cd', 'ci']
    """

    def __init__(self):
        super().__init__(
            name="generation_agent",
            description=(
                "One-shot generation: runs IACAgent (Terraform + Docker) + "
                "CDAgent (ArgoCD + K8s) + CIAgent (GitHub Actions + GitLab CI)"
            )
        )
        self._iac = IACAgent()
        self._cd  = CDAgent()
        self._ci  = CIAgent()

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        skip      = [s.lower() for s in params.get('skip', [])]

        self.log(f"Running full generation for {repo_path.absolute()}")
        self.log(f"Skipping: {skip or 'nothing'}")

        all_actions: List[Dict] = []
        all_findings: List[str] = []
        results: Dict[str, Dict] = {}
        errors: List[str] = []

        # ── IACAgent: Terraform + Docker ─────────────────────────────────────
        if 'iac' not in skip:
            self.log("→ IACAgent (Terraform + Docker)...")
            try:
                iac_result = self._iac.execute(params)
                results['iac'] = iac_result
                all_actions.extend(iac_result.get('actions', []))
                all_findings.append(f"[IAC] {iac_result['summary']}")
                if iac_result.get('status') == 'error':
                    errors.append(f"IACAgent: {iac_result['summary']}")
            except Exception as e:
                errors.append(f"IACAgent exception: {e}")
                all_findings.append(f"[IAC] ❌ Exception: {e}")
        else:
            all_findings.append("[IAC] skipped")

        # ── CDAgent: ArgoCD + K8s + Kustomize ────────────────────────────────
        if 'cd' not in skip:
            self.log("→ CDAgent (ArgoCD + K8s manifests)...")
            try:
                cd_result = self._cd.execute(params)
                results['cd'] = cd_result
                all_actions.extend(cd_result.get('actions', []))
                all_findings.append(f"[CD]  {cd_result['summary']}")
                if cd_result.get('status') == 'error':
                    errors.append(f"CDAgent: {cd_result['summary']}")
            except Exception as e:
                errors.append(f"CDAgent exception: {e}")
                all_findings.append(f"[CD]  ❌ Exception: {e}")
        else:
            all_findings.append("[CD] skipped")

        # ── CIAgent: GitHub Actions + GitLab CI + Dependabot ─────────────────
        if 'ci' not in skip:
            self.log("→ CIAgent (GitHub Actions + GitLab CI)...")
            try:
                ci_result = self._ci.execute(params)
                results['ci'] = ci_result
                all_actions.extend(ci_result.get('actions', []))
                all_findings.append(f"[CI]  {ci_result['summary']}")
                if ci_result.get('status') == 'error':
                    errors.append(f"CIAgent: {ci_result['summary']}")
            except Exception as e:
                errors.append(f"CIAgent exception: {e}")
                all_findings.append(f"[CI]  ❌ Exception: {e}")
        else:
            all_findings.append("[CI] skipped")

        # ── Aggregate ─────────────────────────────────────────────────────────
        total_created = len([a for a in all_actions if a.get('action') == 'created'])
        total_exists  = len([a for a in all_actions if a.get('action') == 'exists'])
        agents_run    = [k for k in ('iac', 'cd', 'ci') if k not in skip]

        overall_status = 'error' if errors else 'success'

        summary = (
            f"Generation complete: {total_created} files created, "
            f"{total_exists} already existed "
            f"(ran: {', '.join(agents_run).upper()})"
        )
        if errors:
            summary = f"Generation completed with errors: {'; '.join(errors)}"

        self.log(summary)

        return self.create_result(
            status=overall_status,
            summary=summary,
            data={
                'agents_run': agents_run,
                'agents_skipped': skip,
                'total_files_created': total_created,
                'total_files_existing': total_exists,
                'iac': results.get('iac', {}).get('data', {}),
                'cd':  results.get('cd',  {}).get('data', {}),
                'ci':  results.get('ci',  {}).get('data', {}),
                'errors': errors,
            },
            findings=all_findings,
            actions=all_actions
        )
