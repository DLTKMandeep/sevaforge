#!/usr/bin/env python3
"""
Normalization Agent - Standardizes repository structure.
Mapped to: normalize command → normalize_mcp
"""
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent


STANDARD_FILES = {
    'README.md': '# Project\n\nProject description here.\n',
    '.gitignore': '__pycache__/\n*.pyc\n.env\nvenv/\nnode_modules/\n.DS_Store\n',
    'LICENSE': 'MIT License\n\nCopyright (c) 2024\n',
}

STANDARD_DIRS = ['src', 'tests', 'docs', 'config']


class NormalizationAgent(BaseAgent):
    """Agent that normalizes repository structure."""
    
    def __init__(self):
        super().__init__(
            name="normalization_agent",
            description="Standardizes repository structure, adds missing files, fixes formatting"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run normalization on repository."""
        repo_path = Path(params.get('path', '.'))
        actions = []
        
        self.log(f"Normalizing {repo_path.absolute()}...")
        
        # Check for missing standard files
        for filename, default_content in STANDARD_FILES.items():
            file_path = repo_path / filename
            if not file_path.exists():
                actions.append({
                    'item': filename,
                    'type': 'create_file',
                    'status': 'pending',
                    'action': f'Create missing {filename}'
                })
            else:
                actions.append({
                    'item': filename,
                    'type': 'verify',
                    'status': 'exists',
                    'action': f'{filename} already exists'
                })
        
        # Check for missing standard directories
        for dirname in STANDARD_DIRS:
            dir_path = repo_path / dirname
            if not dir_path.exists():
                actions.append({
                    'item': dirname,
                    'type': 'create_dir',
                    'status': 'pending',
                    'action': f'Create missing {dirname}/ directory'
                })
            else:
                actions.append({
                    'item': dirname,
                    'type': 'verify',
                    'status': 'exists',
                    'action': f'{dirname}/ already exists'
                })
        
        # Check for code style issues (basic)
        style_issues = self._check_style_issues(repo_path)
        
        if style_issues:
            for issue in style_issues[:5]:
                actions.append({
                    'item': issue.split(':')[0],
                    'type': 'style',
                    'status': 'warning',
                    'action': issue
                })
        
        # Create docs directory for reports
        docs_dir = repo_path / 'docs'
        docs_dir.mkdir(exist_ok=True)
        
        self.log(f"Normalization check complete: {len(actions)} items reviewed")
        
        return self.create_result(
            status='success',
            summary=f"Normalization check complete: {len(actions)} items reviewed",
            data={
                'total_actions': len(actions),
                'pending': len([a for a in actions if a['status'] == 'pending']),
                'warnings': len([a for a in actions if a['status'] == 'warning']),
                'verified': len([a for a in actions if a['status'] == 'exists'])
            },
            findings=[f"{a['type']}: {a['item']} - {a['status']}" for a in actions]
        )
    
    def _check_style_issues(self, repo_path: Path) -> List[str]:
        """Check for basic code style issues."""
        style_issues = []
        for py_file in repo_path.rglob('*.py'):
            if '__pycache__' in str(py_file) or 'venv' in str(py_file):
                continue
            try:
                content = py_file.read_text()
                if '\t' in content:
                    style_issues.append(f"{py_file.name}: tabs instead of spaces")
                if content and not content.endswith('\n'):
                    style_issues.append(f"{py_file.name}: missing newline at end")
            except Exception:
                pass
        return style_issues
