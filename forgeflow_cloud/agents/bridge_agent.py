#!/usr/bin/env python3
"""
Bridge Agent - Simple GitHub repo creation and push.
Mapped to: bridge command → github_mcp

SIMPLIFIED: 
- Extracts folder name from path (e.g., /Users/john/myapp → myapp)
- Runs: gh repo create <folder_name> --public --source=. --push
- Returns success/failure
"""
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Tuple

from .base_agent import BaseAgent


class BridgeAgent(BaseAgent):
    """Simple agent that creates a GitHub repo from the current folder and pushes."""
    
    def __init__(self):
        super().__init__(
            name="bridge_agent",
            description="Creates GitHub repo and pushes code"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create GitHub repo and push code.
        
        Params:
            path: Repository path (folder name becomes repo name)
        """
        repo_path = Path(params.get('path', '.') or '.').resolve()
        
        # Extract folder name for repo name
        repo_name = repo_path.name
        self.log(f"Bridge: Creating GitHub repo '{repo_name}' from {repo_path}")
        
        # Check if gh CLI is available
        if not self._check_gh_cli():
            return self.create_result(
                status='error',
                summary='GitHub CLI (gh) not found',
                data={
                    'repo_name': repo_name,
                    'error': 'gh CLI not installed or not authenticated'
                },
                findings=[
                    'Install GitHub CLI: https://cli.github.com/',
                    'Then run: gh auth login'
                ]
            )
        
        # Initialize git if needed
        if not (repo_path / '.git').exists():
            success, output = self._run_command(repo_path, ['git', 'init'])
            if not success:
                return self.create_result(
                    status='error',
                    summary='Failed to initialize git',
                    data={'error': output},
                    findings=['git init failed']
                )
            self.log("Initialized git repository")
        
        # Stage and commit if there are changes
        success, status = self._run_command(repo_path, ['git', 'status', '--porcelain'])
        if status:
            self._run_command(repo_path, ['git', 'add', '-A'])
            self._run_command(repo_path, ['git', 'commit', '-m', 'Initial commit from ForgeFlow'])
            self.log("Committed changes")
        
        # Create repo and push: gh repo create <name> --public --source=. --push
        success, output = self._run_command(
            repo_path, 
            ['gh', 'repo', 'create', repo_name, '--public', '--source=.', '--push']
        )
        
        if success:
            return self.create_result(
                status='success',
                summary=f'Successfully created repo and pushed: {repo_name}',
                data={
                    'repo_name': repo_name,
                    'repo_url': f'https://github.com/{self._get_gh_username()}/{repo_name}',
                    'output': output
                },
                findings=[
                    f'✓ Created GitHub repo: {repo_name}',
                    '✓ Pushed code to main branch',
                    f'✓ View at: https://github.com/{self._get_gh_username()}/{repo_name}'
                ]
            )
        else:
            # Check if repo already exists
            if 'already exists' in output.lower():
                # Try just pushing to existing repo
                push_success, push_output = self._run_command(
                    repo_path,
                    ['git', 'push', '-u', 'origin', 'main']
                )
                if push_success:
                    return self.create_result(
                        status='success',
                        summary=f'Pushed to existing repo: {repo_name}',
                        data={'repo_name': repo_name, 'output': push_output},
                        findings=['Repo already exists, pushed updates']
                    )
            
            return self.create_result(
                status='error',
                summary=f'Failed to create/push repo: {repo_name}',
                data={
                    'repo_name': repo_name,
                    'error': output,
                    'manual_command': f'gh repo create {repo_name} --public --source=. --push'
                },
                findings=[
                    f'Failed: {output}',
                    'Try manually: gh repo create ' + repo_name + ' --public --source=. --push'
                ]
            )
    
    def _run_command(self, cwd: Path, args: list) -> Tuple[bool, str]:
        """Run a command and return (success, output)."""
        try:
            result = subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=120
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except Exception as e:
            return False, str(e)
    
    def _check_gh_cli(self) -> bool:
        """Check if GitHub CLI is available and authenticated."""
        try:
            result = subprocess.run(['gh', 'auth', 'status'], capture_output=True, timeout=10)
            return result.returncode == 0
        except:
            return False
    
    def _get_gh_username(self) -> str:
        """Get the authenticated GitHub username."""
        try:
            result = subprocess.run(
                ['gh', 'api', 'user', '--jq', '.login'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else 'YOUR_USERNAME'
        except:
            return 'YOUR_USERNAME'
