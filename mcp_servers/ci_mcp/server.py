#!/usr/bin/env python3
"""
ForgeFlow MCP Server: CIAgent
Protocol layer that delegates to CIAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import CIAgent

# Instantiate the agent
_agent = CIAgent()


def run(params: dict) -> dict:
    """
    Run CIAgent task.
    Delegates to CIAgent for actual business logic.

    Args:
        params: Dictionary with 'path' key for repository path

    Returns:
        Result dictionary from CIAgent
    """
    print(f"  ⚙️ [CI MCP] Delegating to CIAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
