#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Deployment Artifact Generation
Protocol layer that delegates to GenerationAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import GenerationAgent


# Instantiate the agent
_agent = GenerationAgent()


def run(params: dict) -> dict:
    """
    Generate deployment artifacts.
    Delegates to GenerationAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' and optional 'stack' keys
        
    Returns:
        Result dictionary from GenerationAgent
    """
    print(f"  📦 [Deployment MCP] Delegating to GenerationAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
