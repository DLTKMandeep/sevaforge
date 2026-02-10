#!/usr/bin/env python3
"""
ForgeFlow MCP Server: Discovery
Protocol layer that delegates to DiscoveryAgent.

Architecture: Orchestrator → MCP Server → Agent → Results

This server:
1. Receives params from Orchestrator
2. Delegates to DiscoveryAgent
3. Wraps result in MCPResponse format
4. Returns to Orchestrator (NO print statements)
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import DiscoveryAgent
from core.models import wrap_agent_result

# Configure logging (not printing)
logger = logging.getLogger("discovery-mcp-server")

# Server metadata
SERVER_NAME = "discovery-mcp-server"
AGENT_NAME = "DiscoveryAgent"

# Instantiate the agent (singleton per module load)
_agent = DiscoveryAgent()


def run(params: dict) -> dict:
    """
    Run discovery scan on repository.
    Delegates to DiscoveryAgent for actual business logic.
    
    Args:
        params: Dictionary with 'path' key for repository path
        
    Returns:
        MCPResponse dictionary with wrapped agent result
    """
    logger.info(f"Delegating to {AGENT_NAME}...")
    
    # Execute agent
    agent_result = _agent.execute(params)
    
    # Wrap in MCP response format
    return wrap_agent_result(agent_result, SERVER_NAME, AGENT_NAME)


if __name__ == '__main__':
    # CLI mode for standalone testing
    logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    result = run({'path': path})
    print(json.dumps(result, indent=2))
