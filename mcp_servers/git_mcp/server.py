#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Git (Code Review)
Protocol layer that delegates to CodeReviewAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import CodeReviewAgent
from core.models import wrap_agent_result

logger = logging.getLogger("git-mcp-server")

SERVER_NAME = "git-mcp-server"
AGENT_NAME = "CodeReviewAgent"

_agent = CodeReviewAgent()


def run(params: dict) -> dict:
    """
    Run code review and quality analysis.
    Delegates to CodeReviewAgent for actual business logic.
    
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    logger.info(f"Delegating to {AGENT_NAME}...")
    agent_result = _agent.execute(params)
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
