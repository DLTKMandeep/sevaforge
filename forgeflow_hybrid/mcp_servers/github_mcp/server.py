#!/usr/bin/env python3
"""
ForgeFlow MCP Server: GitHub Bridge
Protocol layer that delegates to BridgeAgent.

Architecture: Orchestrator → MCP Server → Agent → Results

Supported Operations:
- init: Initialize git repository
- push: Push to remote repository
- pr: Create pull request
- branch: Create/switch branches
- status: Check repository status (default)
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for agent import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents import BridgeAgent


# Instantiate the agent
_agent = BridgeAgent()


def run(params: dict) -> dict:
    """
    Bridge to GitHub with full Git/GitHub integration.
    Delegates to BridgeAgent for actual business logic.
    
    Args:
        params: Dictionary with:
            - path: Repository path
            - operation: One of 'init', 'push', 'pr', 'branch', 'status'
            - repo: GitHub repository (owner/repo)
            - branch: Branch name
            - base_branch: Base branch for PR
            - message: Commit message
            - pr_title: Pull request title
            - pr_body: Pull request body
        
    Returns:
        Result dictionary from BridgeAgent
    """
    operation = params.get('operation', 'status')
    print(f"  🌉 [GitHub MCP] Operation: {operation} → Delegating to BridgeAgent...")
    return _agent.execute(params)


if __name__ == '__main__':
    # CLI usage for testing
    import argparse
    parser = argparse.ArgumentParser(description='GitHub Bridge MCP Server')
    parser.add_argument('path', nargs='?', default='.', help='Repository path')
    parser.add_argument('--operation', '-o', default='status', 
                       choices=['init', 'push', 'pr', 'branch', 'status'],
                       help='Operation to perform')
    parser.add_argument('--repo', '-r', help='GitHub repository (owner/repo)')
    parser.add_argument('--branch', '-b', help='Branch name')
    parser.add_argument('--base-branch', default='main', help='Base branch for PR')
    parser.add_argument('--message', '-m', help='Commit message')
    parser.add_argument('--pr-title', help='PR title')
    parser.add_argument('--pr-body', help='PR body')
    
    args = parser.parse_args()
    
    result = run({
        'path': args.path,
        'operation': args.operation,
        'repo': args.repo,
        'branch': args.branch,
        'base_branch': args.base_branch,
        'message': args.message,
        'pr_title': args.pr_title,
        'pr_body': args.pr_body
    })
    print(json.dumps(result, indent=2))
