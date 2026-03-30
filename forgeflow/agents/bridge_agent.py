#!/usr/bin/env python3
"""
Bridge Agent - GitHub operations: create repo, push, PR, branch management.
Mapped to: bridge command → github_mcp

Supported operations:
  create  — initialise git (if needed), create GitHub repo, push
  push    — stage, commit, and push to an existing remote
  pr      — create a pull request from the current branch
  branch  — create and/or switch to a branch
  status  — show git status and latest commit info
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

from .base_agent import BaseAgent


class BridgeAgent(BaseAgent):
    """Agent that bridges the local repo to GitHub via the gh CLI."""

    def __init__(self):
        super().__init__(
            name="bridge_agent",
            description="GitHub operations: create repo, push, PR, branch management"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch to the requested GitHub operation.

        Params:
            path        : local repo path (required)
            operation   : create | push | pr | branch | status  (default: create)
            repo_name   : override repo name (default: folder name)
            visibility  : public | private  (default: public)
            branch      : target branch name  (default: main)
            message     : commit message  (default: 'Update from ForgeFlow')
            pr_title    : PR title (operation=pr)
            pr_body     : PR body/description (operation=pr)
            base_branch : base branch for PR  (default: main)
            push_after  : push after creating branch  (default: True)
        """
        repo_path = Path(params.get('path', '.') or '.').resolve()
        operation  = params.get('operation', 'create').lower()
        repo_name  = params.get('repo_name') or repo_path.name
        visibility = params.get('visibility', 'public').lower()
        branch     = params.get('branch', 'main')
        message    = params.get('message', 'Update from ForgeFlow')
        pr_title   = params.get('pr_title', f'ForgeFlow: {branch}')
        pr_body    = params.get('pr_body', '')
        base_branch = params.get('base_branch', 'main')

        self.log(f"Bridge operation='{operation}' repo='{repo_name}' path={repo_path}")

        # gh CLI required for everything except status
        if operation != 'status' and not self._check_gh_cli():
            return self.create_result(
                status='error',
                summary='GitHub CLI (gh) not found or not authenticated',
                data={'error': 'gh CLI not installed or not authenticated'},
                findings=[
                    'Install: https://cli.github.com/',
                    'Authenticate: gh auth login',
                ]
            )

        dispatch = {
            'create': self._op_create,
            'push':   self._op_push,
            'pr':     self._op_pr,
            'branch': self._op_branch,
            'status': self._op_status,
        }

        if operation not in dispatch:
            return self.create_result(
                status='error',
                summary=f"Unknown operation '{operation}'",
                data={'valid_operations': list(dispatch.keys())},
                findings=[f"Use one of: {', '.join(dispatch.keys())}"]
            )

        return dispatch[operation](
            repo_path=repo_path,
            repo_name=repo_name,
            visibility=visibility,
            branch=branch,
            message=message,
            pr_title=pr_title,
            pr_body=pr_body,
            base_branch=base_branch,
            params=params,
        )

    # -----------------------------------------------------------------------
    # Operations
    # -----------------------------------------------------------------------

    def _op_create(self, repo_path, repo_name, visibility, branch, message, **kw) -> Dict:
        """Create a new GitHub repo, commit everything, and push."""
        # Init git if needed
        if not (repo_path / '.git').exists():
            ok, out = self._run(repo_path, ['git', 'init', '-b', branch])
            if not ok:
                return self._error(f"git init failed: {out}")
            self.log("Initialised git repository")
        else:
            # Ensure we're on the right branch
            self._run(repo_path, ['git', 'checkout', '-B', branch])

        # Stage and commit
        commit_result = self._stage_and_commit(repo_path, message)
        if commit_result:
            return commit_result

        # Create GitHub repo and push
        vis_flag = '--private' if visibility == 'private' else '--public'
        ok, out = self._run(
            repo_path,
            ['gh', 'repo', 'create', repo_name, vis_flag, '--source=.', '--push']
        )

        if ok:
            username = self._gh_username()
            repo_url = f"https://github.com/{username}/{repo_name}"
            return self.create_result(
                status='success',
                summary=f"Created {visibility} repo and pushed: {repo_url}",
                data={'repo_name': repo_name, 'repo_url': repo_url, 'visibility': visibility},
                findings=[
                    f"✅ Created GitHub repo: {repo_name} ({visibility})",
                    f"✅ Pushed branch: {branch}",
                    f"🔗 {repo_url}",
                ]
            )

        # Repo already exists — just push
        if 'already exists' in out.lower():
            self.log("Repo already exists, pushing to existing remote")
            return self._op_push(
                repo_path=repo_path, repo_name=repo_name,
                visibility=visibility, branch=branch, message=message, **kw
            )

        return self._error(f"gh repo create failed: {out}", manual=f"gh repo create {repo_name} {vis_flag} --source=. --push")

    def _op_push(self, repo_path, branch, message, **kw) -> Dict:
        """Stage uncommitted changes, commit, and push to an existing remote."""
        # Stage and commit if there are changes
        commit_result = self._stage_and_commit(repo_path, message)
        if commit_result:
            return commit_result  # hard error from commit step

        # First attempt — normal push
        ok, out = self._run(repo_path, ['git', 'push', '-u', 'origin', branch])
        if ok:
            return self.create_result(
                status='success',
                summary=f"Pushed branch '{branch}' to origin",
                data={'branch': branch, 'output': out},
                findings=[f"✅ Pushed '{branch}' to origin"]
            )

        # Push rejected because remote has diverged — try pull --rebase then push
        is_diverged = any(k in out.lower() for k in ('rejected', 'fetch first', 'non-fast-forward', 'diverged'))
        if is_diverged:
            self.log("Push rejected (diverged). Attempting git pull --rebase …")
            pull_ok, pull_out = self._run(repo_path, ['git', 'pull', '--rebase', 'origin', branch])
            if pull_ok:
                # Retry push after successful rebase
                ok2, out2 = self._run(repo_path, ['git', 'push', '-u', 'origin', branch])
                if ok2:
                    return self.create_result(
                        status='success',
                        summary=f"Pulled (rebase) + pushed branch '{branch}'",
                        data={'branch': branch},
                        findings=[
                            f"✅ Rebased on top of remote '{branch}'",
                            f"✅ Pushed '{branch}' to origin",
                        ]
                    )

            # Rebase had conflicts or push still failed — fall back to force-with-lease
            self.log("Rebase push failed. Falling back to --force-with-lease …")
            ok3, out3 = self._run(repo_path, ['git', 'push', '--force-with-lease', '-u', 'origin', branch])
            if ok3:
                return self.create_result(
                    status='warning',
                    summary=f"Force-pushed '{branch}' (remote was diverged — local wins)",
                    data={'branch': branch},
                    findings=[
                        f"⚠️  Remote '{branch}' had diverged; used --force-with-lease",
                        f"✅ Pushed '{branch}' to origin",
                    ]
                )
            return self._error(f"All push strategies failed: {out3}")

        return self._error(f"git push failed: {out}")

    def _op_pr(self, repo_path, branch, base_branch, pr_title, pr_body, **kw) -> Dict:
        """Create a pull request from current branch into base_branch."""
        # Make sure we're on the right branch and it's pushed
        cur_ok, current_branch = self._run(repo_path, ['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        current_branch = current_branch.strip()

        # Push branch first so it exists on remote
        self._run(repo_path, ['git', 'push', '-u', 'origin', current_branch])

        cmd = [
            'gh', 'pr', 'create',
            '--title', pr_title,
            '--base', base_branch,
            '--head', current_branch,
        ]
        if pr_body:
            cmd += ['--body', pr_body]
        else:
            cmd += ['--body', f'Automated PR created by ForgeFlow from `{current_branch}` → `{base_branch}`']

        ok, out = self._run(repo_path, cmd)
        if ok:
            return self.create_result(
                status='success',
                summary=f"PR created: {pr_title}",
                data={
                    'pr_title': pr_title,
                    'head': current_branch,
                    'base': base_branch,
                    'pr_url': out.strip(),
                },
                findings=[
                    f"✅ PR created: '{pr_title}'",
                    f"   {current_branch} → {base_branch}",
                    f"🔗 {out.strip()}",
                ]
            )

        if 'already exists' in out.lower():
            return self.create_result(
                status='warning',
                summary=f"PR already exists for {current_branch} → {base_branch}",
                data={'head': current_branch, 'base': base_branch},
                findings=[f"PR already open: {current_branch} → {base_branch}"]
            )

        return self._error(f"gh pr create failed: {out}")

    def _op_branch(self, repo_path, branch, params, **kw) -> Dict:
        """Create and optionally push a new branch."""
        push_after = params.get('push_after', True)

        # Create and switch to branch (or just switch if it already exists)
        ok, out = self._run(repo_path, ['git', 'checkout', '-b', branch])
        if not ok:
            if 'already exists' in out.lower():
                ok, out = self._run(repo_path, ['git', 'checkout', branch])
                if not ok:
                    return self._error(f"git checkout {branch} failed: {out}")
                action = 'switched'
            else:
                return self._error(f"git checkout -b {branch} failed: {out}")
        else:
            action = 'created'

        findings = [f"✅ Branch '{branch}' {action}"]

        if push_after:
            push_ok, push_out = self._run(repo_path, ['git', 'push', '-u', 'origin', branch])
            if push_ok:
                findings.append(f"✅ Pushed '{branch}' to origin")
            else:
                findings.append(f"⚠️  Push failed: {push_out}")

        return self.create_result(
            status='success',
            summary=f"Branch '{branch}' {action}",
            data={'branch': branch, 'action': action},
            findings=findings
        )

    def _op_status(self, repo_path, **kw) -> Dict:
        """Return git status and last commit info."""
        _, status_out = self._run(repo_path, ['git', 'status', '--short'])
        _, branch_out = self._run(repo_path, ['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
        _, log_out    = self._run(repo_path, ['git', 'log', '-3', '--oneline'])
        _, remote_out = self._run(repo_path, ['git', 'remote', '-v'])

        is_clean = not bool(status_out.strip())
        branch = branch_out.strip()

        findings = [
            f"Branch: {branch}",
            "Working tree: clean" if is_clean else f"Uncommitted changes:\n{status_out}",
        ]
        if log_out:
            findings.append(f"Recent commits:\n{log_out}")
        if remote_out:
            findings.append(f"Remotes:\n{remote_out}")

        return self.create_result(
            status='success',
            summary=f"Git status on branch '{branch}' — {'clean' if is_clean else 'has changes'}",
            data={
                'branch': branch,
                'is_clean': is_clean,
                'status': status_out,
                'recent_commits': log_out,
                'remotes': remote_out,
            },
            findings=findings
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _stage_and_commit(self, repo_path: Path, message: str) -> Optional[Dict]:
        """
        Stage all changes and commit. Returns an error result dict if commit fails,
        or None if nothing needed committing / commit succeeded.
        Avoids staging files that should be gitignored.
        """
        _, status_out = self._run(repo_path, ['git', 'status', '--porcelain'])
        if not status_out.strip():
            self.log("Nothing to commit, working tree clean")
            return None

        # Use `git add .` which respects .gitignore
        ok, out = self._run(repo_path, ['git', 'add', '.'])
        if not ok:
            return self._error(f"git add failed: {out}")

        ok, out = self._run(repo_path, ['git', 'commit', '-m', message])
        if not ok and 'nothing to commit' not in out.lower():
            return self._error(f"git commit failed: {out}")

        self.log(f"Committed: {message}")
        return None

    def _run(self, cwd: Path, args: list) -> Tuple[bool, str]:
        """Run a subprocess command and return (success, combined_output)."""
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=120
            )
            output = (result.stdout or '') + (result.stderr or '')
            return result.returncode == 0, output.strip()
        except Exception as e:
            return False, str(e)

    def _check_gh_cli(self) -> bool:
        """Check if gh CLI is installed and authenticated."""
        try:
            result = subprocess.run(['gh', 'auth', 'status'], capture_output=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False

    def _gh_username(self) -> str:
        """Return the authenticated GitHub username."""
        try:
            result = subprocess.run(
                ['gh', 'api', 'user', '--jq', '.login'],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else 'YOUR_USERNAME'
        except Exception:
            return 'YOUR_USERNAME'

    def _error(self, message: str, manual: str = '') -> Dict:
        findings = [f"❌ {message}"]
        if manual:
            findings.append(f"Manual command: {manual}")
        return self.create_result(
            status='error',
            summary=message,
            data={'error': message, 'manual_command': manual},
            findings=findings
        )
