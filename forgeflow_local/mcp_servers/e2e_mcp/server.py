#!/usr/bin/env python3
"""
E2E MCP Server - End-to-End Testing Setup
Protocol layer for E2ETestingAgent

Mapped from: forgeflow e2e <path>
"""
import sys
import json
from pathlib import Path

# Add project root to path for agent import
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from agents import E2ETestingAgent
from core.models import wrap_agent_result

# Server metadata
SERVER_NAME = "e2e-mcp-server"
AGENT_NAME = "E2ETestingAgent"

# Single agent instance
_agent = None


def get_agent():
    """Lazy initialization of agent."""
    global _agent
    if _agent is None:
        _agent = E2ETestingAgent()
    return _agent


def run(params: dict) -> dict:
    """
    MCP Server entry point for E2E testing setup generation.
    
    Args:
        params: Dictionary containing:
            - repo_path: Path to repository
            - framework: Testing framework (playwright, cypress, both) - default: playwright
            - include_ci: Whether to include CI workflow - default: True
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    agent = get_agent()
    agent_result = agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == "__main__":
    # For testing
    import argparse
    parser = argparse.ArgumentParser(description="E2E MCP Server")
    parser.add_argument("--repo-path", default=".", help="Repository path")
    parser.add_argument("--framework", default="playwright", choices=["playwright", "cypress", "both"])
    parser.add_argument("--no-ci", action="store_true", help="Skip CI workflow")
    args = parser.parse_args()
    
    result = run({
        "repo_path": args.repo_path,
        "framework": args.framework,
        "include_ci": not args.no_ci
    })
    print(json.dumps(result, indent=2))
