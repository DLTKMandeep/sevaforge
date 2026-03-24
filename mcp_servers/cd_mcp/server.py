#!/usr/bin/env python3
"""
CD MCP Server - Continuous Deployment Configuration
Protocol layer for CDAgent

Mapped from: forgeflow cd <path>
"""
import sys
import json
from pathlib import Path

# Add project root to path for agent import
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from agents import CDAgent
from core.models import wrap_agent_result

# Server metadata
SERVER_NAME = "cd-mcp-server"
AGENT_NAME = "CDAgent"

# Single agent instance
_agent = None


def get_agent():
    """Lazy initialization of agent."""
    global _agent
    if _agent is None:
        _agent = CDAgent()
    return _agent


def run(params: dict) -> dict:
    """
    MCP Server entry point for CD configuration generation.
    
    Args:
        params: Dictionary containing:
            - repo_path: Path to repository
            - repo_url: Git repository URL - default: https://github.com/org/repo.git
            - include_flux: Whether to include FluxCD config - default: False
            - include_helm: Whether to include Helm charts - default: False
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    agent = get_agent()
    agent_result = agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == "__main__":
    # For testing
    import argparse
    parser = argparse.ArgumentParser(description="CD MCP Server")
    parser.add_argument("--repo-path", default=".", help="Repository path")
    parser.add_argument("--repo-url", default="https://github.com/org/repo.git", help="Git repo URL")
    parser.add_argument("--include-flux", action="store_true", help="Include FluxCD")
    parser.add_argument("--include-helm", action="store_true", help="Include Helm charts")
    args = parser.parse_args()
    
    result = run({
        "repo_path": args.repo_path,
        "repo_url": args.repo_url,
        "include_flux": args.include_flux,
        "include_helm": args.include_helm
    })
    print(json.dumps(result, indent=2))
