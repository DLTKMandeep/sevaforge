#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Security
Protocol layer that delegates to SecurityAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import SecurityAgent


# Instantiate the agent
_agent = SecurityAgent()


def run(params: dict) -> dict:
    """
    Run security scan on repository.
    Delegates to SecurityAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' and optional 'severity_threshold' keys
        
    Returns:
        Result dictionary from SecurityAgent
    """
    print(f"  🔒 [Security MCP] Delegating to SecurityAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
