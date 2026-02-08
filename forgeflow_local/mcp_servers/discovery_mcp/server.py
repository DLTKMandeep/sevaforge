#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Discovery
Protocol layer that delegates to DiscoveryAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import DiscoveryAgent


# Instantiate the agent
_agent = DiscoveryAgent()


def run(params: dict) -> dict:
    """
    Run discovery scan on repository.
    Delegates to DiscoveryAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' key for repository path
        
    Returns:
        Result dictionary from DiscoveryAgent
    """
    print(f"  🔍 [Discovery MCP] Delegating to DiscoveryAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
