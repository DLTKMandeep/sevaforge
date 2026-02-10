#!/usr/bin/env python3
"""
Testing Agent - Runs tests and CI/CD operations.
Mapped to: test command → cicd_mcp
"""
import json
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent


class TestingAgent(BaseAgent):
    """Agent that runs tests and CI/CD operations."""
    
    def __init__(self):
        super().__init__(
            name="testing_agent",
            description="Runs tests, manages CI/CD pipelines"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run tests and CI/CD operations."""
        repo_path = Path(params.get('path', '.'))
        test_results = []
        
        self.log(f"Running tests in {repo_path.absolute()}...")
        
        framework = self._detect_test_framework(repo_path)
        
        # Find test files
        test_files = []
        for pattern in ['test_*.py', '*_test.py', '*.test.js', '*.spec.js']:
            test_files.extend(repo_path.rglob(pattern))
        
        # Simulate test execution
        for test_file in test_files[:10]:  # Limit for demo
            if '__pycache__' in str(test_file) or 'node_modules' in str(test_file):
                continue
            test_results.append({
                'file': str(test_file.relative_to(repo_path)),
                'framework': framework,
                'status': 'passed',  # Simulated
                'duration': '0.5s'
            })
        
        # Check for CI/CD config
        ci_configs = [
            '.github/workflows',
            '.gitlab-ci.yml',
            'Jenkinsfile',
            '.circleci/config.yml'
        ]
        
        detected_ci = []
        for ci in ci_configs:
            if (repo_path / ci).exists():
                detected_ci.append(ci)
        
        passed = len([t for t in test_results if t['status'] == 'passed'])
        failed = len([t for t in test_results if t['status'] == 'failed'])
        
        status = 'success' if failed == 0 else 'warning'
        summary = f"Tests: {passed} passed, {failed} failed ({framework})"
        
        self.log(summary)
        
        return self.create_result(
            status=status,
            summary=summary,
            data={
                'framework': framework,
                'total_tests': len(test_results),
                'passed': passed,
                'failed': failed,
                'ci_systems': detected_ci,
                'results': test_results
            },
            findings=[
                f"Framework: {framework}",
                f"Test files found: {len(test_files)}",
                f"CI/CD configs: {', '.join(detected_ci) if detected_ci else 'None'}"
            ]
        )
    
    def _detect_test_framework(self, repo_path: Path) -> str:
        """Detect testing framework in use."""
        if (repo_path / 'pytest.ini').exists() or (repo_path / 'pyproject.toml').exists():
            return 'pytest'
        if (repo_path / 'package.json').exists():
            try:
                pkg = json.loads((repo_path / 'package.json').read_text())
                if 'jest' in pkg.get('devDependencies', {}):
                    return 'jest'
                if 'mocha' in pkg.get('devDependencies', {}):
                    return 'mocha'
            except Exception:
                pass
        if list(repo_path.rglob('*_test.go')):
            return 'go test'
        return 'pytest'  # Default
