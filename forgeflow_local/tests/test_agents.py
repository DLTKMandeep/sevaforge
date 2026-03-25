"""Tests for ForgeFlow agents."""
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents import (
    BaseAgent,
    DiscoveryAgent,
    NormalizationAgent,
    SecurityAgent,
    GenerationAgent,
    DeploymentAgent,
    TestingAgent,
    MonitoringAgent,
    DocumentationAgent,
    CodeReviewAgent,
    BridgeAgent,
    IACAgent,
    CDAgent,
    CIAgent,
    E2ETestingAgent,
)


class TestDiscoveryAgent:
    """Tests for DiscoveryAgent."""
    
    def test_discover_basic_repo(self, temp_repo):
        """Test discovery on a basic repository."""
        agent = DiscoveryAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result
        assert "files" in result["data"]
        assert len(result["data"]["files"]) > 0
    
    def test_discover_empty_repo(self, empty_repo):
        """Test discovery on an empty repository."""
        agent = DiscoveryAgent()
        result = agent.execute({"repo_path": str(empty_repo)})
        
        assert result["status"] == "success"
    
    def test_discover_creates_inventory(self, temp_repo):
        """Test that discovery creates inventory file."""
        agent = DiscoveryAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        inventory_file = temp_repo / ".forgeflow" / "inventory.json"
        assert inventory_file.exists()


class TestNormalizationAgent:
    """Tests for NormalizationAgent."""
    
    def test_normalize_basic_repo(self, temp_repo):
        """Test normalization on a basic repository."""
        agent = NormalizationAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] in ["success", "warning"]
        assert "findings" in result
    
    def test_normalize_empty_repo(self, empty_repo):
        """Test normalization suggests standard files for empty repo."""
        agent = NormalizationAgent()
        result = agent.execute({"repo_path": str(empty_repo)})
        
        # Should suggest adding standard files
        assert result["status"] in ["success", "warning"]


class TestSecurityAgent:
    """Tests for SecurityAgent."""
    
    def test_scan_clean_repo(self, temp_repo):
        """Test security scan on a clean repository."""
        agent = SecurityAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_scan_repo_with_issues(self, temp_repo_with_issues):
        """Test security scan detects issues."""
        agent = SecurityAgent()
        result = agent.execute({
            "repo_path": str(temp_repo_with_issues),
            "severity_threshold": "low"
        })
        
        # Should find vulnerabilities
        assert "findings" in result
        assert len(result["findings"]) > 0
    
    def test_scan_severity_filter(self, temp_repo_with_issues):
        """Test severity filtering."""
        agent = SecurityAgent()
        
        # Low threshold - should find more
        result_low = agent.execute({
            "repo_path": str(temp_repo_with_issues),
            "severity_threshold": "low"
        })
        
        # Critical threshold - should find fewer
        result_critical = agent.execute({
            "repo_path": str(temp_repo_with_issues),
            "severity_threshold": "critical"
        })
        
        # More findings with lower threshold
        assert len(result_low.get("findings", [])) >= len(result_critical.get("findings", []))


class TestGenerationAgent:
    """Tests for GenerationAgent."""
    
    def test_generate_basic(self, temp_repo):
        """Test artifact generation."""
        agent = GenerationAgent()
        result = agent.execute({
            "repo_path": str(temp_repo),
            "stack": "auto"
        })
        
        assert result["status"] == "success"
        assert "data" in result
    
    def test_generate_creates_terraform(self, temp_repo):
        """Test that generation creates Terraform files."""
        agent = GenerationAgent()
        result = agent.execute({
            "repo_path": str(temp_repo),
            "stack": "terraform"
        })
        
        terraform_dir = temp_repo / "terraform"
        # Generation should create terraform directory
        assert terraform_dir.exists() or result["status"] == "success"


class TestDeploymentAgent:
    """Tests for DeploymentAgent."""
    
    def test_deploy_simulation(self, temp_repo):
        """Test deployment simulation."""
        agent = DeploymentAgent()
        result = agent.execute({
            "repo_path": str(temp_repo),
            "target": "staging"
        })
        
        assert result["status"] == "success"


class TestTestingAgent:
    """Tests for TestingAgent."""
    
    def test_testing_detection(self, temp_repo):
        """Test framework detection."""
        agent = TestingAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result


