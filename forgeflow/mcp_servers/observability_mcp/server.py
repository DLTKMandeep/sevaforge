#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Observability (Monitoring)
Protocol layer that delegates to MonitoringAgent.

Architecture: Orchestrator → MCP Server → Agent → Results
"""
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import MonitoringAgent
from core.models import wrap_agent_result

logger = logging.getLogger("observability-mcp-server")

SERVER_NAME = "observability-mcp-server"
AGENT_NAME = "MonitoringAgent"

_agent = MonitoringAgent()


def run(params: dict) -> dict:
    """
    Set up monitoring and observability.
    Delegates to MonitoringAgent for actual business logic.
    
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
