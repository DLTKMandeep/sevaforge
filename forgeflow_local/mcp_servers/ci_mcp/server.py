#!/usr/bin/env python3
"""
CI MCP Server - Continuous Integration Pipeline
Protocol layer for CIAgent

Mapped from: forgeflow ci <path>
"""
import sys
import json
from pathlib import Path

# Add project root to path for agent import
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from agents import CIAgent
from core.models import wrap_agent_result

# Server metadata
SERVER_NAME = "ci-mcp-server"
AGENT_NAME = "CIAgent"

# Single agent instance
_agent = None


def get_agent():
    """Lazy initialization of agent."""
    global _agent
    if _agent is None:
        _agent = CIAgent()
    return _agent


def run(params: dict) -> dict:
    """
    MCP Server entry point for CI pipeline generation.
    
    Args:
        params: Dictionary containing:
            - repo_path: Path to repository
            - include_gitlab: Whether to include GitLab CI - default: True
            - include_dependabot: Whether to include Dependabot config - default: True
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    agent = get_agent()
    agent_result = agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == "__main__":
    # For testing
    import argparse
    parser = argparse.ArgumentParser(description="CI MCP Server")
    parser.add_argument("--repo-path", default=".", help="Repository path")
    parser.add_argument("--no-gitlab", action="store_true", help="Skip GitLab CI")
    parser.add_argument("--no-dependabot", action="store_true", help="Skip Dependabot")
    args = parser.parse_args()
    
    result = run({
        "repo_path": args.repo_path,
        "include_gitlab": not args.no_gitlab,
        "include_dependabot": not args.no_dependabot
    })
    print(json.dumps(result, indent=2))
