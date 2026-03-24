#!/usr/bin/env python3
"""
Normalization Agent - Standardizes repository structure.
Mapped to: normalize command -> normalize_mcp

Reads .forgeflow/inventory.json (written by DiscoveryAgent) to make
language-aware decisions about README content, directory layout,
pre-commit hooks, and style fixes.
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent


# ---------------------------------------------------------------------------
# .gitignore templates per language (base + extras merged at runtime)
# ---------------------------------------------------------------------------
GITIGNORE_BASE = """\
# OS
.DS_Store
Thumbs.db
desktop.ini

# Editors
.vscode/
.idea/
*.swp
*.swo
*~

# Environment / secrets
.env
.env.local
.env.*.local
*.env

# ForgeFlow
staging/
.forgeflow/
"""

GITIGNORE_EXTRAS = {
    'Python': """\
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
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/
.ruff_cache/
""",
    'JavaScript': """\
# Node
node_modules/
dist/
build/
.next/
.nuxt/
.cache/
.parcel-cache/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
coverage/
.nyc_output/
""",
    'TypeScript': """\
# Node / TypeScript
node_modules/
dist/
build/
.next/
.nuxt/
.cache/
coverage/
*.js.map
*.d.ts
""",
    'Go': """\
# Go
*.exe
*.exe~
*.dll
*.so
*.dylib
*.test
*.out
vendor/
""",
    'Rust': """\
