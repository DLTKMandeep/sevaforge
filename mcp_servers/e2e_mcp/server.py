#!/usr/bin/env python3
"""
ForgeFlow MCP Server: E2ETestingAgent
Protocol layer that delegates to E2ETestingAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import E2ETestingAgent

# Instantiate the agent
_agent = E2ETestingAgent()


def run(params: dict) -> dict:
    """
    Run E2ETestingAgent task.
    Delegates to E2ETestingAgent for actual business logic.

    Args:
        params: Dictionary with 'path' key for repository path

    Returns:
        Result dictionary from E2ETestingAgent
    """
    print(f"  🧪 [E2E MCP] Delegating to E2ETestingAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
