#!/usr/bin/env python3
"""
Normalization Agent - Standardizes repository structure.
Mapped to: normalize command -> normalize_mcp

Now actually creates missing files and fixes issues instead of just reporting them.
"""
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent


GITIGNORE_TEMPLATE = """\
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
env/
ENV/
*.egg-info/
dist/
build/
.eggs/
pip-wheel-metadata/

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/
.ruff_cache/

# Environment
.env
.env.local
.env.production
*.env

# IDEs
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Outputs
staging/
*.log
"""

README_TEMPLATE = """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Project Structure

```
{project_name}/
├── src/          # Source code
├── tests/        # Test suite
├── docs/         # Documentation
└── config/       # Configuration files
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a Pull Request

## License

MIT
"""

PRE_COMMIT_TEMPLATE = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
        language_version: python3

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=120]
"""

EDITORCONFIG_TEMPLATE = """\
root = true

[*]
indent_style = space
indent_size = 4
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.{json,yaml,yml,toml}]
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
"""


class NormalizationAgent(BaseAgent):
    """Agent that normalizes repository structure — actually creates and fixes files."""

    def __init__(self):
        super().__init__(
            name="normalization_agent",
            description="Standardizes repo structure: creates missing files, fixes formatting issues"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        dry_run = params.get('dry_run', False)
        actions = []

        self.log(f"Normalizing {repo_path.absolute()} (dry_run={dry_run})...")

        project_name = repo_path.name

        # 1. Standard files
        actions.extend(self._ensure_file(
            repo_path / '.gitignore', GITIGNORE_TEMPLATE, dry_run,
            merge=True  # Append missing entries rather than overwrite
        ))
        actions.extend(self._ensure_file(
            repo_path / 'README.md',
            README_TEMPLATE.format(project_name=project_name),
            dry_run, only_if_missing=True
        ))
        actions.extend(self._ensure_file(
            repo_path / '.editorconfig', EDITORCONFIG_TEMPLATE, dry_run, only_if_missing=True
        ))
        actions.extend(self._ensure_file(
            repo_path / '.pre-commit-config.yaml', PRE_COMMIT_TEMPLATE, dry_run, only_if_missing=True
        ))

        # 2. Standard directories
        for dirname in ['src', 'tests', 'docs', 'config']:
            dir_path = repo_path / dirname
            if not dir_path.exists():
                if not dry_run:
                    dir_path.mkdir(exist_ok=True)
                    # Add placeholder so git tracks it
                    (dir_path / '.gitkeep').touch()
                actions.append({'item': f'{dirname}/', 'status': 'created' if not dry_run else 'would_create',
                                 'action': f'Created {dirname}/ directory'})
            else:
                actions.append({'item': f'{dirname}/', 'status': 'exists', 'action': f'{dirname}/ already exists'})

        # 3. Fix code style issues in Python files
        style_actions = self._fix_style_issues(repo_path, dry_run)
        actions.extend(style_actions)

        # 4. Ensure staging/ is gitignored
        actions.extend(self._ensure_staging_ignored(repo_path, dry_run))

        created = len([a for a in actions if 'created' in a['status']])
        fixed = len([a for a in actions if 'fixed' in a['status']])
        skipped = len([a for a in actions if a['status'] == 'exists'])

        summary = f"Normalization complete: {created} created, {fixed} fixed, {skipped} already correct"
        self.log(summary)

        return self.create_result(
            status='success',
            summary=summary,
            data={
                'total_actions': len(actions),
                'created': created,
                'fixed': fixed,
                'skipped': skipped,
                'dry_run': dry_run,
            },
            findings=[f"{a['status'].upper()}: {a['item']} - {a['action']}" for a in actions]
        )

    def _ensure_file(self, path: Path, content: str, dry_run: bool,
                     only_if_missing: bool = False, merge: bool = False) -> List[Dict]:
        name = path.name
        if not path.exists():
            if not dry_run:
                path.write_text(content)
            return [{'item': name, 'status': 'created' if not dry_run else 'would_create',
                     'action': f'Created missing {name}'}]
        elif merge:
            # For .gitignore: add missing entries
            existing = path.read_text()
            missing_lines = [ln for ln in content.split('\n')
                             if ln.strip() and not ln.startswith('#') and ln not in existing]
            if missing_lines:
                if not dry_run:
                    with path.open('a') as f:
                        f.write('\n# Added by ForgeFlow normalize\n')
                        f.write('\n'.join(missing_lines) + '\n')
                return [{'item': name, 'status': 'fixed' if not dry_run else 'would_fix',
                         'action': f'Added {len(missing_lines)} missing entries to {name}'}]
        return [{'item': name, 'status': 'exists', 'action': f'{name} already exists'}]

    def _fix_style_issues(self, repo_path: Path, dry_run: bool) -> List[Dict]:
        actions = []
        skip = {'__pycache__', 'venv', '.venv', 'node_modules', '.git'}
        for py_file in repo_path.rglob('*.py'):
            if any(s in py_file.parts for s in skip):
                continue
            try:
                original = py_file.read_text()
                fixed = original

                # Fix tabs -> 4 spaces
                if '\t' in fixed:
                    fixed = fixed.replace('\t', '    ')

                # Fix missing newline at end
                if fixed and not fixed.endswith('\n'):
                    fixed += '\n'

                # Fix Windows line endings
                if '\r\n' in fixed:
                    fixed = fixed.replace('\r\n', '\n')

                if fixed != original:
                    rel = str(py_file.relative_to(repo_path))
                    if not dry_run:
                        py_file.write_text(fixed)
                    actions.append({'item': rel,
                                    'status': 'fixed' if not dry_run else 'would_fix',
                                    'action': 'Fixed formatting (tabs, trailing newline, line endings)'})
            except Exception:
                pass
        return actions

    def _ensure_staging_ignored(self, repo_path: Path, dry_run: bool) -> List[Dict]:
        gitignore = repo_path / '.gitignore'
        if not gitignore.exists():
            return []
        content = gitignore.read_text()
        if 'staging/' not in content:
            if not dry_run:
                with gitignore.open('a') as f:
                    f.write('\n# ForgeFlow auto-generated reports\nstaging/\n')
            return [{'item': '.gitignore', 'status': 'fixed' if not dry_run else 'would_fix',
                     'action': 'Added staging/ to .gitignore'}]
        return [{'item': '.gitignore', 'status': 'exists', 'action': 'staging/ already in .gitignore'}]
