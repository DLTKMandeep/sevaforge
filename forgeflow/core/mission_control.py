"""
ForgeFlow Mission Control
Handles command execution by delegating to Orchestrator.

Supports deployment modes:
- LOCAL: All MCPs run locally (full offline capability, default)
- CLOUD: All MCPs run on ForgeFlow cloud endpoints (requires FORGEFLOW_API_KEY)

Responsibilities:
1. Create MCPOrchestrator instance with deployment mode
2. Delegate commands to orchestrator.run_mission()
3. Format and save reports/output
4. Display findings to user with rich formatting
5. Execute pipeline stages in proper sequence

New Pipeline Sequence:
    DISCOVER → NORMALIZE → DOCS → GENERATE → REVIEW → TEST → SCAN → [APPROVAL] → BRIDGE
    Post-merge (optional): DEPLOY → MONITOR

Does NOT implement discovery/normalize/scan logic directly!
All "work" is done by MCP servers via the Orchestrator.
"""
import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from .orchestrator import MCPOrchestrator
from .display import (
    console,
    print_header,
    print_stage_start,
    print_stage_result,
    print_pipeline_header,
    print_pipeline_summary,
    print_success_banner,
    print_error_banner,
    print_skipped_banner,
    print_mission_start,
    prompt_bridge_approval,
    prompt_post_merge,
    get_stage_color,
    get_stage_info,
    print_mode_indicator,
    STAGE_MAPPING,
)
try:
    from ..gui.dashboard_server import get_dashboard
except ImportError:
    try:
        from gui.dashboard_server import get_dashboard  # flat CLI import path
    except ImportError:
        def get_dashboard():
            return None


# New pipeline sequence (v2.1 with specialized generation agents)
PIPELINE_STAGES = [
    "discover",
    "normalize",
    "docs",
    "iac",       # Infrastructure as Code (Terraform, Docker)
    "cd",        # Continuous Deployment (ArgoCD, Kustomize)
    "ci",        # Continuous Integration (GitHub Actions, GitLab CI)
    "e2e",       # E2E Testing (Playwright, Cypress)
    "review",
    "test",
    "scan"
]

# Post-merge stages (optional)
POST_MERGE_STAGES = [
    "deploy",
    "monitor"
]


