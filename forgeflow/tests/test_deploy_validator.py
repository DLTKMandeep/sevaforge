"""Tests for DeployValidatorAgent — cross-checks persona artifacts."""
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from forgeflow.agents.deploy_orchestrator_agent import DeployOrchestratorAgent
from forgeflow.agents.deploy_validator_agent import DeployValidatorAgent


def _base_intent():
    return {
        "version": 1,
        "app": {"name": "testapp", "language": "python", "port": 8000, "healthcheck_path": "/health"},
        "cloud": {"provider": "gcp", "project_id": "test-proj", "region": "us-central1"},
        "compute": {
            "model": "kubernetes", "flavour": "gke-autopilot", "replicas": 2,
            "autoscale": {"enabled": True, "min": 2, "max": 6},
        },
        "environments": [
            {"name": "dev", "auto_promote": True},
            {"name": "prod", "auto_promote": False},
        ],
        "secrets": [
            {"name": "GH_TOKEN", "description": "pat", "source": "github-actions", "required_by": ["ci_cd"]},
            {"name": "GCP_SA_KEY", "description": "sa", "source": "github-actions", "required_by": ["infra"]},
            {"name": "GCP_PROJECT_ID", "description": "pid", "source": "github-actions", "required_by": ["infra"]},
            {"name": "GCP_REGION", "description": "reg", "source": "github-actions", "required_by": ["infra"]},
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
    }


def _hash_intent(intent: dict) -> str:
    payload = {k: v for k, v in intent.items() if k != "_meta"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _write_intent(project_path: Path, intent: dict):
    intent = dict(intent)
    intent["_meta"] = {
        "created_at": "2026-04-15T00:00:00Z",
        "created_by": "test",
        "last_validated": None,
        "intent_hash": _hash_intent(intent),
    }
    intent_dir = project_path / ".sevaforge"
    intent_dir.mkdir(parents=True, exist_ok=True)
    (intent_dir / "deployment-intent.yaml").write_text(yaml.safe_dump(intent, sort_keys=False))


@pytest.fixture
def full_deployment(tmp_path):
    """Repo with a complete, consistent set of artifacts produced by the orchestrator."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    (tmp_path / "app.py").write_text("print('hi')\n")
    _write_intent(tmp_path, _base_intent())
    DeployOrchestratorAgent().execute({"path": str(tmp_path), "overwrite": True})
    return tmp_path


class TestValidatorHappyPath:
    def test_validates_clean_deployment(self, full_deployment):
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        assert result["status"] == "success", result["summary"]
        assert not result["data"]["failed"]
        assert len(result["data"]["passed"]) == 7

    def test_updates_last_validated_timestamp(self, full_deployment):
        DeployValidatorAgent().execute({"path": str(full_deployment)})
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        assert intent["_meta"]["last_validated"] is not None


class TestValidatorFailures:
    def test_missing_intent(self, tmp_path):
        result = DeployValidatorAgent().execute({"path": str(tmp_path)})
        assert result["status"] == "error"
        assert "missing" in result["summary"]

    def test_detects_stale_inventoried_secret(self, full_deployment):
        """Inventory lists a secret that appears nowhere in the project."""
        inv_file = full_deployment / "deploy" / "secrets" / "inventory.yaml"
        inv = yaml.safe_load(inv_file.read_text()) or {}
        inv["secrets"].append({"name": "PHANTOM_KEY", "source": "manual"})
        inv_file.write_text(yaml.safe_dump(inv, sort_keys=False))
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        assert result["status"] == "error"
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "secrets_referenced_are_inventoried" in failed_checks

    def test_workflow_only_secret_does_not_fail(self, full_deployment):
        """A secret used only in CI (not inventoried) should NOT block push."""
        wf = full_deployment / ".github" / "workflows"
        wf.mkdir(parents=True, exist_ok=True)
        (wf / "ci-only.yml").write_text(
            "jobs:\n  ci:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - run: echo ${{ secrets.CODECOV_TOKEN }}\n"
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        # passed is a list of check-name strings
        assert "secrets_referenced_are_inventoried" in result["data"]["passed"]

    def test_detects_invalid_cron(self, full_deployment):
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["cost_controls"]["auto_shutdown"]["schedule_down"] = "not-a-cron"
        # Rehash so the intent_hash check still passes
        intent["_meta"]["intent_hash"] = _hash_intent(intent)
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "cron_schedules_valid" in failed_checks

    def test_detects_past_teardown_date(self, full_deployment):
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["cost_controls"]["teardown_date"] = "2000-01-01"
        intent["_meta"]["intent_hash"] = _hash_intent(intent)
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "dates_are_future" in failed_checks

    def test_detects_unrealistic_slo(self, full_deployment):
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["observability"]["slo"]["availability_target"] = 150  # > 100
        intent["_meta"]["intent_hash"] = _hash_intent(intent)
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "slo_realistic" in failed_checks

    def test_detects_edited_intent(self, full_deployment):
        """If someone edits the intent after the design stage, hash mismatch blocks push."""
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["cloud"]["region"] = "europe-west1"  # mutate, don't rehash
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "intent_hash_matches" in failed_checks

    def test_detects_undeclared_terraform_var(self, full_deployment):
        """If a .tf file references var.FOO without declaring it, validator flags it."""
        infra = full_deployment / "forgeflow" / "infrastructure" / "gcp"
        rogue_tf = infra / "rogue.tf"
        rogue_tf.write_text(
            'resource "google_compute_address" "x" {\n'
            '  name   = var.mystery_variable\n'
            '  region = var.region\n'
            '}\n'
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "terraform_vars_declared" in failed_checks

    def test_detects_wrong_cloud_registry_prefix(self, full_deployment):
        values_path = full_deployment / "deploy" / "helm" / "testapp" / "values.yaml"
        values = yaml.safe_load(values_path.read_text())
        values["image"]["repository"] = "docker.io/example/testapp"  # wrong for GCP
        values_path.write_text(yaml.safe_dump(values))
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "image_repo_matches_cloud" in failed_checks


class TestValidatorTolerates:
    def test_legacy_intent_without_hash(self, full_deployment):
        """Intents created before the hash feature should still validate."""
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["_meta"].pop("intent_hash", None)
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        # intent_hash_matches should pass (no stored hash)
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "intent_hash_matches" not in failed_checks

    def test_no_teardown_date_is_ok(self, full_deployment):
        intent = yaml.safe_load(
            (full_deployment / ".sevaforge" / "deployment-intent.yaml").read_text()
        )
        intent["cost_controls"]["teardown_date"] = ""
        intent["_meta"]["intent_hash"] = _hash_intent(intent)
        (full_deployment / ".sevaforge" / "deployment-intent.yaml").write_text(
            yaml.safe_dump(intent, sort_keys=False)
        )
        result = DeployValidatorAgent().execute({"path": str(full_deployment)})
        failed_checks = {f["check"] for f in result["data"]["failed"]}
        assert "dates_are_future" not in failed_checks
