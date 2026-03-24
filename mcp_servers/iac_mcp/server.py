#!/usr/bin/env python3
"""
IAC MCP Server - Infrastructure as Code Generation
Protocol layer for IACAgent

Mapped from: forgeflow iac <path>
"""
import sys
import json
from pathlib import Path

# Add project root to path for agent import
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from agents import IACAgent
from core.models import wrap_agent_result

# Server metadata
SERVER_NAME = "iac-mcp-server"
AGENT_NAME = "IACAgent"

# Single agent instance
_agent = None


def get_agent():
    """Lazy initialization of agent."""
    global _agent
    if _agent is None:
        _agent = IACAgent()
    return _agent


def run(params: dict) -> dict:
    """
    MCP Server entry point for IAC generation.
    
    Args:
        params: Dictionary containing:
            - repo_path: Path to repository
            - cloud: Cloud provider (aws, gcp, azure) - default: aws
            - include_pulumi: Whether to include Pulumi config - default: False
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    agent = get_agent()
    agent_result = agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == "__main__":
    # For testing
    import argparse
    parser = argparse.ArgumentParser(description="IAC MCP Server")
    parser.add_argument("--repo-path", default=".", help="Repository path")
    parser.add_argument("--cloud", default="aws", help="Cloud provider")
    parser.add_argument("--include-pulumi", action="store_true", help="Include Pulumi")
    args = parser.parse_args()
    
    result = run({
        "repo_path": args.repo_path,
        "cloud": args.cloud,
        "include_pulumi": args.include_pulumi
    })
    print(json.dumps(result, indent=2))
