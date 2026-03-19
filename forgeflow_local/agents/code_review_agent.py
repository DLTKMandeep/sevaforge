#!/usr/bin/env python3
"""
Code Review Agent - Performs code review and git analysis.
Mapped to: review command -> git_mcp

Stack:
- radon: cyclomatic complexity + maintainability index
- subprocess/git: commit history, blame, branch analysis
- AST: function length, class size analysis
- pylint/flake8: linting when available
"""
import ast
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from .base_agent import BaseAgent

# Thresholds
MAX_FUNCTION_LINES = 50
MAX_CLASS_LINES = 300
MAX_FILE_LINES = 500
MAX_CYCLOMATIC_COMPLEXITY = 10  # McCabe threshold
MAX_ARGS = 7


class CodeReviewAgent(BaseAgent):
    """Agent that performs real code quality analysis and git review."""

    def __init__(self):
        super().__init__(
            name="code_review_agent",
            description="Analyzes code quality with radon, AST analysis, and git history"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        self.log(f"Reviewing code in {repo_path.absolute()}...")

        findings = []

        # 1. Git analysis
        git_findings = self._analyze_git(repo_path)
        findings.extend(git_findings)

        # 2. Code complexity via radon (or AST fallback)
        complexity_findings, complexity_stats = self._analyze_complexity(repo_path)
        findings.extend(complexity_findings)

        # 3. AST-based structural analysis
        structural_findings, structural_stats = self._analyze_structure(repo_path)
        findings.extend(structural_findings)

        # 4. Code smell detection
        smell_findings = self._detect_code_smells(repo_path)
        findings.extend(smell_findings)

        # 5. Run pylint/flake8 if available
        lint_findings, lint_summary = self._run_linter(repo_path)
        findings.extend(lint_findings)

        # 6. Large file detection
        large_files = self._find_large_files(repo_path)
        if large_files:
            findings.append({
                'type': 'large-files', 'severity': 'warning',
                'message': f'{len(large_files)} files exceed {MAX_FILE_LINES} lines',
                'data': large_files[:10]
            })

        py_files = [f for f in repo_path.rglob('*.py')
                    if '__pycache__' not in str(f) and '.venv' not in str(f)]

        summary = (
            f"Reviewed {len(py_files)} Python files: "
            f"{complexity_stats.get('complex_functions', 0)} complex functions, "
            f"{structural_stats.get('long_functions', 0)} long functions, "
            f"{len(smell_findings)} code smells"
        )
        if lint_summary:
            summary += f", {lint_summary}"

        self.log(summary)

        return self.create_result(
            status='success',
            summary=summary,
            data={
                'files_reviewed': len(py_files),
                'complexity': complexity_stats,
                'structure': structural_stats,
                'linter': lint_summary or 'not available',
                'findings': findings,
            },
            findings=[f"[{f.get('severity', 'info').upper()}] {f['type']}: {f['message']}"
                      for f in findings[:20]]
        )

    # ── Git Analysis ───────────────────────────────────────────────────────────

    def _analyze_git(self, repo_path: Path) -> List[Dict]:
        findings = []
        if not (repo_path / '.git').exists():
            return [{'type': 'git', 'severity': 'info', 'message': 'Not a git repository'}]

        # Recent commits
        log = self._git(repo_path, ['log', '--oneline', '-20'])
        commits = [c for c in log.split('\n') if c]
        findings.append({'type': 'git-history', 'severity': 'info',
                         'message': f'{len(commits)} recent commits', 'data': commits[:10]})

        # Check commit message quality
        bad_messages = [c for c in commits if len(c.split(' ', 1)[-1]) < 10
                        or c.split(' ', 1)[-1].lower() in ('fix', 'update', 'wip', 'test', 'changes')]
        if bad_messages:
            findings.append({'type': 'commit-messages', 'severity': 'warning',
                             'message': f'{len(bad_messages)} low-quality commit messages',
                             'data': bad_messages[:5]})

        # Uncommitted changes
        status = self._git(repo_path, ['status', '--porcelain'])
        if status:
            changed = len([l for l in status.split('\n') if l.strip()])
            findings.append({'type': 'uncommitted', 'severity': 'warning',
                             'message': f'{changed} uncommitted changes'})

        # Branch info
        branch = self._git(repo_path, ['branch', '--show-current'])
        if branch:
            findings.append({'type': 'branch', 'severity': 'info',
                             'message': f'Current branch: {branch}'})

        # Hotspot files (most frequently changed)
        hotspot_raw = self._git(repo_path, ['log', '--name-only', '--pretty=format:', '-50'])
        if hotspot_raw:
            from collections import Counter
            file_changes = Counter(f for f in hotspot_raw.split('\n') if f.strip() and not f.startswith('commit'))
            hotspots = file_changes.most_common(5)
            if hotspots:
                findings.append({'type': 'hotspots', 'severity': 'info',
                                 'message': f'Top {len(hotspots)} frequently changed files',
                                 'data': [f'{f}: {c} changes' for f, c in hotspots]})

        return findings

    def _git(self, repo_path: Path, args: List[str]) -> str:
        try:
            r = subprocess.run(['git'] + args, cwd=str(repo_path),
                               capture_output=True, text=True, timeout=15)
            return r.stdout.strip()
        except Exception:
            return ''

    # ── Complexity Analysis ────────────────────────────────────────────────────

    def _analyze_complexity(self, repo_path: Path) -> Tuple[List[Dict], Dict]:
        """Use radon for cyclomatic complexity, fall back to AST counting."""
        findings = []
        stats = {'complex_functions': 0, 'avg_complexity': 0, 'tool': 'none'}
        skip = {'__pycache__', 'venv', '.venv', 'node_modules', '.git'}

        # Try radon first
        try:
            result = subprocess.run(
                ['python3', '-m', 'radon', 'cc', str(repo_path), '-s', '-j', '--min', 'C'],
                capture_output=True, text=True, timeout=30
            )
            if result.stdout and result.stdout.strip() != '{}':
                import json
                data = json.loads(result.stdout)
                stats['tool'] = 'radon'
                complex_funcs = []
                all_complexities = []
                for filepath, items in data.items():
                    for item in items:
                        cc = item.get('complexity', 0)
                        all_complexities.append(cc)
                        if cc > MAX_CYCLOMATIC_COMPLEXITY:
                            stats['complex_functions'] += 1
                            complex_funcs.append(
                                f"{filepath.replace(str(repo_path)+'/', '')}:"
                                f"{item.get('name', '?')} (complexity={cc})"
                            )
                if all_complexities:
                    stats['avg_complexity'] = round(sum(all_complexities) / len(all_complexities), 1)
                if complex_funcs:
                    findings.append({
                        'type': 'high-complexity', 'severity': 'warning',
                        'message': f'{len(complex_funcs)} functions exceed complexity threshold ({MAX_CYCLOMATIC_COMPLEXITY})',
                        'data': complex_funcs[:10]
                    })
                return findings, stats
        except Exception:
            pass

        # Fallback: count branches via AST
        for filepath in repo_path.rglob('*.py'):
            if any(s in filepath.parts for s in skip):
                continue
            try:
                tree = ast.parse(filepath.read_text(errors='ignore'))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        branches = sum(1 for n in ast.walk(node)
                                       if isinstance(n, (ast.If, ast.For, ast.While,
                                                         ast.Try, ast.ExceptHandler,
                                                         ast.With, ast.Assert)))
                        if branches > MAX_CYCLOMATIC_COMPLEXITY:
                            stats['complex_functions'] += 1
                            findings.append({
                                'type': 'high-complexity', 'severity': 'warning',
                                'message': f'{filepath.name}:{node.name} has ~{branches} branches'
                            })
            except Exception:
                pass
        stats['tool'] = 'ast-fallback'
        return findings, stats

    # ── Structural Analysis ────────────────────────────────────────────────────

    def _analyze_structure(self, repo_path: Path) -> Tuple[List[Dict], Dict]:
        findings = []
        stats = {'long_functions': 0, 'large_classes': 0, 'many_args': 0, 'missing_docstrings': 0}
        skip = {'__pycache__', 'venv', '.venv', 'node_modules', '.git'}

        for filepath in repo_path.rglob('*.py'):
            if any(s in filepath.parts for s in skip):
                continue
            try:
                source = filepath.read_text(errors='ignore')
                tree = ast.parse(source)
                lines = source.split('\n')
                rel = str(filepath.relative_to(repo_path))

                for node in ast.walk(tree):
                    # Long functions
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        end = getattr(node, 'end_lineno', node.lineno + 10)
                        length = end - node.lineno
                        if length > MAX_FUNCTION_LINES:
                            stats['long_functions'] += 1
                            findings.append({
                                'type': 'long-function', 'severity': 'warning',
                                'message': f'{rel}:{node.name} is {length} lines (limit: {MAX_FUNCTION_LINES})'
                            })

                        # Too many arguments
                        arg_count = len(node.args.args)
                        if arg_count > MAX_ARGS:
                            stats['many_args'] += 1
                            findings.append({
                                'type': 'too-many-args', 'severity': 'info',
                                'message': f'{rel}:{node.name} has {arg_count} arguments (limit: {MAX_ARGS})'
                            })

                        # Missing docstring
                        if not (node.body and isinstance(node.body[0], ast.Expr)
                                and isinstance(node.body[0].value, ast.Constant)):
                            if node.name not in ('__init__', '__str__', '__repr__'):
                                stats['missing_docstrings'] += 1

                    # Large classes
                    if isinstance(node, ast.ClassDef):
                        end = getattr(node, 'end_lineno', node.lineno + 10)
                        length = end - node.lineno
                        if length > MAX_CLASS_LINES:
                            stats['large_classes'] += 1
                            findings.append({
                                'type': 'large-class', 'severity': 'warning',
                                'message': f'{rel}:{node.name} is {length} lines (limit: {MAX_CLASS_LINES})'
                            })

            except SyntaxError as e:
                findings.append({'type': 'syntax-error', 'severity': 'error',
                                  'message': f'{rel}: {e}'})
            except Exception:
                pass

        if stats['missing_docstrings'] > 5:
            findings.append({'type': 'missing-docstrings', 'severity': 'info',
                             'message': f'{stats["missing_docstrings"]} functions missing docstrings'})

        return findings, stats

    # ── Code Smells ────────────────────────────────────────────────────────────

    def _detect_code_smells(self, repo_path: Path) -> List[Dict]:
        findings = []
        skip = {'__pycache__', 'venv', '.venv', 'node_modules', '.git'}
        smells = {
            'bare-except': (r'except\s*:', 'info', 'Bare except clause (catches all exceptions)'),
            'mutable-default': (r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|\(\))', 'warning', 'Mutable default argument'),
            'print-debug': (r'^\s*print\s*\(', 'info', 'print() statement (use logging)'),
            'magic-number': (r'(?<!\w)(?<!\.)\d{4,}(?!\w)(?!\.)', 'info', 'Magic number (consider named constant)'),
            'todo-fixme': (r'#\s*(TODO|FIXME|HACK|XXX)', 'info', 'TODO/FIXME comment'),
            'pass-in-except': (r'except.*:\s*\n\s*pass', 'warning', 'Silenced exception with pass'),
        }

        smell_counts = {k: 0 for k in smells}
        for filepath in repo_path.rglob('*.py'):
            if any(s in filepath.parts for s in skip):
                continue
            try:
                content = filepath.read_text(errors='ignore')
                for smell_type, (pattern, severity, description) in smells.items():
                    matches = re.findall(pattern, content, re.MULTILINE)
                    smell_counts[smell_type] += len(matches)
            except Exception:
                pass

        for smell_type, count in smell_counts.items():
            if count > 0:
                _, severity, description = smells[smell_type]
                findings.append({'type': smell_type, 'severity': severity,
                                  'message': f'{count} instances: {description}'})

        return findings

    # ── Linting ────────────────────────────────────────────────────────────────

    def _run_linter(self, repo_path: Path) -> Tuple[List[Dict], Optional[str]]:
        findings = []
        # Try flake8
        try:
            result = subprocess.run(
                ['python3', '-m', 'flake8', str(repo_path),
                 '--max-line-length=120', '--count', '--statistics',
                 '--exclude=.venv,venv,__pycache__,node_modules'],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout + result.stderr
            # Count errors by code
            error_codes = re.findall(r'\b(E\d+|W\d+)\b', output)
            from collections import Counter
            top = Counter(error_codes).most_common(5)
            total = len(error_codes)
            if total > 0:
                findings.append({'type': 'flake8', 'severity': 'warning',
                                  'message': f'{total} flake8 issues: {", ".join(f"{c}×{n}" for c,n in top)}'})
                return findings, f'flake8: {total} issues'
            return findings, 'flake8: clean'
        except Exception:
            pass

        return findings, None

    # ── Large Files ────────────────────────────────────────────────────────────

    def _find_large_files(self, repo_path: Path) -> List[str]:
        large = []
        skip = {'__pycache__', '.git', 'node_modules', '.venv', 'venv'}
        for f in repo_path.rglob('*.py'):
            if any(s in f.parts for s in skip):
                continue
            try:
                lines = len(f.read_text(errors='ignore').split('\n'))
                if lines > MAX_FILE_LINES:
                    large.append(f'{str(f.relative_to(repo_path))}: {lines} lines')
            except Exception:
                pass
        return large
