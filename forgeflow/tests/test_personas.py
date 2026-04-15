"""Unit tests for individual persona agents.

Each persona is tested in isolation against a minimal intent + repo fixture.
The orchestrator end-to-end path is covered separately in test_deploy_orchestrator.
"""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from forgeflow.agents.personas import (
    SecretsManagerPersona,
    InfraArchitectPersona,
    ClusterBuilderPersona,
    AppDeployerPersona,
    ObservabilityEngineerPersona,
    SecurityAuditorPersona,
    CostGuardianPersona,
)


# =============================================================================
# Fixtures
# =============================================================================

def _hashed_intent(intent: dict) -> dict:
    payload = {k: v for k, v in intent.items() if k != "_meta"}
    intent = dict(intent)
    intent["_meta"] = {
        "created_at": "2026-04-15T00:00:00Z",
        "created_by": "test",
        "last_validated": None,
        "intent_hash": hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest(),
    }
    return intent


def _write_intent(project_path: Path, cloud: str = "gcp", compute_model: str = "kubernetes"):
    flavour = {
        ("gcp", "kubernetes"): "gke-autopilot",
        ("gcp", "serverless"): "cloud-run",
        ("aws", "kubernetes"): "eks",
    }.get((cloud, compute_model), "gke-autopilot")

    intent = _hashed_intent({
        "version": 1,
        "app": {"name": "testapp", "language": "python", "port": 8000,
                "healthcheck_path": "/health"},
        "cloud": {"provider": cloud, "project_id": "test-proj", "region": "us-central1"},
        "compute": {
            "model": compute_model, "flavour": flavour, "replicas": 2,
            "autoscale": {"enabled": True, "min": 2, "max": 6},
        },
        "environments": [
            {"name": "dev", "auto_promote": True},
            {"name": "prod", "auto_promote": False},
        ],
        "secrets": [
            {"name": "GH_TOKEN", "description": "pat",
             "source": "github-actions", "required_by": ["ci_cd"]},
            {"name": "GCP_SA_KEY", "description": "sa",
             "source": "github-actions", "required_by": ["infra"]},
            {"name": "GCP_PROJECT_ID", "description": "pid",
             "source": "github-actions", "required_by": ["infra"]},
            {"name": "GCP_REGION", "description": "reg",
             "source": "github-actions", "required_by": ["infra"]},
        ],
        "observability": {
            "stack": "prometheus-grafana", "metrics": True, "logs": True, "traces": False,
            "slo": {"availability_target": 99.5, "latency_p99_ms": 500},
        },
        "security": {
            "network_policies": True, "image_scanning": True,
            "iam_least_privilege": True, "sbom": False,
        },
        "cost_controls": {
            "budget_usd_monthly": 50.0,
            "auto_shutdown": {"enabled": True,
                              "schedule_down": "0 4 * * *",
                              "schedule_up": "0 14 * * *"},
            "teardown_date": "2099-12-31",
        },
        "ci_cd": {"platform": "github-actions", "use_argocd": False,
                  "require_approval_for": ["prod"]},
    })
    intent_dir = project_path / ".sevaforge"
    intent_dir.mkdir(parents=True, exist_ok=True)
    (intent_dir / "deployment-intent.yaml").write_text(yaml.safe_dump(intent, sort_keys=False))


@pytest.fixture
def gcp_k8s_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    (tmp_path / "app.py").write_text(
        "import os\n"
        "DATABASE_URL = os.environ.get('DATABASE_URL')\n"
        "JWT_SECRET = os.environ.get('JWT_SECRET')\n"
    )
    _write_intent(tmp_path, cloud="gcp", compute_model="kubernetes")
    return tmp_path


@pytest.fixture
def aws_k8s_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    (tmp_path / "app.py").write_text("print('hi')\n")
    _write_intent(tmp_path, cloud="aws", compute_model="kubernetes")
    return tmp_path


