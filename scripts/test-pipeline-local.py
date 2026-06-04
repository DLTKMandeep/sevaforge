#!/usr/bin/env python3
"""
Local smoke test for the new pre-push deployment pipeline.

Runs: DeployIntentAgent → DeployOrchestratorAgent → DeployValidatorAgent
against a target repo path. Uses non-interactive mode with sensible
defaults so you can see the full flow without answering prompts.

Usage:
    python3 scripts/test-pipeline-local.py [PATH]

If PATH is omitted, uses a throwaway temp directory seeded with a
minimal Python app so the personas have something to work on.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Make `forgeflow` importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forgeflow.agents import (  # noqa: E402
    DeployIntentAgent,
    DeployOrchestratorAgent,
    DeployValidatorAgent,
)


# ----------------------------------------------------------------------- helpers

def banner(title: str):
    line = "=" * 70
    print(f"\n{line}\n  {title}\n{line}")


def summarize(result: dict):
    status = result.get("status", "?")
    summary = result.get("summary", "")
    icon = {"success": "✅", "warning": "⚠️ ", "error": "❌"}.get(status, "·")
    print(f"{icon} [{status}] {summary}")
    findings = result.get("findings") or []
    for f in findings[:20]:
        print(f"   • {f}")
    if len(findings) > 20:
        print(f"   … and {len(findings) - 20} more")


def seed_sample_repo(target: Path):
    target.mkdir(parents=True, exist_ok=True)
    (target / "pyproject.toml").write_text(
        '[project]\nname = "smoketest"\nversion = "0.1"\n'
    )
    (target / "app.py").write_text(
        "import os\n"
        "PORT = 8000\n"
        "DATABASE_URL = os.environ['DATABASE_URL']\n"
        "JWT_SECRET = os.environ['JWT_SECRET']\n"
        "def main():\n"
        "    print('hi')\n"
        "if __name__ == '__main__':\n    main()\n"
    )
    (target / "requirements.txt").write_text("fastapi>=0.100\nuvicorn>=0.20\n")


# ----------------------------------------------------------------------- driver

def run_pipeline(project_path: Path):
    banner(f"Target: {project_path}")

    # Non-interactive answers — matches the interview prompts
    answers = {
        "cloud_provider": "gcp",
        "cloud_project_id": "divine-data-469116-b2",
        "cloud_region": "us-central1",
        "compute_model": "kubernetes",
        "compute_flavour": "gke-autopilot",
        "compute_replicas": 2,
        "autoscale_enabled": True,
        "autoscale_min": 2,
        "autoscale_max": 6,
        "environments": "dev,prod",
        "auto_promote_dev": True,
        "approval_envs": "prod",
        "healthcheck_path": "/health",
        "observability_stack": "prometheus-grafana",
        "observability_metrics": True,
        "observability_logs": True,
        "observability_traces": False,
        "slo_availability": 99.5,
        "slo_latency_p99": 500,
        "security_netpol": True,
        "security_image_scan": True,
        "security_iam_least_priv": True,
        "security_sbom": False,
        "cost_budget_usd": 50.0,
        "cost_shutdown_enabled": True,
        "cost_schedule_down": "0 4 * * *",
        "cost_schedule_up": "0 14 * * *",
        "cost_teardown_date": "2026-07-08",
        "cicd_platform": "github-actions",
        "cicd_use_argocd": False,
    }

    # Stage 1: intent
    banner("Stage 1/3 — deploy-intent (interview)")
    r1 = DeployIntentAgent().execute({
        "path": str(project_path),
        "answers": answers,
        "interactive": False,
        "force": True,
    })
    summarize(r1)
    if r1["status"] == "error":
        return

    # Stage 2: design (fan-out)
    banner("Stage 2/3 — deploy-design (persona fan-out)")
    r2 = DeployOrchestratorAgent().execute({
        "path": str(project_path),
        "overwrite": True,
    })
    summarize(r2)
    personas = r2.get("data", {}).get("personas", {})
    for name in sorted(personas):
        p = personas[name]
        status = p.get("status", "?")
        icon = {"success": "✅", "warning": "⚠️ ", "error": "❌"}.get(status, "·")
        print(f"   {icon} {name}: {p.get('summary', '')}")

    # Stage 3: validate (push gate)
    banner("Stage 3/3 — deploy-validate (push gate)")
    r3 = DeployValidatorAgent().execute({"path": str(project_path)})
    summarize(r3)
    if r3["status"] == "error":
        print("\n❌ Push would be BLOCKED by validator.")
    else:
        print("\n✅ Push would be ALLOWED — artifacts consistent.")

    banner("Artifacts written")
    for rel in [
        ".sevaforge/deployment-intent.yaml",
        "forgeflow/infrastructure/gcp/network.tf",
        "forgeflow/infrastructure/gcp/cluster.tf",
        "Dockerfile",
        "deploy/helm/smoketest/Chart.yaml",
        "deploy/secrets/inventory.yaml",
        "deploy/secrets/bootstrap.sh",
        ".github/workflows/security-scan.yml",
        ".github/workflows/cost-shutdown.yml",
        ".github/workflows/cost-teardown.yml",
    ]:
        p = project_path / rel
        mark = "✓" if p.exists() else "✗"
        print(f"  {mark} {rel}")


def main():
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).resolve()
        run_pipeline(target)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="forgeflow-smoke-"))
        try:
            seed_sample_repo(tmp)
            run_pipeline(tmp)
            print(f"\n(Sample repo left at {tmp} — rm -rf to clean up)")
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise


if __name__ == "__main__":
    main()