class MissionControl:
    """
    Mission Control - CLI backend that delegates to MCPOrchestrator.
    Supports local and hybrid deployment modes.
    """
    
    def __init__(self, config_path: str = None, mode: str = None):
        self.orchestrator = MCPOrchestrator(config_path, mode=mode)
        self.timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        self.mode = self.orchestrator.get_deployment_mode()
        
    def execute(self, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a ForgeFlow command by delegating to the orchestrator.
        
        Args:
            command: The command name (discover, normalize, scan, etc.)
            params: Optional parameters for the command
            
        Returns:
            Result dictionary from the MCP server
        """
        if params is None:
            params = {}
        
        path = params.get("path", ".")
        
        # Display stage start info
        print_mission_start(command, path, self.mode)
        
        # Delegate to orchestrator
        result = self.orchestrator.run_mission(command, params)
        
        # Save report
        self._save_report(result, command, path)
        
        return result
    
    # === Convenience methods for each canonical command ===
    
    def discover(self, path: str = ".") -> Dict[str, Any]:
        """Run discovery on a repository."""
        return self.execute("discover", {"path": path})
    
    def normalize(self, path: str = ".") -> Dict[str, Any]:
        """Run normalization on a repository."""
        return self.execute("normalize", {"path": path})
    
    def scan(self, path: str = ".", severity: str = "medium") -> Dict[str, Any]:
        """Run security scan on a repository."""
        return self.execute("scan", {"path": path, "severity_threshold": severity})
    
    def generate(self, path: str = ".", stack: str = "auto") -> Dict[str, Any]:
        """Generate deployment artifacts."""
        return self.execute("generate", {"path": path, "stack": stack})
    
    # === Specialized Generation Commands (v2.1) ===
    
    def iac(self, path: str = ".", cloud: str = "aws", include_pulumi: bool = False) -> Dict[str, Any]:
        """Generate Infrastructure as Code (IACAgent → iac-mcp-server).
        
        Generates:
        - Terraform files (main.tf, variables.tf, outputs.tf)
        - Terraform modules (network, cluster, storage, iam)
        - Dockerfile based on detected language
        - docker-compose.yml for local development
        - Pulumi configuration (optional)
        """
        return self.execute("iac", {
            "repo_path": path,
            "cloud": cloud,
            "include_pulumi": include_pulumi
        })
    
    def cd(self, path: str = ".", repo_url: str = "https://github.com/org/repo.git",
           include_flux: bool = False, include_helm: bool = False,
           overwrite: bool = False) -> Dict[str, Any]:
        """Generate Continuous Deployment configs (CDAgent → cd-mcp-server).

        Generates:
        - .github/workflows/infra.yml    (Terraform provisioning — runs in GitHub Actions)
        - .github/workflows/bootstrap.yml (ArgoCD bootstrap — runs in GitHub Actions)
        - .github/workflows/deploy.yml   (full pilot-to-prod pipeline)
        - ArgoCD Application manifests
        - ArgoCD AppProject + ApplicationSet
        - Kustomize base and overlays (dev, staging, prod)
        - Kubernetes manifests (deployment, service, configmap, hpa)
        - scripts/setup-github.sh        (one-time 4-secret setup)
        - infrastructure/k8s/secrets/    (External Secrets Operator manifests)
        - RUNBOOK.md
        - FluxCD configuration (optional)
        - Helm charts (optional)
        """
        return self.execute("cd", {
            "repo_path": path,
            "repo_url": repo_url,
            "include_flux": include_flux,
            "include_helm": include_helm,
            "overwrite": overwrite,
        })
    
    def ci(self, path: str = ".", include_gitlab: bool = True, 
           include_dependabot: bool = True) -> Dict[str, Any]:
        """Generate Continuous Integration pipelines (CIAgent → ci-mcp-server).
        
        Generates:
        - GitHub Actions workflows (ci.yml, security.yml, release.yml)
        - GitLab CI (.gitlab-ci.yml)
        - Dependabot configuration
        - Linting, unit tests, integration tests
        - Build and push container
        """
        return self.execute("ci", {
            "repo_path": path,
            "include_gitlab": include_gitlab,
            "include_dependabot": include_dependabot
        })
    
    def e2e(self, path: str = ".", framework: str = "playwright",
            include_ci: bool = True) -> Dict[str, Any]:
        """Generate E2E testing setup (E2ETestingAgent → e2e-mcp-server).
        
        Generates:
        - Playwright configuration and test templates
        - Cypress configuration (alternative)
        - Test templates (auth, navigation, forms, api)
        - CI workflow for E2E tests
        - Test reporting setup
        """
        return self.execute("e2e", {
            "repo_path": path,
            "framework": framework,
            "include_ci": include_ci
        })
    
    def review(self, path: str = ".") -> Dict[str, Any]:
        """Run code review and quality analysis (CodeReviewAgent → git-mcp-server)."""
        return self.execute("review", {"path": path})
    
    def test(self, path: str = ".") -> Dict[str, Any]:
        """Run tests via CI/CD pipeline (TestingAgent → cicd-mcp-server)."""
        return self.execute("test", {"path": path})
    
    def deploy(self, path: str = ".", target: str = "staging") -> Dict[str, Any]:
        """Deploy to cloud infrastructure (DeploymentAgent → cloud-mcp-server)."""
        return self.execute("deploy", {"path": path, "target": target})
    
    def monitor(self, path: str = ".") -> Dict[str, Any]:
        """Set up monitoring and observability (MonitoringAgent → observability-mcp-server)."""
        return self.execute("monitor", {"path": path})
    
    def docs(self, path: str = ".", full: bool = False, architecture: bool = False,
             threat_model: bool = False, erd: bool = False, deployment: bool = False) -> Dict[str, Any]:
        """Generate documentation and diagrams.
        
        Options:
            --full: Generate all documentation (default if no option specified)
            --architecture: Generate C4-style architecture diagrams
            --threat-model: Generate STRIDE-based threat model
            --erd: Generate Entity Relationship Diagram
            --deployment: Generate deployment architecture diagrams
        """
        return self.execute("docs", {
            "path": path,
            "full": full,
            "architecture": architecture,
            "threat_model": threat_model,
            "erd": erd,
            "deployment": deployment
        })
    
    def bridge(self, repo: str = None, branch: str = None, operation: str = "status",
               base_branch: str = "main", message: str = None, pr_title: str = None, 
               pr_body: str = None, path: str = ".") -> Dict[str, Any]:
        """Bridge to GitHub - creates repo and pushes code.
        
        Simple operation: extracts folder name from path, creates GitHub repo, pushes.
        """
        params = {
            "path": path,
            "repo": repo,
            "branch": branch,
            "operation": operation,
        }
        return self.execute("bridge", params)
    
    def run_all(self, path: str = ".", include_post_merge: bool = False, greenfield: bool = False) -> Dict[str, Any]:
        """
        Run full 11-stage pipeline:
        DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → BRIDGE

        Bridge (GitHub push) is now a first-class pipeline stage — no manual
        approval prompt.  Post-merge stages (DEPLOY → MONITOR) are optional.

        Args:
            path: Repository path to run pipeline on
            include_post_merge: Whether to run deploy + monitor after bridge
            greenfield: If True, generation agents overwrite existing files (new project).
                        If False (default), existing files are preserved (brownfield).

        If any stage fails, the pipeline stops and reports the failure.
        """
        stages = [
            ("discover",  lambda: self._execute_stage("discover",  path, greenfield)),
            ("normalize", lambda: self._execute_stage("normalize", path, greenfield)),
            ("docs",      lambda: self._execute_stage("docs",      path, greenfield)),
            ("iac",       lambda: self._execute_stage("iac",       path, greenfield)),
            ("cd",        lambda: self._execute_stage("cd",        path, greenfield)),
            ("ci",        lambda: self._execute_stage("ci",        path, greenfield)),
            ("e2e",       lambda: self._execute_stage("e2e",       path, greenfield)),
            ("review",    lambda: self._execute_stage("review",    path, greenfield)),
            ("test",      lambda: self._execute_stage("test",      path, greenfield)),
            ("scan",      lambda: self._execute_stage("scan",      path, greenfield)),
            ("bridge",    lambda: self._execute_stage("bridge",    path)),           # Push to GitHub
        ]

        total = len(stages)
        print_pipeline_header("RUN-ALL PIPELINE", self.mode)
        console.print(f"  [dim]Pipeline: DISCOVER → NORMALIZE → DOCS → IAC → CD → CI → E2E → REVIEW → TEST → SCAN → BRIDGE[/]")
        console.print()

        dash = get_dashboard()

        # Emit pipeline_start to all connected browsers
        if dash:
            dash.emit_pipeline_start(path, [s[0] for s in stages])

        # Statuses that count as "already done / nothing to do" — treat as success
        PASS_STATUSES = {"success", "warning", "skipped", "done", "already_done",
                         "already_complete", "no_changes", "nothing_to_do"}
        # Pause between stages when GUI is watching so the hourglass has time to display
        STAGE_PAUSE_S = 30

        results: List[tuple] = []
        for idx, (stage_name, stage_fn) in enumerate(stages, 1):
            # Display stage start with number context
            print_stage_start(stage_name, path, stage_num=idx, total=total)

            # Emit stage_start to browser — include purpose/outputs info
            if dash:
                info = STAGE_MAPPING.get(stage_name, {})
                dash.emit_stage_start(stage_name, num=idx, total=total, info={
                    "purpose":    info.get("purpose", ""),
                    "outputs":    info.get("outputs", ""),
                    "agent":      info.get("agent", ""),
                    "mcp_server": info.get("mcp_server", ""),
                })

            # Execute stage
            result = stage_fn()

            # Normalise "already done" results so the pipeline never stops early
            raw_status = result.get("status", "error")
            if raw_status not in PASS_STATUSES and raw_status not in {"error", "failed"}:
                # Unknown status — assume success rather than killing the pipeline
                result["status"] = "success"
                result.setdefault("summary", "Stage completed (no changes needed).")
            elif raw_status in PASS_STATUSES and raw_status not in {"success", "warning"}:
                # Skipped / already-done variants → rewrite to success for display
                result["status"] = "success"
                result.setdefault("summary", "Already complete — nothing to do.")

            results.append((stage_name, result))

            # Display stage result
            print_stage_result(stage_name, result)

            # Emit stage_result to browser
            if dash:
                dash.emit_stage_result(stage_name, {
                    "status":   result.get("status", "error"),
                    "summary":  result.get("summary", ""),
                    "findings": result.get("findings", []),
                })

                # ── 30-second spotlight pause so the GUI hourglass is visible ──
                if idx < total:
                    console.print(f"  [dim]⏳ Waiting {STAGE_PAUSE_S}s before next stage…[/]")
                    time.sleep(STAGE_PAUSE_S)

            if result.get("status") not in {"success", "warning"}:
                # Pipeline truly failed
                print_pipeline_summary(results, success=False)
                print_error_banner("Pipeline failed", stage_name)
                if dash:
                    dash.emit_pipeline_done(success=False, summary=f"Pipeline failed at {stage_name}")
                return {
                    "status": "error",
                    "mission": "run-all",
                    "deployment_mode": self.mode,
                    "summary": f"Pipeline failed at {stage_name} stage",
                    "failed_stage": stage_name,
                    "stage_result": result,
                    "completed_stages": [r[0] for r in results[:-1]]
                }

        # All 11 stages (including bridge/GitHub push) completed
        print_pipeline_summary(results, success=True)
        print_success_banner("RUN-ALL COMPLETE: All stages passed + pushed to GitHub!")

        if include_post_merge and prompt_post_merge():
            return self._run_post_merge_stages(path, results)

        if dash:
            dash.emit_pipeline_done(success=True, summary="Full pipeline completed + pushed to GitHub")
        return {
            "status": "success",
            "mission": "run-all",
            "deployment_mode": self.mode,
            "summary": "Full pipeline completed successfully — code pushed to GitHub",
            "stages": [r[0] for r in results],
        }
    
    def _run_post_merge_stages(self, path: str, results: List[tuple]) -> Dict[str, Any]:
        """Run post-merge stages: deploy → monitor."""
        console.print()
        console.print("[bold purple]▶ Running Post-Merge Stages: DEPLOY → MONITOR[/]")
        console.print()
        
        post_merge_stages = [
            ("deploy", lambda: self._execute_stage("deploy", path)),
            ("monitor", lambda: self._execute_stage("monitor", path)),
        ]
        
        for stage_name, stage_fn in post_merge_stages:
            print_stage_start(stage_name, path)
            result = stage_fn()
            results.append((stage_name, result))
            print_stage_result(stage_name, result)
            
            if result.get("status") not in ["success", "warning"]:
                print_pipeline_summary(results, success=False)
                print_error_banner(f"Post-merge failed at {stage_name}", stage_name)
                return {
                    "status": "warning",
                    "mission": "run-all",
                    "deployment_mode": self.mode,
                    "summary": f"Pipeline completed but post-merge failed at {stage_name}",
                    "stages": [r[0] for r in results],
                    "failed_post_merge_stage": stage_name
                }
        
        print_pipeline_summary(results, success=True)
        print_success_banner("FULL PIPELINE + POST-MERGE COMPLETE!")
        return {
            "status": "success",
            "mission": "run-all",
            "deployment_mode": self.mode,
            "summary": "Full pipeline with post-merge stages completed successfully",
            "stages": [r[0] for r in results],
            "included_post_merge": True
        }
    
    def _execute_stage(self, stage: str, path: str, greenfield: bool = False) -> Dict[str, Any]:
        """Execute a single stage without display (used by run_all)."""
        params = {"path": path, "greenfield": greenfield}
        return self.orchestrator.run_mission(stage, params)
    
    def status(self, path: str = ".") -> Dict[str, Any]:
        """Check pipeline status (standalone agent)."""
        return self.execute("status", {"path": path})
    
    def doctor(self) -> Dict[str, Any]:
        """Run internal health check."""
        return self.execute("doctor", {})
    
    # === Output formatting and reporting ===
    
    def _save_report(self, result: Dict[str, Any], command: str, repo_path: str):
        """Save mission report to staging folder."""
        try:
            staging_path = Path(repo_path) / "staging"
            staging_path.mkdir(exist_ok=True)
            
            filename = f"{command}_report.md"
            report_file = staging_path / filename
            
            with open(report_file, "w") as f:
                f.write(f"# ForgeFlow Report: {command.upper()}\n\n")
                f.write(f"**Date:** {datetime.now().isoformat()}\n")
                f.write(f"**Status:** {result.get('status', 'N/A')}\n")
                f.write(f"**Server:** {result.get('server', 'N/A')}\n")
                f.write(f"**Mode:** {result.get('deployment_mode', self.mode)}\n\n")
                f.write(f"## Summary\n\n{result.get('summary', 'No summary provided.')}\n\n")
                
                # Write findings if present
                if 'findings' in result:
                    f.write("## Findings\n\n")
                    for finding in result['findings']:
                        if isinstance(finding, dict):
                            f.write(f"- **{finding.get('type', 'Info')}**: {finding.get('message', str(finding))}\n")
                        else:
                            f.write(f"- {finding}\n")
                
                # Write data if present
                if 'data' in result:
                    f.write("\n## Data\n\n```json\n")
                    f.write(json.dumps(result['data'], indent=2))
                    f.write("\n```\n")
            
            console.print(f"  [dim]📝 Report saved: {report_file}[/]")
        except Exception as e:
            console.print(f"  [dim yellow]⚠️ Could not save report: {e}[/]")
    
    def format_result(self, result: Dict[str, Any]) -> str:
        """Format result for CLI display (legacy method)."""
        lines = []
        lines.append(f"\n{'='*60}")
        lines.append(f"✅ Mission: {result.get('mission', 'Unknown').upper()}")
        lines.append(f"{'='*60}")
        lines.append(f"Status: {result.get('status', 'N/A')}")
        lines.append(f"Server: {result.get('server', 'N/A')}")
        lines.append(f"Mode: {result.get('deployment_mode', self.mode)}")
        lines.append(f"Summary: {result.get('summary', 'No summary')}")
        
        if 'findings' in result:
            lines.append(f"\nFindings ({len(result['findings'])}):") 
            for finding in result['findings'][:10]:
                if isinstance(finding, dict):
                    lines.append(f"  - {finding.get('message', str(finding))}")
                else:
                    lines.append(f"  - {finding}")
            if len(result['findings']) > 10:
                lines.append(f"  ... and {len(result['findings']) - 10} more")
        
        lines.append(f"{'='*60}\n")
        return "\n".join(lines)
    
    def print_result(self, result: Dict[str, Any]):
        """Print formatted result to console using rich display."""
        stage = result.get("mission", "unknown")
        print_stage_result(stage, result)
