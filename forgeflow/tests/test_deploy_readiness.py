"""Tests for DeployReadinessAgent."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from forgeflow.agents.deploy_readiness_agent import DeployReadinessAgent


@pytest.fixture
def agent():
    return DeployReadinessAgent()


@pytest.fixture
def sample_repo(tmp_path):
    """Create a minimal repo structure for testing."""
    # Python project
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test-app"\n')
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\nEXPOSE 8000\nCMD [\"uvicorn\"]\n")

    # OCI infrastructure
    oci_dir = tmp_path / "forgeflow" / "infrastructure" / "oci"
    oci_dir.mkdir(parents=True)
    (oci_dir / "main.tf").write_text('resource "oci_containerengine_cluster" "x" {}\n')

    # K8s manifests
    k8s_dir = tmp_path / "infrastructure" / "oci-k8s"
    k8s_dir.mkdir(parents=True)
    (k8s_dir / "deployment.yaml").write_text("apiVersion: apps/v1\nkind: Deployment\n")

    # Existing workflow referencing secrets
    wf_dir = tmp_path / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "terraform.yml").write_text(
        "env:\n  TF_VAR_tenancy: ${{ secrets.OCI_TENANCY_OCID }}\n"
        "  KEY: ${{ secrets.OCI_PRIVATE_KEY }}\n"
    )

    return tmp_path


class TestDeployReadinessAgent:
    def test_init(self, agent):
        assert agent.name == "DeployReadinessAgent"

    def test_execute_success(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["status"] == "success"
        assert "actions" in result

    def test_detects_oci_cloud(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["data"]["strategy"]["cloud_provider"] == "oci"

    def test_detects_python_language(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["data"]["strategy"]["primary_language"] == "python"

    def test_detects_dockerfile(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["data"]["strategy"]["has_dockerfile"] is True

    def test_detects_port_from_dockerfile(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["data"]["strategy"]["port"] == 8000

    def test_detects_k8s_manifests(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        assert result["data"]["strategy"]["has_k8s_manifests"] is True

    def test_generates_deployment_guide(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        guide = sample_repo / "docs" / "DEPLOYMENT_GUIDE.md"
        assert guide.exists()
        content = guide.read_text()
        assert "OCI" in content
        assert "OCI_TENANCY_OCID" in content

    def test_generates_bootstrap_script(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        script = sample_repo / "scripts" / "bootstrap-secrets.sh"
        assert script.exists()
        content = script.read_text()
        assert "prompt_secret" in content
        assert "OCI_TENANCY_OCID" in content

    def test_generates_ci_workflow(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        ci = sample_repo / ".github" / "workflows" / "ci-build.yml"
        assert ci.exists()
        content = ci.read_text()
        assert "CI Build" in content
        assert "docker" in content.lower()

    def test_generates_validation_workflow(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        val = sample_repo / ".github" / "workflows" / "validate.yml"
        assert val.exists()
        content = val.read_text()
        assert "Validate" in content
        assert "kubeconform" in content

    def test_generates_cd_workflow(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        cd = sample_repo / ".github" / "workflows" / "cd-deploy.yml"
        assert cd.exists()
        content = cd.read_text()
        assert "CD Deploy" in content
        assert "staging" in content.lower()

    def test_generates_strategy_json(self, agent, sample_repo):
        agent.execute({"path": str(sample_repo), "overwrite": True})
        strat = sample_repo / ".forgeflow" / "deploy-strategy.json"
        assert strat.exists()
        data = json.loads(strat.read_text())
        assert data["cloud_provider"] == "oci"

    def test_brownfield_skips_existing(self, agent, sample_repo):
        """In brownfield mode, existing files should not be overwritten."""
        guide = sample_repo / "docs" / "DEPLOYMENT_GUIDE.md"
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text("EXISTING CONTENT")

        result = agent.execute({"path": str(sample_repo), "overwrite": False})
        assert guide.read_text() == "EXISTING CONTENT"
        exists_actions = [a for a in result["actions"] if a["action"] == "exists"]
        assert len(exists_actions) > 0

    def test_scans_workflow_secrets(self, agent, sample_repo):
        result = agent.execute({"path": str(sample_repo), "overwrite": True})
        # Should have found OCI_TENANCY_OCID and OCI_PRIVATE_KEY from the terraform.yml
        findings = result["findings"]
        assert any("Required secrets:" in f for f in findings)

    def test_nonexistent_path(self, agent):
        result = agent.execute({"path": "/nonexistent/path"})
        assert result["status"] == "error"

    def test_aws_detection(self, agent, tmp_path):
        """Test AWS cloud detection."""
        (tmp_path / "package.json").write_text('{"name": "my-app"}')
        eks_dir = tmp_path / "infrastructure" / "modules" / "cluster"
        eks_dir.mkdir(parents=True)
        (eks_dir / "main.tf").write_text('resource "aws_eks_cluster" "x" {}')

        result = agent.execute({"path": str(tmp_path), "overwrite": True})
        assert result["data"]["strategy"]["cloud_provider"] == "aws"
        assert result["data"]["strategy"]["primary_language"] == "javascript"

    def test_forced_cloud_provider(self, agent, sample_repo):
        result = agent.execute({
            "path": str(sample_repo),
            "overwrite": True,
            "cloud_provider": "gcp",
        })
        assert result["data"]["strategy"]["cloud_provider"] == "gcp"