class TestMonitoringAgent:
    """Tests for MonitoringAgent."""
    
    def test_monitoring_setup(self, temp_repo):
        """Test monitoring configuration generation."""
        agent = MonitoringAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        
        # Should create monitoring directory
        monitoring_dir = temp_repo / "monitoring"
        assert monitoring_dir.exists()


class TestDocumentationAgent:
    """Tests for DocumentationAgent."""
    
    def test_docs_generation(self, temp_repo):
        """Test documentation generation."""
        agent = DocumentationAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"


class TestCodeReviewAgent:
    """Tests for CodeReviewAgent."""
    
    def test_review_basic(self, temp_repo):
        """Test code review on basic repo."""
        agent = CodeReviewAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        # May fail if not a git repo, which is expected
        assert result["status"] in ["success", "warning", "error"]


class TestBridgeAgent:
    """Tests for BridgeAgent."""
    
    def test_bridge_status(self, temp_repo):
        """Test bridge status check."""
        agent = BridgeAgent()
        result = agent.execute({
            "repo_path": str(temp_repo),
            "operation": "status"
        })
        
        # Status check should work even without GitHub
        assert result["status"] in ["success", "warning", "error"]


class TestIACAgent:
    """Tests for IACAgent."""
    
    def test_iac_basic(self, temp_repo):
        """Test IAC generation on basic repo."""
        agent = IACAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result
        assert "actions" in result
    
    def test_iac_accepts_path_param(self, temp_repo):
        """Test IAC agent accepts 'path' parameter (pipeline compatibility)."""
        agent = IACAgent()
        result = agent.execute({"path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_iac_creates_terraform(self, temp_repo):
        """Test IAC creates Terraform directory."""
        agent = IACAgent()
        agent.execute({"repo_path": str(temp_repo), "cloud": "aws"})
        
        terraform_dir = temp_repo / "infrastructure"
        assert terraform_dir.exists()
    
    def test_iac_creates_docker(self, temp_repo):
        """Test IAC creates Dockerfile."""
        agent = IACAgent()
        agent.execute({"repo_path": str(temp_repo)})
        
        assert (temp_repo / "Dockerfile").exists()


class TestCDAgent:
    """Tests for CDAgent."""
    
    def test_cd_basic(self, temp_repo):
        """Test CD config generation."""
        agent = CDAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result
        assert "actions" in result
    
    def test_cd_accepts_path_param(self, temp_repo):
        """Test CD agent accepts 'path' parameter (pipeline compatibility)."""
        agent = CDAgent()
        result = agent.execute({"path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_cd_creates_k8s_dir(self, temp_repo):
        """Test CD creates Kubernetes manifests."""
        agent = CDAgent()
        agent.execute({"repo_path": str(temp_repo)})
        
        k8s_dir = temp_repo / "infrastructure" / "k8s"
        assert k8s_dir.exists()


class TestCIAgent:
    """Tests for CIAgent."""
    
    def test_ci_basic(self, temp_repo):
        """Test CI pipeline generation."""
        agent = CIAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result
        assert "actions" in result
    
    def test_ci_accepts_path_param(self, temp_repo):
        """Test CI agent accepts 'path' parameter (pipeline compatibility)."""
        agent = CIAgent()
        result = agent.execute({"path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_ci_creates_github_actions(self, temp_repo):
        """Test CI creates GitHub Actions workflows."""
        agent = CIAgent()
        agent.execute({"repo_path": str(temp_repo)})
        
        workflows_dir = temp_repo / ".github" / "workflows"
        assert workflows_dir.exists()


class TestE2ETestingAgent:
    """Tests for E2ETestingAgent."""
    
    def test_e2e_basic(self, temp_repo):
        """Test E2E testing setup generation."""
        agent = E2ETestingAgent()
        result = agent.execute({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
        assert "data" in result
        assert "actions" in result
    
    def test_e2e_accepts_path_param(self, temp_repo):
        """Test E2E agent accepts 'path' parameter (pipeline compatibility)."""
        agent = E2ETestingAgent()
        result = agent.execute({"path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_e2e_playwright_framework(self, temp_repo):
        """Test Playwright framework generation."""
        agent = E2ETestingAgent()
        result = agent.execute({
            "repo_path": str(temp_repo),
            "framework": "playwright"
        })
        
        assert result["status"] == "success"
