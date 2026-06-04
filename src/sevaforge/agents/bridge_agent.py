"""
SevaForge Bridge Agent

Bridges local Git repositories to GitHub: creates remote repos, pushes code,
opens pull requests, manages branches, and reports repo status.  Uses pattern-
based git command sequences with conflict resolution and LLM-generated PR
descriptions.

Capabilities:
  - create_repo:       Create a new GitHub repository
  - push_changes:      Push local changes to remote with conflict handling
  - create_pr:         Create a pull request with LLM-written description
  - manage_branches:   Create, list, delete, or switch branches
  - repo_status:       Report local vs remote status, divergence, and health
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)

logger = logging.getLogger(__name__)


# -- Git command templates ---------------------------------------------------

_GIT_COMMANDS: dict[str, list[str]] = {
    "init_and_push": [
        "git init",
        "git add -A",
        'git commit -m "{message}"',
        "git branch -M main",
        "git remote add origin {remote_url}",
        "git push -u origin main",
    ],
    "push_existing": [
        "git add -A",
        'git commit -m "{message}"',
        "git push origin {branch}",
    ],
    "create_branch": [
        "git checkout -b {branch}",
        "git push -u origin {branch}",
    ],
    "delete_branch": [
        "git checkout main",
        "git branch -d {branch}",
        "git push origin --delete {branch}",
    ],
    "conflict_resolution": [
        "git fetch origin",
        "git rebase origin/{branch}",
        "git push origin {branch}",
    ],
    "force_push_safe": [
        "git push --force-with-lease origin {branch}",
    ],
}

# -- Repo status patterns ----------------------------------------------------

_STATUS_PATTERNS: dict[str, str] = {
    "ahead": r"Your branch is ahead of .+ by (\d+) commit",
    "behind": r"Your branch is behind .+ by (\d+) commit",
    "diverged": r"have diverged",
    "up_to_date": r"Your branch is up to date",
    "untracked": r"Untracked files:",
    "modified": r"Changes not staged for commit:",
    "staged": r"Changes to be committed:",
    "clean": r"nothing to commit, working tree clean",
}

# -- Branch naming convention patterns ---------------------------------------

_BRANCH_PATTERNS: dict[str, str] = {
    "feature": "feature/{name}",
    "bugfix": "bugfix/{name}",
    "hotfix": "hotfix/{name}",
    "release": "release/{version}",
    "chore": "chore/{name}",
}

# -- PR template -------------------------------------------------------------

_PR_TEMPLATE = (
    "## Summary\n\n{summary}\n\n"
    "## Changes\n\n{changes}\n\n"
    "## Testing\n\n{testing}\n\n"
    "## Checklist\n\n"
    "- [ ] Tests pass locally\n"
    "- [ ] No new warnings\n"
    "- [ ] Documentation updated\n"
    "- [ ] Reviewed for security implications\n"
)


class BridgeAgent(BaseAgent):
    """
    Git-to-GitHub bridge agent.

    Manages the connection between local Git repositories and GitHub,
    providing safe push workflows, PR creation with LLM-generated
    descriptions, and branch management.
    """

    SYSTEM_PROMPT = (
        "You are a senior developer who writes clear, descriptive pull request "
        "descriptions. Summarize the changes concisely, highlight breaking "
        "changes, and list what reviewers should focus on. Use Markdown "
        "formatting with sections: Summary, Changes, Testing, Checklist."
    )

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="bridge",
            name="Bridge Agent",
            description="Bridges local Git repos to GitHub — create, push, PR, branch, status",
            version="1.0.0",
            capabilities=[
                AgentCapability(
                    name="create_repo",
                    description="Create a new GitHub repository and push initial code",
                    input_schema={"repo_name": "str", "visibility": "str"},
                    output_schema={"remote_url": "str", "commands": "list"},
                ),
                AgentCapability(
                    name="push_changes",
                    description="Push local changes to remote with conflict resolution",
                    input_schema={"branch": "str", "message": "str"},
                    output_schema={"commands": "list", "status": "str"},
                ),
                AgentCapability(
                    name="create_pr",
                    description="Create a pull request with auto-generated description",
                    input_schema={"title": "str", "base": "str", "head": "str"},
                    output_schema={"pr_body": "str", "commands": "list"},
                ),
                AgentCapability(
                    name="manage_branches",
                    description="Create, list, delete, or switch branches",
                    input_schema={"operation": "str", "branch": "str"},
                    output_schema={"commands": "list"},
                ),
                AgentCapability(
                    name="repo_status",
                    description="Report local vs remote status and divergence",
                    input_schema={"git_status_output": "str"},
                    output_schema={"status": "dict"},
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["git", "github", "bridge", "pr", "branch"],
        ))

    # -- execute --------------------------------------------------------------

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute bridge operations.

        ctx.input: diff, status output, or commit messages
        ctx.params:
          - action: "create_repo" | "push" | "create_pr" | "branch" | "status"
          - repo_name: str
          - owner: str          (GitHub org or user)
          - visibility: str     (public | private)
          - branch: str
          - base_branch: str
          - message: str
          - title: str
          - branch_type: str    (feature, bugfix, hotfix, release, chore)
          - branch_operation: str  (create, delete, list)
        """
        action = ctx.params.get("action", "status")
        owner = ctx.params.get("owner", "org")
        repo_name = ctx.params.get("repo_name", "my-repo")
        branch = ctx.params.get("branch", "main")

        if action == "create_repo":
            return self._create_repo(owner, repo_name, ctx.params)

        if action == "push":
            return self._push_changes(branch, ctx.params, ctx.input)

        if action == "create_pr":
            return await self._create_pr(ctx, owner, repo_name)

        if action == "branch":
            return self._manage_branches(branch, ctx.params)

        # Default: status
        return self._parse_status(ctx.input)

    # -- Create repo ----------------------------------------------------------

    def _create_repo(
        self, owner: str, repo_name: str, params: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate commands to create a GitHub repo and push initial code."""
        visibility = params.get("visibility", "private")
        message = params.get("message", "Initial commit")
        remote_url = f"https://github.com/{owner}/{repo_name}.git"

        gh_create_cmd = (
            f"gh repo create {owner}/{repo_name} "
            f"--{visibility} --source=. --remote=origin --push"
        )

        commands = [gh_create_cmd] + [
            cmd.format(message=message, remote_url=remote_url)
            for cmd in _GIT_COMMANDS["init_and_push"]
        ]

        return {
            "remote_url": remote_url,
            "commands": commands,
            "visibility": visibility,
            "owner": owner,
            "repo_name": repo_name,
            "model_used": "template",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.95,
        }

    # -- Push changes ---------------------------------------------------------

    def _push_changes(
        self, branch: str, params: dict[str, Any], git_output: str,
    ) -> dict[str, Any]:
        """Generate push commands with conflict detection."""
        message = params.get("message", "Update")
        has_conflict = bool(re.search(r"CONFLICT|rejected|diverged", git_output, re.IGNORECASE))

        if has_conflict:
            commands = [
                cmd.format(branch=branch, message=message)
                for cmd in _GIT_COMMANDS["conflict_resolution"]
            ]
            strategy = "rebase-then-push"
        else:
            commands = [
                cmd.format(branch=branch, message=message)
                for cmd in _GIT_COMMANDS["push_existing"]
            ]
            strategy = "direct-push"

        return {
            "commands": commands,
            "strategy": strategy,
            "branch": branch,
            "conflict_detected": has_conflict,
            "model_used": "template",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.9,
        }

    # -- Create PR (LLM-enhanced) --------------------------------------------

    async def _create_pr(
        self, ctx: AgentExecutionContext, owner: str, repo_name: str,
    ) -> dict[str, Any]:
        """Create a PR with LLM-generated description."""
        title = ctx.params.get("title", "Update")
        base = ctx.params.get("base_branch", "main")
        head = ctx.params.get("branch", "feature/update")
        diff = ctx.input

        # LLM: generate meaningful PR body
        prompt = (
            f"Write a GitHub pull request description for a PR titled '{title}'.\n\n"
            f"Base branch: {base}\n"
            f"Head branch: {head}\n\n"
            f"Diff / changes:\n```\n{diff[:4000]}\n```\n\n"
            "Use the following structure:\n"
            "## Summary  (1-3 sentences)\n"
            "## Changes  (bullet list of what changed and why)\n"
            "## Testing  (how to test these changes)\n"
        )

        try:
            llm_response = await self.call_llm(ctx, prompt)
            pr_body = llm_response.content
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM unavailable for PR description: %s", exc)
            pr_body = _PR_TEMPLATE.format(
                summary=title,
                changes="See diff for details.",
                testing="Run test suite.",
            )
            model_used = "template-only"
            input_tokens = 0
            output_tokens = 0

        gh_pr_cmd = (
            f"gh pr create --repo {owner}/{repo_name} "
            f'--title "{title}" --base {base} --head {head} --body-file -'
        )

        return {
            "pr_body": pr_body,
            "title": title,
            "base": base,
            "head": head,
            "commands": [
                f"git push -u origin {head}",
                gh_pr_cmd,
            ],
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.85 if model_used != "template-only" else 0.6,
        }

    # -- Branch management ----------------------------------------------------

    def _manage_branches(
        self, branch: str, params: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate branch management commands."""
        operation = params.get("branch_operation", "create")
        branch_type = params.get("branch_type", "feature")

        if operation == "create":
            name_template = _BRANCH_PATTERNS.get(branch_type, "feature/{name}")
            full_branch = name_template.format(name=branch, version=branch)
            commands = [
                cmd.format(branch=full_branch)
                for cmd in _GIT_COMMANDS["create_branch"]
            ]
        elif operation == "delete":
            commands = [
                cmd.format(branch=branch)
                for cmd in _GIT_COMMANDS["delete_branch"]
            ]
            full_branch = branch
        else:
            commands = ["git branch -a"]
            full_branch = branch

        return {
            "commands": commands,
            "branch": full_branch,
            "operation": operation,
            "model_used": "template",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.95,
        }

    # -- Status parsing -------------------------------------------------------

    def _parse_status(self, git_output: str) -> dict[str, Any]:
        """Parse git status / fetch output into structured report."""
        status: dict[str, Any] = {
            "state": "unknown",
            "ahead": 0,
            "behind": 0,
            "untracked": False,
            "modified": False,
            "staged": False,
            "clean": False,
        }

        for key, pattern in _STATUS_PATTERNS.items():
            match = re.search(pattern, git_output)
            if match:
                if key == "ahead":
                    status["ahead"] = int(match.group(1))
                    status["state"] = "ahead"
                elif key == "behind":
                    status["behind"] = int(match.group(1))
                    status["state"] = "behind"
                elif key == "diverged":
                    status["state"] = "diverged"
                elif key == "up_to_date":
                    status["state"] = "up_to_date"
                elif key == "clean":
                    status["clean"] = True
                else:
                    status[key] = True

        # Determine sync recommendation
        if status["state"] == "diverged":
            status["recommendation"] = "Rebase or merge to resolve divergence"
        elif status["state"] == "behind":
            status["recommendation"] = f"Pull {status['behind']} commits from remote"
        elif status["state"] == "ahead":
            status["recommendation"] = f"Push {status['ahead']} commits to remote"
        elif status["clean"]:
            status["recommendation"] = "Repository is clean and up to date"
        else:
            status["recommendation"] = "Commit or stash local changes"

        return {
            "status": status,
            "model_used": "pattern",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.9,
        }