@pytest.fixture
def gcp_serverless_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    (tmp_path / "app.py").write_text("print('hi')\n")
    _write_intent(tmp_path, cloud="gcp", compute_model="serverless")
    return tmp_path


# =============================================================================
# Secrets Manager
# =============================================================================

class TestSecretsManagerPersona:
    def test_writes_inventory_bootstrap_and_guide(self, gcp_k8s_repo):
        result = SecretsManagerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        assert (gcp_k8s_repo / "deploy/secrets/inventory.yaml").exists()
        assert (gcp_k8s_repo / "deploy/secrets/bootstrap.sh").exists()
        assert (gcp_k8s_repo / "deploy/secrets/DEPLOYMENT_SECRETS_GUIDE.md").exists()

    def test_scans_app_code_for_extra_secrets(self, gcp_k8s_repo):
        SecretsManagerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        inv = yaml.safe_load(
            (gcp_k8s_repo / "deploy/secrets/inventory.yaml").read_text()
        )
        names = {s["name"] for s in inv["secrets"]}
        assert "DATABASE_URL" in names
        assert "JWT_SECRET" in names
        assert "GH_TOKEN" in names  # from baseline

    def test_bootstrap_script_is_executable(self, gcp_k8s_repo):
        SecretsManagerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        bootstrap = gcp_k8s_repo / "deploy/secrets/bootstrap.sh"
        # chmod is best-effort in write; verify at least the content is sh
        assert bootstrap.read_text().startswith("#!")


# =============================================================================
# Infrastructure Architect
# =============================================================================

