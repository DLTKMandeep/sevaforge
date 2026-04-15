"""Tests for DeployOrchestratorAgent — parallel persona fan-out."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from forgeflow.agents.deploy_orchestrator_agent import (
    DeployOrchestratorAgent,
    PERSONA_LAYERS,
)


def _write_intent(project_path: Path, overrides=None) -> dict:
    """Write a minimal valid deployment-intent.yaml. Returns the intent dict."""
    intent = {
        "version": 1,
        "app": {
            "name": "testapp",
            "language": "python",
            "port": 8000,
            "healthcheck_path": "/health",
        },
        "cloud": {
            "provider": "gcp",
            "project_id": "test-proj",
            "region": "us-central1",
        },
        "compute": {
            "model": "kubernetes",
            "flavour": "gke-autopilot",
            "replicas": 2,
            "autoscale": {"enabled": True, "min": 2, "max": 6},
        },
        "environments": [
            {"name": "dev", "auto_promote": True},
            {"name": "prod", "auto_promote": False},
        ],
        "secrets": [
            {"name": "GH_TOKEN", "description": "GitHub PAT",
             "source": "github-actions", "required_by": ["ci_cd"]},
            {"name": "GCP_SA_KEY", "description": "Deployer SA",
             "source": "github-actions", "required_by": ["infra", "app"]},
            {"name": "GCP_PROJECT_ID", "description": "project id",
             "source": "github-actions", "required_by": ["infra"]},
            {"name": "GCP_REGION", "description": "region",
             "source": "github-actions", "required_by": ["infra"]},
        ],
        "observability": {
            "stack": "prometheus-grafana",
            "metrics": True, "logs": True, "traces": False,
            "slo": {"availability_target": 99.5, "latency_p99_ms": 500},
        },
        "security": {
            "network_policies": True,
            "image_scanning": True,
            "iam_least_privilege": True,
            "sbom": False,
        },
        "cost_controls": {
            "budget_usd_monthly": 50.0,
            "auto_shutdown": {
                "enabled": True,
                "schedule_down": "0 4 * * *",
                "schedule_up": "0 14 * * *",
            },
            "teardown_date": "2099-12-31",
        },
        "ci_cd": {
            "platform": "github-actions",
            "use_argocd": False,
            "require_approval_for": ["prod"],
        },
    }
    if overrides:
        _deep_merge(intent, overrides)

    payload = json.dumps(intent, sort_keys=True).encode()
    intent["_meta"] = {
        "created_at": "2026-04-15T00:00:00Z",
        "created_by": "test",
        "last_validated": None,
        "intent_hash": hashlib.sha256(payload).hexdigest(),
    }

    intent_dir = project_path / ".sevaforge"
    intent_dir.mkdir(parents=True, exist_ok=True)
    (intent_dir / "deployment-intent.yaml").write_text(yaml.safe_dump(intent, sort_keys=False))
    return intent


def _deep_merge(target: dict, source: dict):
    for k, v in source.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v)
        else:
            target[k] = v


@pytest.fixture
def intent_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    (tmp_path / "app.py").write_text(
        "import os\n"
        "DATABASE_URL = os.environ['DATABASE_URL']\n"
        "JWT_SECRET = os.environ['JWT_SECRET']\n"
    )
    _write_intent(tmp_path)
    return tmp_path


class TestOrchestratorHappyPath:
    def test_runs_all_personas_successfully(self, intent_repo):
        orchestrator = DeployOrchestratorAgent()
        result = orchestrator.execute({"path": str(intent_repo), "overwrite": True})

        assert result["status"] in ("success", "warning"), result.get("summary")
        personas = result["data"]["personas"]
        # All 7 personas should have run
        assert len(personas) == 7
        assert "infra-architect" in personas
        assert "cluster-builder" in personas
        assert "app-deployer" in personas
        assert "secrets-manager" in personas
        assert "observability-engineer" in personas
        assert "security-auditor" in personas
        assert "cost-guardian" in personas

    def test_writes_artifacts_to_disk(self, intent_repo):
        orchestrator = DeployOrchestratorAgent()
        orchestrator.execute({"path": str(intent_repo), "overwrite": True})

        # Representative artifacts across all personas
        expected = [
            "forgeflow/infrastructure/gcp/network.tf",
            "forgeflow/infrastructure/gcp/cluster.tf",
            "deploy/helm/testapp/Chart.yaml",
            "deploy/secrets/inventory.yaml",
            "deploy/secrets/bootstrap.sh",
            ".github/workflows/security-scan.yml",
            ".github/workflows/cost-shutdown.yml",
        ]
        missing = [p for p in expected if not (intent_repo / p).exists()]
        assert not missing, f"Missing artifacts: {missing}"

    def test_aggregates_actions(self, intent_repo):
        orchestrator = DeployOrchestratorAgent()
        result = orchestrator.execute({"path": str(intent_repo), "overwrite": True})
        assert result["data"]["total_actions"] >= 10


class TestOrchestratorFiltering:
    def test_only_runs_selected_personas(self, intent_repo):
        orchestrator = DeployOrchestratorAgent()
        result = orchestrator.execute({
            "path": str(intent_repo),
            "overwrite": True,
            "only": ["secrets-manager", "cost-guardian"],
        })
        personas = result["data"]["personas"]
        assert set(personas.keys()) == {"secrets-manager", "cost-guardian"}

    def test_skip_excludes_personas(self, intent_repo):
        orchestrator = DeployOrchestratorAgent()
        result = orchestrator.execute({
            "path": str(intent_repo),
            "overwrite": True,
            "skip": ["observability-engineer", "security-auditor"],
        })
        personas = result["data"]["personas"]
        assert "observability-engineer" not in personas
        assert "security-auditor" not in personas
        # The others still ran
        assert "infra-architect" in personas
        assert "app-deployer" in personas


class TestOrchestratorErrors:
    def test_missing_intent_returns_error(self, tmp_path):
        orchestrator = DeployOrchestratorAgent()
        result = orchestrator.execute({"path": str(tmp_path)})
        assert result["status"] == "error"
        assert "deployment-intent.yaml" in result["summary"]


class TestLayerOrdering:
    def test_infra_runs_before_cluster(self):
        """ClusterBuilder references InfraArchitect outputs; layer 0 must precede layer 1."""
        layer0 = {p.__name__ for p in PERSONA_LAYERS[0]}
        layer1 = {p.__name__ for p in PERSONA_LAYERS[1]}
        assert "InfraArchitectPersona" in layer0
        assert "ClusterBuilderPersona" in layer1

    def test_every_persona_appears_exactly_once(self):
        all_personas = [p for layer in PERSONA_LAYERS for p in layer]
        assert len(all_personas) == len(set(all_personas)) == 7
