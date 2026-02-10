#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Observability and Monitoring
Protocol layer that delegates to MonitoringAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import MonitoringAgent


# Instantiate the agent
_agent = MonitoringAgent()


def run(params: dict) -> dict:
    """
    Set up monitoring and observability.
    Delegates to MonitoringAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' key for repository path
        
    Returns:
        Result dictionary from MonitoringAgent
    """
    print(f"  📊 [Observability MCP] Delegating to MonitoringAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
