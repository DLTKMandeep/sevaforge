#!/usr/bin/env python3
"""
ForgeFlow MCP Server: IACAgent
Protocol layer that delegates to IACAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import IACAgent

# Instantiate the agent
_agent = IACAgent()


def run(params: dict) -> dict:
    """
    Run IACAgent task.
    Delegates to IACAgent for actual business logic.

    Args:
        params: Dictionary with 'path' key for repository path

    Returns:
        Result dictionary from IACAgent
    """
    print(f"  🏗️ [IAC MCP] Delegating to IACAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
