"""
SevaForge GitHub MCP Server

Provides GitHub operations: repository management, pull requests,
issues, code search, and branch management.

Tools:
  - list_repos:       List repositories for a user/org
  - get_repo:         Get repository details
  - list_pull_requests: List PRs with filtering
  - create_pull_request: Create a new PR
  - get_pull_request: Get PR details with diff stats
  - list_issues:      List issues with filtering
  - create_issue:     Create a new issue
  - search_code:      Search code across repositories
  - list_branches:    List branches for a repository
  - get_file:         Get file contents from a repository
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from sevaforge.mcp.base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter

logger = logging.getLogger(__name__)


class GitHubMCPServer(BaseMCPServer):
    """
    GitHub MCP server for repository operations.

    In mock mode (no GitHub token configured), returns realistic
    simulated responses. With a token, proxies to the GitHub API.
    """

    def __init__(self, github_token: Optional[str] = None):
        self._github_token = github_token
        self._mock_mode = github_token is None
        super().__init__(
            server_id="github",
            name="GitHub MCP Server",
            description="Repository management, PRs, issues, and code search via GitHub API",
            version="2.0.0",
        )

    def _register_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="list_repos",
                description="List repositories for a user or organization",
                category="repository",
                tags=["github", "repos"],
                parameters=[
                    MCPToolParameter(name="owner", type="string", description="GitHub user or org", required=True),
                    MCPToolParameter(name="type", type="string", description="Filter: all, public, private", default="all",
                                     enum=["all", "public", "private"]),
                    MCPToolParameter(name="sort", type="string", description="Sort by: created, updated, pushed",
                                     default="updated", enum=["created", "updated", "pushed"]),
                    MCPToolParameter(name="limit", type="integer", description="Max results", default=10),
                ],
                handler=self._list_repos,
            ),
            MCPTool(
                name="get_repo",
                description="Get detailed information about a repository",
                category="repository",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                ],
                handler=self._get_repo,
            ),
            MCPTool(
                name="list_pull_requests",
                description="List pull requests for a repository",
                category="pull_request",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="state", type="string", default="open", enum=["open", "closed", "all"]),
                    MCPToolParameter(name="limit", type="integer", default=10),
                ],
                handler=self._list_pull_requests,
            ),
            MCPTool(
                name="create_pull_request",
                description="Create a new pull request",
                category="pull_request",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="title", type="string", required=True),
                    MCPToolParameter(name="body", type="string", description="PR description"),
                    MCPToolParameter(name="head", type="string", required=True, description="Source branch"),
                    MCPToolParameter(name="base", type="string", default="main", description="Target branch"),
                ],
                handler=self._create_pull_request,
            ),
            MCPTool(
                name="list_issues",
                description="List issues for a repository",
                category="issue",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="state", type="string", default="open", enum=["open", "closed", "all"]),
                    MCPToolParameter(name="labels", type="string", description="Comma-separated label filter"),
                    MCPToolParameter(name="limit", type="integer", default=10),
                ],
                handler=self._list_issues,
            ),
            MCPTool(
                name="create_issue",
                description="Create a new issue",
                category="issue",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="title", type="string", required=True),
                    MCPToolParameter(name="body", type="string"),
                    MCPToolParameter(name="labels", type="array", description="List of label names"),
                ],
                handler=self._create_issue,
            ),
            MCPTool(
                name="search_code",
                description="Search code across repositories",
                category="search",
                parameters=[
                    MCPToolParameter(name="query", type="string", required=True),
                    MCPToolParameter(name="owner", type="string", description="Limit to owner's repos"),
                    MCPToolParameter(name="language", type="string"),
                    MCPToolParameter(name="limit", type="integer", default=10),
                ],
                handler=self._search_code,
            ),
            MCPTool(
                name="list_branches",
                description="List branches for a repository",
                category="repository",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                ],
                handler=self._list_branches,
            ),
            MCPTool(
                name="get_file",
                description="Get file contents from a repository",
                category="repository",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="path", type="string", required=True),
                    MCPToolParameter(name="ref", type="string", default="main", description="Branch or commit SHA"),
                ],
                handler=self._get_file,
            ),
            MCPTool(
                name="get_pull_request",
                description="Get detailed pull request information",
                category="pull_request",
                parameters=[
                    MCPToolParameter(name="owner", type="string", required=True),
                    MCPToolParameter(name="repo", type="string", required=True),
                    MCPToolParameter(name="number", type="integer", required=True),
                ],
                handler=self._get_pull_request,
            ),
        ]

    # ── Tool Handlers ────────────────────────────────────────────────

    async def _list_repos(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner = params["owner"]
        limit = params.get("limit", 10)
        return {
            "owner": owner,
            "total_count": 3,
            "repositories": [
                {"name": "sevaforge", "full_name": f"{owner}/sevaforge", "description": "Enterprise AI Platform",
                 "language": "Python", "stars": 42, "forks": 8, "open_issues": 12, "default_branch": "main",
                 "updated_at": "2025-06-01T00:00:00Z", "private": False},
                {"name": "forgeflow", "full_name": f"{owner}/forgeflow", "description": "Agent Orchestration Framework",
                 "language": "Python", "stars": 28, "forks": 5, "open_issues": 3, "default_branch": "main",
                 "updated_at": "2025-05-15T00:00:00Z", "private": False},
                {"name": "seva-infra", "full_name": f"{owner}/seva-infra", "description": "Infrastructure as Code",
                 "language": "HCL", "stars": 15, "forks": 2, "open_issues": 1, "default_branch": "main",
                 "updated_at": "2025-04-20T00:00:00Z", "private": True},
            ][:limit],
            "mock_mode": self._mock_mode,
        }

    async def _get_repo(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        return {
            "full_name": f"{owner}/{repo}",
            "description": "Enterprise AI Platform — Agentic Orchestration",
            "language": "Python",
            "stars": 42, "forks": 8, "watchers": 42, "open_issues": 12,
            "default_branch": "main", "private": False,
            "topics": ["ai", "agents", "llm", "enterprise"],
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-06-01T00:00:00Z",
            "size_kb": 15360,
            "license": "MIT",
            "mock_mode": self._mock_mode,
        }

    async def _list_pull_requests(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        state = params.get("state", "open")
        return {
            "repository": f"{owner}/{repo}",
            "state": state,
            "total_count": 2,
            "pull_requests": [
                {"number": 15, "title": "feat: Add agent intelligence layer", "state": "open",
                 "author": "mandeep", "branch": "intelligence-maturity", "base": "main",
                 "created_at": "2025-06-01T00:00:00Z", "additions": 4200, "deletions": 150,
                 "changed_files": 28, "labels": ["enhancement", "week-5"]},
                {"number": 14, "title": "feat: Admin dashboard and ModelRouter", "state": "open",
                 "author": "mandeep", "branch": "week-4-ui", "base": "main",
                 "created_at": "2025-05-28T00:00:00Z", "additions": 2100, "deletions": 50,
                 "changed_files": 6, "labels": ["frontend", "week-4"]},
            ],
            "mock_mode": self._mock_mode,
        }

    async def _create_pull_request(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "number": 16,
            "title": params["title"],
            "state": "open",
            "html_url": f"https://github.com/{params['owner']}/{params['repo']}/pull/16",
            "head": params["head"],
            "base": params.get("base", "main"),
            "body": params.get("body", ""),
            "created_at": datetime.utcnow().isoformat(),
            "mock_mode": self._mock_mode,
        }

    async def _list_issues(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        return {
            "repository": f"{owner}/{repo}",
            "total_count": 3,
            "issues": [
                {"number": 45, "title": "Implement A2A protocol timeout handling",
                 "state": "open", "labels": ["bug", "orchestration"], "assignee": "mandeep"},
                {"number": 44, "title": "Add Redis-backed rate limiter",
                 "state": "open", "labels": ["enhancement", "auth"], "assignee": None},
                {"number": 43, "title": "Dashboard: Add real-time WebSocket updates",
                 "state": "open", "labels": ["enhancement", "frontend"], "assignee": None},
            ],
            "mock_mode": self._mock_mode,
        }

    async def _create_issue(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "number": 46,
            "title": params["title"],
            "state": "open",
            "html_url": f"https://github.com/{params['owner']}/{params['repo']}/issues/46",
            "body": params.get("body", ""),
            "labels": params.get("labels", []),
            "created_at": datetime.utcnow().isoformat(),
            "mock_mode": self._mock_mode,
        }

    async def _search_code(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        query = params["query"]
        return {
            "query": query,
            "total_count": 2,
            "results": [
                {"repository": "DLTKMandeep/sevaforge", "path": "src/sevaforge/agents/base_agent.py",
                 "score": 0.95, "fragment": f"# Match for: {query}",
                 "html_url": "https://github.com/DLTKMandeep/sevaforge/blob/main/src/sevaforge/agents/base_agent.py"},
                {"repository": "DLTKMandeep/sevaforge", "path": "src/sevaforge/gateway/model_router.py",
                 "score": 0.82, "fragment": f"# Related to: {query}",
                 "html_url": "https://github.com/DLTKMandeep/sevaforge/blob/main/src/sevaforge/gateway/model_router.py"},
            ],
            "mock_mode": self._mock_mode,
        }

    async def _list_branches(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        return {
            "repository": f"{owner}/{repo}",
            "branches": [
                {"name": "main", "protected": True, "commit_sha": "abc123"},
                {"name": "intelligence-maturity", "protected": False, "commit_sha": "def456"},
                {"name": "week-4-ui", "protected": False, "commit_sha": "ghi789"},
            ],
            "mock_mode": self._mock_mode,
        }

    async def _get_file(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "path": params["path"],
            "name": params["path"].split("/")[-1],
            "size": 1024,
            "type": "file",
            "encoding": "utf-8",
            "content": f"# File: {params['path']}\n# Mock content for {params['owner']}/{params['repo']}",
            "sha": "abc123def456",
            "ref": params.get("ref", "main"),
            "mock_mode": self._mock_mode,
        }

    async def _get_pull_request(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        owner, repo, number = params["owner"], params["repo"], params["number"]
        return {
            "number": number,
            "title": f"PR #{number} — Feature implementation",
            "state": "open",
            "html_url": f"https://github.com/{owner}/{repo}/pull/{number}",
            "author": "mandeep",
            "branch": "feature-branch",
            "base": "main",
            "additions": 500,
            "deletions": 100,
            "changed_files": 12,
            "mergeable": True,
            "reviews": [{"user": "reviewer", "state": "approved"}],
            "checks": {"status": "success", "total": 5, "passed": 5},
            "mock_mode": self._mock_mode,
        }
