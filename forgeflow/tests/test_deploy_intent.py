"""Tests for DeployIntentAgent — interview, caching, intent assembly."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from forgeflow.agents.deploy_intent_agent import DeployIntentAgent


@pytest.fixture
def python_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\nversion = "0.1"\n')
    (tmp_path / "app.py").write_text("PORT = 9001\nprint('hi')\n")
    return tmp_path


@pytest.fixture
def node_repo(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "nodeapp", "version": "1.0"}))
    (tmp_path / "server.js").write_text("app.listen(4000)\n")
    return tmp_path


@pytest.fixture
def minimal_answers():
    """A complete answer set that skips every prompt."""
    return {
        "cloud_provider": "gcp",
        "cloud_project_id": "test-project-123",
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
        "cost_teardown_date": "2099-12-31",
        "cicd_platform": "github-actions",
        "cicd_use_argocd": False,
    }


class TestDerivation:
    def test_detects_python_from_pyproject(self, python_repo):
        agent = DeployIntentAgent()
        derived = agent._derive_app_facts(python_repo)
        assert derived["app_name"] == "testapp"
        assert derived["language"] == "python"
        assert derived["port"] == 9001

    def test_detects_node_from_package_json(self, node_repo):
        agent = DeployIntentAgent()
        derived = agent._derive_app_facts(node_repo)
        assert derived["app_name"] == "nodeapp"
        assert derived["language"] == "node"
        assert derived["port"] == 4000

    def test_sanitizes_app_name(self):
        assert DeployIntentAgent._sanitize_name("My App!") == "my-app"
        assert DeployIntentAgent._sanitize_name("foo_bar.baz") == "foo-bar-baz"
        assert DeployIntentAgent._sanitize_name("") == "app"

    def test_falls_back_to_dir_name(self, tmp_path):
        agent = DeployIntentAgent()
        derived = agent._derive_app_facts(tmp_path)
        assert derived["language"] == "other"
        assert derived["port"] == 8080


class TestAssembly:
    def test_assembles_gcp_intent(self, python_repo, minimal_answers):
        agent = DeployIntentAgent()
        result = agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })
        assert result["status"] == "success"
        intent = result["data"]["intent"]
        assert intent["app"]["name"] == "testapp"
        assert intent["cloud"]["provider"] == "gcp"
        assert intent["cloud"]["project_id"] == "test-project-123"
        assert intent["compute"]["flavour"] == "gke-autopilot"
        # GCP baseline secrets must be present
        names = {s["name"] for s in intent["secrets"]}
        assert {"GCP_SA_KEY", "GCP_PROJECT_ID", "GCP_REGION", "GH_TOKEN"} <= names

    def test_aws_baseline_secrets(self, python_repo, minimal_answers):
        minimal_answers["cloud_provider"] = "aws"
        minimal_answers["cloud_region"] = "us-east-1"
        minimal_answers["compute_flavour"] = "eks"
        agent = DeployIntentAgent()
        result = agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })
        names = {s["name"] for s in result["data"]["intent"]["secrets"]}
        assert {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"} <= names

    def test_environments_auto_promote_respects_approval(self, python_repo, minimal_answers):
        minimal_answers["environments"] = "dev,staging,prod"
        minimal_answers["approval_envs"] = "prod"
        agent = DeployIntentAgent()
        intent = agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })["data"]["intent"]

        env_map = {e["name"]: e["auto_promote"] for e in intent["environments"]}
        assert env_map["dev"] is True
        assert env_map["staging"] is True
        assert env_map["prod"] is False

    def test_intent_hash_is_deterministic_and_covers_payload(
        self, python_repo, minimal_answers
    ):
        agent = DeployIntentAgent()
        result = agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })
        intent = result["data"]["intent"]
        stored = intent["_meta"]["intent_hash"]

        # Recompute the hash the way the validator does
        meta = intent.pop("_meta")
        computed = hashlib.sha256(
            json.dumps(intent, sort_keys=True).encode()
        ).hexdigest()
        intent["_meta"] = meta
        assert stored == computed


class TestCaching:
    def test_second_run_returns_cached(self, python_repo, minimal_answers):
        agent = DeployIntentAgent()
        first = agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })
        assert first["data"]["cached"] is False

        second = agent.execute({
            "path": str(python_repo),
            "answers": {"cloud_provider": "aws"},  # should be ignored
            "interactive": False,
        })
        assert second["data"]["cached"] is True
        assert second["data"]["intent"]["cloud"]["provider"] == "gcp"

    def test_force_regenerates(self, python_repo, minimal_answers):
        agent = DeployIntentAgent()
        agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })

        new_answers = dict(minimal_answers)
        new_answers["cloud_provider"] = "aws"
        new_answers["cloud_region"] = "us-east-1"
        new_answers["compute_flavour"] = "eks"

        again = agent.execute({
            "path": str(python_repo),
            "answers": new_answers,
            "interactive": False,
            "force": True,
        })
        assert again["data"]["cached"] is False
        assert again["data"]["intent"]["cloud"]["provider"] == "aws"

    def test_writes_intent_file_on_disk(self, python_repo, minimal_answers):
        agent = DeployIntentAgent()
        agent.execute({
            "path": str(python_repo),
            "answers": minimal_answers,
            "interactive": False,
        })
        intent_file = python_repo / ".sevaforge" / "deployment-intent.yaml"
        assert intent_file.exists()
        on_disk = yaml.safe_load(intent_file.read_text())
        assert on_disk["app"]["name"] == "testapp"
