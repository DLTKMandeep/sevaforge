#!/usr/bin/env python3
"""
Code Review Agent - Performs code review and git analysis.
Mapped to: review command → git_mcp
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .base_agent import BaseAgent


class CodeReviewAgent(BaseAgent):
    """Agent that performs code review and git analysis."""
    
    def __init__(self):
        super().__init__(
            name="code_review_agent",
            description="Analyzes git history, performs code review, checks commits"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Perform code review and git analysis."""
        repo_path = Path(params.get('path', '.'))
        review_findings = []
        
        self.log(f"Reviewing code in {repo_path.absolute()}...")
        
        # Check if git repository
        is_git_repo = (repo_path / '.git').exists()
        
        if is_git_repo:
            review_findings.extend(self._analyze_git_repo(repo_path))
        else:
            review_findings.append({
                'type': 'not_git',
                'message': 'Not a git repository',
                'severity': 'info'
            })
        
        # Code quality checks
        review_findings.extend(self._check_code_quality(repo_path))
        
        summary = f"Code review complete: {len(review_findings)} findings"
        self.log(summary)
        
        py_files = list(repo_path.rglob('*.py'))
        py_files = [f for f in py_files if '__pycache__' not in str(f)]
        
        return self.create_result(
            status='success',
            summary=summary,
            data={
                'is_git_repo': is_git_repo,
                'findings': review_findings,
                'files_scanned': len(py_files)
            },
            findings=[f"{f['type']}: {f['message']}" for f in review_findings]
        )
    
    def _run_git_command(self, repo_path: Path, args: List[str]) -> str:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                ['git'] + args,
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout.strip()
        except Exception as e:
            return f"Error: {e}"
    
    def _analyze_git_repo(self, repo_path: Path) -> List[Dict[str, Any]]:
        """Analyze git repository."""
        findings = []
        
        # Get recent commits
        log_output = self._run_git_command(repo_path, ['log', '--oneline', '-10'])
        commits = log_output.split('\n') if log_output and not log_output.startswith('Error') else []
        
        findings.append({
            'type': 'commits',
            'message': f'Recent commits: {len(commits)}',
            'data': commits[:5]
        })
        
        # Check for uncommitted changes
        status = self._run_git_command(repo_path, ['status', '--porcelain'])
        if status:
            changes = len(status.split('\n'))
            findings.append({
                'type': 'uncommitted',
                'message': f'{changes} uncommitted changes',
                'severity': 'warning'
            })
        
        # Get branch info
        branch = self._run_git_command(repo_path, ['branch', '--show-current'])
        findings.append({
            'type': 'branch',
            'message': f'Current branch: {branch}'
        })
        
        # Check for large files
        large_files = []
        for f in repo_path.rglob('*'):
            if f.is_file() and '.git' not in str(f):
                try:
                    if f.stat().st_size > 1_000_000:  # > 1MB
                        large_files.append(str(f.relative_to(repo_path)))
                except Exception:
                    pass
        
        if large_files:
            findings.append({
                'type': 'large_files',
                'message': f'{len(large_files)} files > 1MB',
                'severity': 'warning',
                'data': large_files[:5]
            })
        
        return findings
    
    def _check_code_quality(self, repo_path: Path) -> List[Dict[str, Any]]:
        """Check code quality."""
        findings = []
        
        py_files = list(repo_path.rglob('*.py'))
        py_files = [f for f in py_files if '__pycache__' not in str(f)]
        
        # Check for TODO/FIXME comments
        todo_count = 0
        for py_file in py_files[:50]:  # Limit
            try:
                content = py_file.read_text()
                todo_count += content.upper().count('TODO')
                todo_count += content.upper().count('FIXME')
            except Exception:
                pass
        
        if todo_count > 0:
            findings.append({
                'type': 'todos',
                'message': f'{todo_count} TODO/FIXME comments found',
                'severity': 'info'
            })
        
        return findings