# Rust
target/
Cargo.lock
**/*.rs.bk
""",
    'Java': """\
# Java / Maven / Gradle
target/
*.class
*.jar
*.war
*.ear
.gradle/
build/
""",
    'Ruby': """\
# Ruby
*.gem
*.rbc
.bundle/
vendor/bundle/
""",
}

# ---------------------------------------------------------------------------
# README templates per language (filled at runtime)
# ---------------------------------------------------------------------------
README_TEMPLATES = {
    'Python': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
    'JavaScript': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Install dependencies
npm install

# Run the application
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
    'TypeScript': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Install dependencies
npm install

# Run the application
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
    'Go': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Build
go build ./...

# Run
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
    'Rust': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
# Build
cargo build --release

# Run
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
    'default': """\
# {project_name}

> Add a short description of your project here.

## Getting Started

```bash
{run_command}
```

## Project Structure

```
{project_name}/
{structure}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes and open a Pull Request

## License

MIT
""",
}

# ---------------------------------------------------------------------------
# Pre-commit configs per language
# ---------------------------------------------------------------------------
PRE_COMMIT_TEMPLATES = {
    'Python': """\
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
""",
    'JavaScript': """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.1.0
    hooks:
      - id: prettier
        types_or: [javascript, jsx, ts, tsx, json, yaml, markdown]

  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.56.0
    hooks:
      - id: eslint
        files: \\.[jt]sx?$
""",
    'TypeScript': """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-json
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.1.0
    hooks:
      - id: prettier
        types_or: [javascript, jsx, ts, tsx, json, yaml, markdown]
""",
    'Go': """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/dnephin/pre-commit-golang
    rev: v0.5.1
    hooks:
      - id: go-fmt
      - id: go-vet
      - id: go-imports
      - id: go-cyclo
        args: [-over=15]
""",
    'Rust': """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key

  - repo: https://github.com/doublify/pre-commit-rust
    rev: v1.0
    hooks:
      - id: fmt
      - id: cargo-check
      - id: clippy
""",
    'default': """\
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
""",
}

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

# Language → idiomatic directory layout
LANGUAGE_DIRS = {
    'Python':     ['src', 'tests', 'docs', 'config'],
    'JavaScript': ['src', 'tests', 'docs', 'public'],
    'TypeScript': ['src', 'tests', 'docs', 'public'],
    'Go':         ['cmd', 'internal', 'pkg', 'docs'],
    'Rust':       ['src', 'tests', 'docs'],
    'Java':       ['src/main/java', 'src/test/java', 'docs'],
    'Ruby':       ['lib', 'spec', 'docs', 'config'],
    'default':    ['src', 'tests', 'docs'],
}

# Language → source file extensions for style fixes
STYLE_FIX_EXTENSIONS = {
    'Python':     ['.py'],
    'JavaScript': ['.js', '.jsx', '.mjs', '.cjs'],
    'TypeScript': ['.ts', '.tsx'],
    'Go':         ['.go'],
    'Rust':       ['.rs'],
    'Ruby':       ['.rb'],
    'default':    ['.py'],
}

# Language → default run command
DEFAULT_RUN_COMMANDS = {
    'Python':     'python main.py',
    'JavaScript': 'node index.js',
    'TypeScript': 'npx ts-node src/index.ts',
    'Go':         'go run ./cmd/...',
    'Rust':       'cargo run',
    'Ruby':       'ruby app.rb',
    'default':    '# see project docs',
}


class NormalizationAgent(BaseAgent):
    """Agent that normalizes repository structure — language-aware, inventory-driven."""

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

        # Load DiscoveryAgent inventory if available
        inventory = self._load_inventory(repo_path)
        primary_language = inventory.get('summary', {}).get('primary_language', 'Python')
        entry_points = inventory.get('summary', {}).get('entry_points', [])
        existing_dirs = list(inventory.get('summary', {}).get('components', {}).keys())

        self.log(f"Primary language: {primary_language}")

        # 1. .gitignore — merged, language-aware
        gitignore_content = GITIGNORE_BASE
        extra = GITIGNORE_EXTRAS.get(primary_language, '')
        if extra:
            gitignore_content += '\n' + extra
        actions.extend(self._ensure_file(
            repo_path / '.gitignore', gitignore_content, dry_run, merge=True
        ))

        # 2. README.md — only if missing, language-aware with real entry point
        run_cmd = self._pick_run_command(primary_language, entry_points)
        structure = self._build_structure_snippet(repo_path, primary_language)
        readme_template = README_TEMPLATES.get(primary_language, README_TEMPLATES['default'])
        readme_content = readme_template.format(
            project_name=project_name,
            run_command=run_cmd,
            structure=structure,
        )
        actions.extend(self._ensure_file(
            repo_path / 'README.md', readme_content, dry_run, only_if_missing=True
        ))

        # 3. .editorconfig — only if missing
        actions.extend(self._ensure_file(
            repo_path / '.editorconfig', EDITORCONFIG_TEMPLATE, dry_run, only_if_missing=True
        ))

        # 4. .pre-commit-config.yaml — language-aware, only if missing
        pre_commit = PRE_COMMIT_TEMPLATES.get(primary_language, PRE_COMMIT_TEMPLATES['default'])
        actions.extend(self._ensure_file(
            repo_path / '.pre-commit-config.yaml', pre_commit, dry_run, only_if_missing=True
        ))

        # 5. Standard directories — language-aware, skip if already present
        target_dirs = LANGUAGE_DIRS.get(primary_language, LANGUAGE_DIRS['default'])
        for dirname in target_dirs:
            dir_path = repo_path / dirname
            if not dir_path.exists():
                if not dry_run:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    (dir_path / '.gitkeep').touch()
                actions.append({
                    'item': f'{dirname}/',
                    'status': 'created' if not dry_run else 'would_create',
                    'action': f'Created {dirname}/ directory'
                })
            else:
                actions.append({
                    'item': f'{dirname}/',
                    'status': 'exists',
                    'action': f'{dirname}/ already exists'
                })

        # 6. Fix code style issues (language-aware)
        actions.extend(self._fix_style_issues(repo_path, primary_language, dry_run))

        # 7. Ensure staging/ is gitignored (separate check since it's ForgeFlow-specific)
        actions.extend(self._ensure_staging_ignored(repo_path, dry_run))

        created = len([a for a in actions if a['status'] in ('created', 'would_create')])
        fixed   = len([a for a in actions if a['status'] in ('fixed', 'would_fix')])
        skipped = len([a for a in actions if a['status'] == 'exists'])

        summary = (
            f"Normalization complete [{primary_language}]: "
            f"{created} created, {fixed} fixed, {skipped} already correct"
        )
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
                'primary_language': primary_language,
                'entry_point_used': run_cmd,
            },
            findings=[f"{a['status'].upper()}: {a['item']} — {a['action']}" for a in actions]
        )

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _load_inventory(self, repo_path: Path) -> Dict[str, Any]:
        """Load DiscoveryAgent's inventory.json if it exists."""
        inventory_path = repo_path / '.forgeflow' / 'inventory.json'
        if inventory_path.exists():
            try:
                with open(inventory_path) as f:
                    data = json.load(f)
                self.log("Loaded .forgeflow/inventory.json")
                return data
            except Exception as e:
                self.log(f"Could not read inventory.json: {e}", level="warning")
        else:
            self.log("No inventory.json found — run discover first for better results", level="warning")
        return {}

    def _pick_run_command(self, language: str, entry_points: List[str]) -> str:
        """Pick the best run command using detected entry points."""
        if entry_points:
            ep = entry_points[0]
            if language == 'Python':
                return f'python {ep}'
            elif language in ('JavaScript', 'TypeScript'):
                return f'node {ep}'
            elif language == 'Go':
                return f'go run {ep}'
            elif language == 'Rust':
                return 'cargo run'
        return DEFAULT_RUN_COMMANDS.get(language, DEFAULT_RUN_COMMANDS['default'])

    def _build_structure_snippet(self, repo_path: Path, language: str) -> str:
        """Build a structure snippet from actual top-level dirs/files."""
        lines = []
        try:
            entries = sorted(repo_path.iterdir(), key=lambda p: (p.is_file(), p.name))
            for entry in entries[:12]:
                if entry.name.startswith('.') and entry.name not in ('.github',):
                    continue
                if entry.name in ('node_modules', '__pycache__', 'venv', '.venv'):
                    continue
                suffix = '/' if entry.is_dir() else ''
                lines.append(f'├── {entry.name}{suffix}')
        except Exception:
            pass
        return '\n'.join(lines) if lines else '├── src/'

    def _ensure_file(self, path: Path, content: str, dry_run: bool,
                     only_if_missing: bool = False, merge: bool = False) -> List[Dict]:
        name = path.name
        if not path.exists():
            if not dry_run:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            return [{'item': name,
                     'status': 'created' if not dry_run else 'would_create',
                     'action': f'Created missing {name}'}]

        if only_if_missing:
            return [{'item': name, 'status': 'exists', 'action': f'{name} already exists'}]

        if merge:
            # Proper line-by-line comparison — no substring false positives
            existing_lines = set(path.read_text().splitlines())
            new_lines = [
                ln for ln in content.splitlines()
                if ln.strip() and not ln.startswith('#') and ln not in existing_lines
            ]
            if new_lines:
                if not dry_run:
                    with path.open('a') as f:
                        f.write('\n# Added by ForgeFlow normalize\n')
                        f.write('\n'.join(new_lines) + '\n')
                return [{'item': name,
                         'status': 'fixed' if not dry_run else 'would_fix',
                         'action': f'Added {len(new_lines)} missing entries to {name}'}]

        return [{'item': name, 'status': 'exists', 'action': f'{name} already exists'}]

    def _fix_style_issues(self, repo_path: Path, language: str, dry_run: bool) -> List[Dict]:
        """Fix whitespace/encoding issues in source files for the detected language."""
        actions = []
        skip = {'__pycache__', 'venv', '.venv', 'node_modules', '.git', 'dist', 'build', 'target'}
        extensions = STYLE_FIX_EXTENSIONS.get(language, STYLE_FIX_EXTENSIONS['default'])

        for ext in extensions:
            for src_file in repo_path.rglob(f'*{ext}'):
                if any(s in src_file.parts for s in skip):
                    continue
                try:
                    original = src_file.read_text(errors='ignore')
                    fixed = original

                    # Fix tabs → 4 spaces (Python/Ruby) or 2 spaces (JS/TS/Go)
                    tab_replacement = '  ' if language in ('JavaScript', 'TypeScript', 'Go') else '    '
                    if '\t' in fixed:
                        fixed = fixed.replace('\t', tab_replacement)

                    # Fix Windows line endings
                    if '\r\n' in fixed:
                        fixed = fixed.replace('\r\n', '\n')

                    # Fix missing newline at end of file
                    if fixed and not fixed.endswith('\n'):
                        fixed += '\n'

                    if fixed != original:
                        rel = str(src_file.relative_to(repo_path))
                        if not dry_run:
                            src_file.write_text(fixed)
                        actions.append({
                            'item': rel,
                            'status': 'fixed' if not dry_run else 'would_fix',
                            'action': 'Fixed formatting (tabs, trailing newline, line endings)'
                        })
                except Exception:
                    pass
        return actions

    def _ensure_staging_ignored(self, repo_path: Path, dry_run: bool) -> List[Dict]:
        gitignore = repo_path / '.gitignore'
        if not gitignore.exists():
            return []
        existing_lines = set(gitignore.read_text().splitlines())
        if 'staging/' not in existing_lines:
            if not dry_run:
                with gitignore.open('a') as f:
                    f.write('\n# ForgeFlow auto-generated reports\nstaging/\n')
            return [{'item': '.gitignore',
                     'status': 'fixed' if not dry_run else 'would_fix',
                     'action': 'Added staging/ to .gitignore'}]
        return [{'item': '.gitignore', 'status': 'exists',
                 'action': 'staging/ already in .gitignore'}]
