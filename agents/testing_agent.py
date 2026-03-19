#!/usr/bin/env python3
"""
Testing Agent - Runs tests and CI/CD operations.
Mapped to: test command -> cicd_mcp

Now actually runs pytest/jest instead of simulating results.
"""
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .base_agent import BaseAgent


class TestingAgent(BaseAgent):
    """Agent that runs tests using the project's actual test framework."""

    def __init__(self):
        super().__init__(
            name="testing_agent",
            description="Runs pytest/jest/go test and reports real results"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        self.log(f"Running tests in {repo_path.absolute()}...")

        framework = self._detect_framework(repo_path)
        self.log(f"Detected framework: {framework}")

        # Run the actual test suite
        if framework == 'pytest':
            run_result = self._run_pytest(repo_path)
        elif framework in ('jest', 'mocha', 'vitest'):
            run_result = self._run_npm_test(repo_path, framework)
        elif framework == 'go test':
            run_result = self._run_go_test(repo_path)
        else:
            run_result = self._run_pytest(repo_path)  # best-effort default

        # Detect CI configs
        ci_systems = self._detect_ci_configs(repo_path)

        # Count test files
        test_files = self._find_test_files(repo_path, framework)

        status = 'success' if run_result['failed'] == 0 and run_result['errors'] == 0 else 'warning'
        summary = (
            f"{framework}: {run_result['passed']} passed, "
            f"{run_result['failed']} failed, "
            f"{run_result['errors']} errors "
            f"in {run_result.get('duration', '?')}s"
        )

        self.log(summary)

        return self.create_result(
            status=status,
            summary=summary,
            data={
                'framework': framework,
                'test_files_found': len(test_files),
                'passed': run_result['passed'],
                'failed': run_result['failed'],
                'errors': run_result['errors'],
                'duration': run_result.get('duration', 0),
                'coverage': run_result.get('coverage'),
                'output': run_result.get('output', '')[:2000],
                'ci_systems': ci_systems,
                'ran_successfully': run_result.get('ran', False),
            },
            findings=self._build_findings(run_result, framework, ci_systems, test_files)
        )

    # ── Framework detection ────────────────────────────────────────────────────

    def _detect_framework(self, repo_path: Path) -> str:
        # Go
        if list(repo_path.rglob('*_test.go')):
            return 'go test'
        # Node
        pkg = repo_path / 'package.json'
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                if 'vitest' in deps:
                    return 'vitest'
                if 'jest' in deps:
                    return 'jest'
                if 'mocha' in deps:
                    return 'mocha'
            except Exception:
                pass
        # Python — check for pytest config
        for marker in ['pytest.ini', 'pyproject.toml', 'setup.cfg', 'tox.ini']:
            if (repo_path / marker).exists():
                return 'pytest'
        # Fallback: test files present
        if list(repo_path.rglob('test_*.py')) or list(repo_path.rglob('*_test.py')):
            return 'pytest'
        return 'pytest'

    # ── Runners ────────────────────────────────────────────────────────────────

    def _run_pytest(self, repo_path: Path) -> Dict:
        """Run pytest with JSON output for reliable parsing."""
        try:
            result = subprocess.run(
                ['python3', '-m', 'pytest', '--tb=no', '-q',
                 '--json-report', '--json-report-file=/dev/stdout',
                 '--no-header'],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=120
            )
            # Try JSON report parse first
            parsed = self._parse_pytest_json(result.stdout)
            if parsed:
                return parsed

            # Fallback: parse plain text output
            return self._parse_pytest_text(result.stdout + result.stderr, result.returncode)

        except subprocess.TimeoutExpired:
            return {'passed': 0, 'failed': 0, 'errors': 1, 'ran': False,
                    'output': 'Test run timed out after 120 seconds'}
        except FileNotFoundError:
            return {'passed': 0, 'failed': 0, 'errors': 0, 'ran': False,
                    'output': 'pytest not found — install with: pip install pytest'}

    def _parse_pytest_json(self, stdout: str) -> Optional[Dict]:
        """Parse pytest-json-report output."""
        for line in stdout.split('\n'):
            line = line.strip()
            if line.startswith('{') and '"summary"' in line:
                try:
                    data = json.loads(line)
                    s = data.get('summary', {})
                    return {
                        'passed': s.get('passed', 0),
                        'failed': s.get('failed', 0),
                        'errors': s.get('error', 0),
                        'duration': round(data.get('duration', 0), 2),
                        'coverage': None,
                        'ran': True,
                        'output': '',
                    }
                except Exception:
                    pass
        return None

    def _parse_pytest_text(self, output: str, returncode: int) -> Dict:
        """Parse plain pytest text output."""
        passed = failed = errors = 0
        duration = 0.0

        # Pattern: "5 passed, 2 failed, 1 error in 3.14s"
        m = re.search(r'(\d+) passed', output)
        if m:
            passed = int(m.group(1))
        m = re.search(r'(\d+) failed', output)
        if m:
            failed = int(m.group(1))
        m = re.search(r'(\d+) error', output)
        if m:
            errors = int(m.group(1))
        m = re.search(r'in ([\d.]+)s', output)
        if m:
            duration = float(m.group(1))

        # Coverage
        coverage = None
        m = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', output)
        if m:
            coverage = int(m.group(1))

        return {
            'passed': passed, 'failed': failed, 'errors': errors,
            'duration': duration, 'coverage': coverage,
            'ran': True, 'output': output[-1500:],
        }

    def _run_npm_test(self, repo_path: Path, framework: str) -> Dict:
        """Run npm test and parse output."""
        try:
            result = subprocess.run(
                ['npm', 'test', '--', '--json'] if framework == 'jest' else ['npm', 'test'],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=120,
                env={**__import__('os').environ, 'CI': 'true'}
            )
            output = result.stdout + result.stderr

            passed = failed = errors = 0
            # Jest JSON output
            try:
                for line in output.split('\n'):
                    if '"numPassedTests"' in line or '"testResults"' in line:
                        data = json.loads(line)
                        return {
                            'passed': data.get('numPassedTests', 0),
                            'failed': data.get('numFailedTests', 0),
                            'errors': 0,
                            'duration': round(data.get('testResults', [{}])[0].get('perfStats', {}).get('runtime', 0) / 1000, 2),
                            'ran': True, 'coverage': None, 'output': output[-1000:],
                        }
            except Exception:
                pass

            # Fallback: parse text
            m = re.search(r'Tests:\s+(\d+) passed', output)
            if m:
                passed = int(m.group(1))
            m = re.search(r'(\d+) failed', output)
            if m:
                failed = int(m.group(1))

            return {'passed': passed, 'failed': failed, 'errors': errors,
                    'ran': True, 'duration': 0, 'coverage': None, 'output': output[-1500:]}

        except FileNotFoundError:
            return {'passed': 0, 'failed': 0, 'errors': 0, 'ran': False,
                    'output': 'npm not found'}
        except subprocess.TimeoutExpired:
            return {'passed': 0, 'failed': 0, 'errors': 1, 'ran': False,
                    'output': 'Test run timed out'}

    def _run_go_test(self, repo_path: Path) -> Dict:
        """Run go test ./..."""
        try:
            result = subprocess.run(
                ['go', 'test', '-v', '-json', './...'],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=120
            )
            passed = failed = 0
            for line in result.stdout.split('\n'):
                try:
                    event = json.loads(line)
                    if event.get('Action') == 'pass' and 'Test' in event:
                        passed += 1
                    elif event.get('Action') == 'fail' and 'Test' in event:
                        failed += 1
                except Exception:
                    pass
            return {'passed': passed, 'failed': failed, 'errors': 0,
                    'ran': True, 'duration': 0, 'coverage': None,
                    'output': result.stdout[-1000:]}
        except FileNotFoundError:
            return {'passed': 0, 'failed': 0, 'errors': 0, 'ran': False,
                    'output': 'go not found'}
        except subprocess.TimeoutExpired:
            return {'passed': 0, 'failed': 0, 'errors': 1, 'ran': False,
                    'output': 'go test timed out'}

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _find_test_files(self, repo_path: Path, framework: str) -> List[Path]:
        patterns = ['test_*.py', '*_test.py', '*.test.js', '*.spec.js',
                    '*.test.ts', '*.spec.ts', '*_test.go']
        files = []
        for p in patterns:
            files.extend(f for f in repo_path.rglob(p)
                         if '__pycache__' not in str(f) and 'node_modules' not in str(f))
        return files

    def _detect_ci_configs(self, repo_path: Path) -> List[str]:
        detected = []
        for ci in ['.github/workflows', '.gitlab-ci.yml', 'Jenkinsfile',
                   '.circleci/config.yml', 'azure-pipelines.yml', 'bitbucket-pipelines.yml']:
            if (repo_path / ci).exists():
                detected.append(ci)
        return detected

    def _build_findings(self, run_result: Dict, framework: str,
                        ci_systems: List[str], test_files: List[Path]) -> List[str]:
        findings = [
            f"Framework: {framework}",
            f"Test files found: {len(test_files)}",
            f"Passed: {run_result['passed']}",
        ]
        if run_result['failed']:
            findings.append(f"FAILED: {run_result['failed']} tests failed")
        if run_result['errors']:
            findings.append(f"ERRORS: {run_result['errors']} errors during collection")
        if run_result.get('coverage') is not None:
            findings.append(f"Coverage: {run_result['coverage']}%")
        if not run_result.get('ran'):
            findings.append(f"WARNING: Could not run tests — {run_result.get('output', '')[:100]}")
        findings.append(f"CI systems: {', '.join(ci_systems) if ci_systems else 'none detected'}")
        return findings