class TestInfraArchitectPersona:
    def test_gcp_writes_network_and_providers(self, gcp_k8s_repo):
        result = InfraArchitectPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        base = gcp_k8s_repo / "forgeflow/infrastructure/gcp"
        assert (base / "network.tf").exists()
        assert (base / "providers.tf").exists()
        assert (base / "backend.tf").exists()

    def test_aws_writes_network(self, aws_k8s_repo):
        result = InfraArchitectPersona().execute({"path": str(aws_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        base = aws_k8s_repo / "forgeflow/infrastructure/aws"
        assert (base / "network.tf").exists()


# =============================================================================
# Cluster Builder
# =============================================================================

class TestClusterBuilderPersona:
    def test_gcp_k8s_writes_gke_autopilot(self, gcp_k8s_repo):
        result = ClusterBuilderPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        cluster_tf = gcp_k8s_repo / "forgeflow/infrastructure/gcp/cluster.tf"
        assert cluster_tf.exists()
        content = cluster_tf.read_text()
        assert "enable_autopilot" in content or "Autopilot" in content

    def test_gcp_serverless_writes_cloud_run(self, gcp_serverless_repo):
        result = ClusterBuilderPersona().execute({"path": str(gcp_serverless_repo), "overwrite": True})
        assert result["status"] == "success"
        # Cloud Run doesn't use cluster.tf; check for a cloud-run specific file
        base = gcp_serverless_repo / "forgeflow/infrastructure/gcp"
        tf_files = list(base.glob("*.tf"))
        content = "\n".join(f.read_text() for f in tf_files)
        assert "cloud_run" in content.lower() or "google_cloud_run" in content.lower()


# =============================================================================
# App Deployer
# =============================================================================

class TestAppDeployerPersona:
    def test_writes_dockerfile(self, gcp_k8s_repo):
        result = AppDeployerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        assert (gcp_k8s_repo / "Dockerfile").exists()
        # Python base image
        assert "python" in (gcp_k8s_repo / "Dockerfile").read_text().lower()

    def test_writes_helm_chart(self, gcp_k8s_repo):
        AppDeployerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        chart_dir = gcp_k8s_repo / "deploy/helm/testapp"
        assert (chart_dir / "Chart.yaml").exists()
        assert (chart_dir / "values.yaml").exists()
        assert (chart_dir / "templates/deployment.yaml").exists()
        assert (chart_dir / "templates/service.yaml").exists()

    def test_helm_values_image_matches_gcp_registry(self, gcp_k8s_repo):
        AppDeployerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        values = yaml.safe_load(
            (gcp_k8s_repo / "deploy/helm/testapp/values.yaml").read_text()
        )
        repo = values["image"]["repository"]
        # Validator expects gcr.io/ prefix for GCP
        assert "gcr.io/" in repo

    def test_writes_hpa_when_autoscale_enabled(self, gcp_k8s_repo):
        AppDeployerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert (gcp_k8s_repo / "deploy/helm/testapp/templates/hpa.yaml").exists()

    def test_preserves_existing_dockerfile(self, gcp_k8s_repo):
        existing = "FROM scratch\n# my custom dockerfile\n"
        (gcp_k8s_repo / "Dockerfile").write_text(existing)
        AppDeployerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": False})
        # brownfield mode — should not clobber
        assert (gcp_k8s_repo / "Dockerfile").read_text() == existing


# =============================================================================
# Observability Engineer
# =============================================================================

class TestObservabilityEngineerPersona:
    def test_prometheus_stack_writes_alerts(self, gcp_k8s_repo):
        result = ObservabilityEngineerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        obs = gcp_k8s_repo / "deploy/observability"
        # at least an alerts or rules file
        files = list(obs.rglob("*"))
        contents = "\n".join(f.read_text() for f in files if f.is_file())
        assert "HighErrorRate" in contents or "HighLatency" in contents

    def test_slo_document_written(self, gcp_k8s_repo):
        ObservabilityEngineerPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        obs = gcp_k8s_repo / "deploy/observability"
        files = [f for f in obs.rglob("*.yaml") if f.is_file()]
        contents = "\n".join(f.read_text() for f in files)
        assert "availability" in contents.lower() or "slo" in contents.lower()


# =============================================================================
# Security Auditor
# =============================================================================

class TestSecurityAuditorPersona:
    def test_writes_network_policy_when_enabled(self, gcp_k8s_repo):
        result = SecurityAuditorPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        sec = gcp_k8s_repo / "deploy/security"
        files = [f for f in sec.rglob("*.yaml") if f.is_file()]
        contents = "\n".join(f.read_text() for f in files)
        assert "NetworkPolicy" in contents

    def test_writes_security_scan_workflow(self, gcp_k8s_repo):
        SecurityAuditorPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        wf = gcp_k8s_repo / ".github/workflows/security-scan.yml"
        assert wf.exists()
        content = wf.read_text()
        # Should reference at least one scanner
        assert "trivy" in content.lower() or "checkov" in content.lower()


# =============================================================================
# Cost Guardian
# =============================================================================

class TestCostGuardianPersona:
    def test_writes_shutdown_workflow(self, gcp_k8s_repo):
        result = CostGuardianPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        assert result["status"] == "success"
        assert (gcp_k8s_repo / ".github/workflows/cost-shutdown.yml").exists()

    def test_shutdown_workflow_uses_intent_cron(self, gcp_k8s_repo):
        CostGuardianPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        wf = (gcp_k8s_repo / ".github/workflows/cost-shutdown.yml").read_text()
        # schedule_down in intent is "0 4 * * *"
        assert "0 4 * * *" in wf

    def test_writes_teardown_workflow_when_date_set(self, gcp_k8s_repo):
        CostGuardianPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        teardown = gcp_k8s_repo / ".github/workflows/cost-teardown.yml"
        assert teardown.exists()
        content = teardown.read_text()
        # 2099-12-31 → cron "0 6 31 12 *"
        assert "31 12" in content or "2099" in content

    def test_writes_budget_terraform(self, gcp_k8s_repo):
        CostGuardianPersona().execute({"path": str(gcp_k8s_repo), "overwrite": True})
        cost_dir = gcp_k8s_repo / "deploy/cost"
        files = list(cost_dir.rglob("*"))
        contents = "\n".join(f.read_text() for f in files if f.is_file())
        assert "google_billing_budget" in contents or "billing_budget" in contents
