#!/usr/bin/env python3
"""
ForgeFlow MCP Server: GitHub (Bridge)
Protocol layer that delegates to BridgeAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import BridgeAgent
from core.models import wrap_agent_result

logger = logging.getLogger("github-mcp-server")

SERVER_NAME = "github-mcp-server"
AGENT_NAME = "BridgeAgent"

_agent = BridgeAgent()


def run(params: dict) -> dict:
    """
    Bridge to GitHub - create repo and push code.
    Delegates to BridgeAgent for actual business logic.
    
    Args:
        params: Dictionary with:
            - path: Repository path
            - repo: GitHub repo name (optional)
            - branch: Branch name (optional)
            - operation: Operation type (optional)
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    operation = params.get('operation', 'create')
    logger.info(f"Operation: {operation} → Delegating to {AGENT_NAME}...")
    agent_result = _agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    repo = sys.argv[2] if len(sys.argv) > 2 else None
    result = run({'path': path, 'repo': repo, 'operation': 'push'})
    print(json.dumps(result, indent=2))
