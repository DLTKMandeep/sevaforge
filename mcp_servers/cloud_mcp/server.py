#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Cloud Deployment
Protocol layer that delegates to DeploymentAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import DeploymentAgent


# Instantiate the agent
_agent = DeploymentAgent()


def run(params: dict) -> dict:
    """
    Deploy to cloud infrastructure.
    Delegates to DeploymentAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' and optional 'target' keys
        
    Returns:
        Result dictionary from DeploymentAgent
    """
    print(f"  ☁️  [Cloud MCP] Delegating to DeploymentAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
