"""Tests for MCP servers."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMCPServers:
    """Tests for MCP server modules."""
    
    def test_discovery_mcp_import(self):
        """Test discovery MCP server can be imported."""
        from mcp_servers.discovery_mcp import server
        assert hasattr(server, 'run')
    
    def test_normalize_mcp_import(self):
        """Test normalize MCP server can be imported."""
        from mcp_servers.normalize_mcp import server
        assert hasattr(server, 'run')
    
    def test_security_mcp_import(self):
        """Test security MCP server can be imported."""
        from mcp_servers.security_mcp import server
        assert hasattr(server, 'run')
    
    def test_deployment_mcp_import(self):
        """Test deployment MCP server can be imported."""
        from mcp_servers.deployment_mcp import server
        assert hasattr(server, 'run')
    
    def test_cloud_mcp_import(self):
        """Test cloud MCP server can be imported."""
        from mcp_servers.cloud_mcp import server
        assert hasattr(server, 'run')
    
    def test_cicd_mcp_import(self):
        """Test cicd MCP server can be imported."""
        from mcp_servers.cicd_mcp import server
        assert hasattr(server, 'run')
    
    def test_observability_mcp_import(self):
        """Test observability MCP server can be imported."""
        from mcp_servers.observability_mcp import server
        assert hasattr(server, 'run')
    
    def test_diagram_generator_mcp_import(self):
        """Test diagram generator MCP server can be imported."""
        from mcp_servers.diagram_generator_mcp import server
        assert hasattr(server, 'run')
    
    def test_git_mcp_import(self):
        """Test git MCP server can be imported."""
        from mcp_servers.git_mcp import server
        assert hasattr(server, 'run')
    
    def test_github_mcp_import(self):
        """Test github MCP server can be imported."""
        from mcp_servers.github_mcp import server
        assert hasattr(server, 'run')
    
    def test_discovery_mcp_run(self, temp_repo):
        """Test discovery MCP server run function."""
        from mcp_servers.discovery_mcp import server
        result = server.run({"repo_path": str(temp_repo)})
        
        assert result["status"] == "success"
    
    def test_security_mcp_run(self, temp_repo):
        """Test security MCP server run function."""
        from mcp_servers.security_mcp import server
        result = server.run({
            "repo_path": str(temp_repo),
            "severity_threshold": "medium"
        })
        
        assert result["status"] == "success"
