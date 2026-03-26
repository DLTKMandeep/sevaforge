#!/usr/bin/env python3
"""
Security Agent - Scans for security vulnerabilities.
Mapped to: scan command -> security_mcp

Stack:
- bandit: Python AST-based SAST (when installed)
- Shannon entropy: high-entropy secret detection
- Pattern matching: known secret formats (AWS, GitHub, Stripe, etc.)
- pip-audit / safety: dependency CVE checks
"""
import re
import subprocess
import json
import math
import string
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent

SEVERITY_LEVELS = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
ENTROPY_THRESHOLD_B64 = 4.5
ENTROPY_THRESHOLD_HEX = 3.0
MIN_SECRET_LEN = 20

SECRET_PATTERNS = [
    (r'AKIA[0-9A-Z]{16}', 'critical', 'AWS Access Key ID'),
    (r'-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----', 'critical', 'Private key in source'),
    (r'ghp_[a-zA-Z0-9]{36}', 'critical', 'GitHub Personal Access Token'),
    (r'sk_live_[0-9a-zA-Z]{24,}', 'critical', 'Stripe Live Secret Key'),
    (r'(?i)(password|passwd|pwd)\s*=\s*["\'][^"\']{8,}["\']', 'high', 'Hardcoded password'),
    (r'(?i)(api[_-]?key|apikey)\s*=\s*["\'][a-zA-Z0-9_\-]{16,}["\']', 'high', 'Hardcoded API key'),
    (r'(?i)(secret[_-]?key)\s*=\s*["\'][^"\']{8,}["\']', 'high', 'Hardcoded secret key'),
    (r'(?i)(token)\s*=\s*["\'][a-zA-Z0-9_\-\.]{20,}["\']', 'high', 'Hardcoded token'),
    (r'xox[baprs]-[0-9a-zA-Z\-]{10,}', 'high', 'Slack Token'),
    (r'AIza[0-9A-Za-z\-_]{35}', 'high', 'Google API Key'),
]

CODE_PATTERNS = {
    'sql-injection': [
        (r'execute\s*\(\s*["\'].*%[sd]', 'high', 'SQL string formatting (% operator)'),
        (r'cursor\.execute\s*\(\s*[^,\)]+\s*\+', 'high', 'SQL string concatenation'),
        (r'f["\'].*SELECT.*\{.*\}', 'high', 'SQL in f-string'),
    ],
    'command-injection': [
        (r'os\.system\s*\([^)]*\+', 'high', 'os.system with string concatenation'),
        (r'subprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True', 'high', 'subprocess with shell=True'),
        (r'eval\s*\(\s*(input|request)', 'critical', 'eval() on user input'),
    ],
    'insecure-config': [
        (r'(?<!["\'])DEBUG\s*=\s*True', 'medium', 'Debug mode enabled'),
        (r'verify\s*=\s*False', 'medium', 'SSL verification disabled'),
        (r'ALLOWED_HOSTS\s*=\s*\[\s*["\'][*]["\']', 'high', 'Wildcard ALLOWED_HOSTS'),
    ],
    'insecure-deserialization': [
        (r'pickle\.loads?\s*\(', 'high', 'Unsafe pickle deserialization'),
        (r'yaml\.load\s*\([^,\)]+\)', 'medium', 'Unsafe yaml.load (use safe_load)'),
    ],
}


def _shannon_entropy(data: str, charset: str) -> float:
    if not data:
        return 0.0
    freq = {c: data.count(c) for c in set(data) if c in charset}
    n = len(data)
    return -sum((f / n) * math.log2(f / n) for f in freq.values() if f > 0)


class SecurityAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="security_agent",
            description="Scans for vulnerabilities using bandit, entropy analysis, and pattern matching"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        severity_threshold = params.get('severity_threshold', 'medium')
        threshold_level = SEVERITY_LEVELS.get(severity_threshold.lower(), 2)

        self.log(f"Scanning {repo_path.absolute()} (threshold: {severity_threshold})...")

        vulns = []
        vulns.extend(self._run_bandit(repo_path, threshold_level))
        vulns.extend(self._scan_secrets(repo_path, threshold_level))
        vulns.extend(self._scan_code_patterns(repo_path, threshold_level))
        vulns.extend(self._check_dependencies(repo_path))
        vulns.extend(self._scan_env_files(repo_path))

        # Deduplicate
        seen, unique = set(), []
        for v in vulns:
            key = (v.get('file', ''), v.get('line', 0), v.get('type', ''))
            if key not in seen:
                seen.add(key)
                unique.append(v)

        unique.sort(key=lambda x: SEVERITY_LEVELS.get(x['severity'], 0), reverse=True)

        by_severity = {}
        for v in unique:
            by_severity[v['severity']] = by_severity.get(v['severity'], 0) + 1

        status = 'success' if not unique else 'warning'
        summary = (
            f"Found {len(unique)} issues: "
            + ', '.join(f"{c} {s}" for s, c in sorted(by_severity.items(), key=lambda x: -SEVERITY_LEVELS.get(x[0], 0)))
        ) if unique else "No security issues found"

        self.log(summary)
        return self.create_result(
            status=status,
            summary=summary,
            data={
                'total': len(unique),
                'by_severity': by_severity,
                'threshold': severity_threshold,
                'scanners_used': self._available_scanners(),
                'vulnerabilities': unique[:50],
            },
            findings=[
                f"[{v['severity'].upper()}] {v.get('file','?')}:{v.get('line','?')} - {v['issue']}"
                for v in unique[:15]
            ]
        )

    def _run_bandit(self, repo_path: Path, threshold_level: int) -> List[Dict]:
        results = []
        try:
            result = subprocess.run(
                ['python3', '-m', 'bandit', '-r', str(repo_path), '-f', 'json', '-q',
                 '--exclude', '.venv,venv,node_modules,__pycache__'],
                capture_output=True, text=True, timeout=60
            )
            if result.stdout:
                data = json.loads(result.stdout)
                smap = {'LOW': 'low', 'MEDIUM': 'medium', 'HIGH': 'high'}
                for issue in data.get('results', []):
                    sev = smap.get(issue.get('issue_severity', 'LOW'), 'low')
                    if SEVERITY_LEVELS.get(sev, 0) >= threshold_level:
                        results.append({
                            'severity': sev,
                            'type': 'bandit-' + issue.get('test_id', 'unknown').lower(),
                            'file': issue.get('filename', '?').replace(str(repo_path) + '/', ''),
                            'line': issue.get('line_number', 0),
                            'issue': issue.get('issue_text', ''),
                            'snippet': issue.get('code', '').strip()[:80],
                            'source': 'bandit',
                        })
        except Exception:
            pass
        return results

    def _scan_secrets(self, repo_path: Path, threshold_level: int) -> List[Dict]:
        results = []
        skip = {'__pycache__', '.git', 'node_modules', '.venv', 'venv', 'dist', 'build'}
        exts = {'.py', '.js', '.ts', '.env', '.yaml', '.yml', '.json',
                '.toml', '.cfg', '.ini', '.sh', '.conf', '.properties'}
        b64_chars = string.ascii_letters + string.digits + '+/='

        for filepath in repo_path.rglob('*'):
            if filepath.is_dir() or any(s in filepath.parts for s in skip):
                continue
            if filepath.suffix not in exts and filepath.name not in {'.env', '.env.local', '.env.production'}:
                continue
            try:
                content = filepath.read_text(errors='ignore')
                rel = str(filepath.relative_to(repo_path))
                for line_num, line in enumerate(content.split('\n'), 1):
                    if line.strip().startswith(('#', '//')):
                        continue
                    for pattern, severity, description in SECRET_PATTERNS:
                        if SEVERITY_LEVELS.get(severity, 0) >= threshold_level and re.search(pattern, line):
                            results.append({'severity': severity, 'type': 'hardcoded-secret',
                                            'file': rel, 'line': line_num, 'issue': description,
                                            'snippet': line.strip()[:80], 'source': 'pattern'})
                # Entropy scan
                if threshold_level <= SEVERITY_LEVELS['high']:
                    for m in re.finditer(r'["\']([a-zA-Z0-9+/=_\-]{20,})["\']', content):
                        cand = m.group(1)
                        if len(cand) < MIN_SECRET_LEN or '/' in cand or '.' in cand:
                            continue
                        if _shannon_entropy(cand, b64_chars) > ENTROPY_THRESHOLD_B64:
                            results.append({'severity': 'high', 'type': 'high-entropy-secret',
                                            'file': rel, 'line': 0, 'source': 'entropy',
                                            'issue': f'High-entropy string (possible secret)',
                                            'snippet': cand[:40]})
            except Exception:
                pass
        return results

    def _scan_code_patterns(self, repo_path: Path, threshold_level: int) -> List[Dict]:
        results = []
        skip = {'__pycache__', '.git', 'node_modules', '.venv', 'venv'}
        for filepath in repo_path.rglob('*.py'):
            if any(s in filepath.parts for s in skip):
                continue
            try:
                lines = filepath.read_text(errors='ignore').split('\n')
                rel = str(filepath.relative_to(repo_path))
                for cat, patterns in CODE_PATTERNS.items():
                    for pattern, severity, desc in patterns:
                        if SEVERITY_LEVELS.get(severity, 0) < threshold_level:
                            continue
                        for ln, line in enumerate(lines, 1):
                            if re.search(pattern, line):
                                results.append({'severity': severity, 'type': cat, 'file': rel,
                                                'line': ln, 'issue': desc,
                                                'snippet': line.strip()[:80], 'source': 'pattern'})
            except Exception:
                pass
        return results

    def _check_dependencies(self, repo_path: Path) -> List[Dict]:
        results = []
        req = repo_path / 'requirements.txt'
        if not req.exists():
            return results
        for cmd in [
            ['python3', '-m', 'pip_audit', '--requirement', str(req), '-f', 'json'],
            ['safety', 'check', '-r', str(req), '--json'],
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if r.stdout:
                    data = json.loads(r.stdout)
                    entries = data if isinstance(data, list) else data.get('vulnerabilities', [])
                    for v in entries[:20]:
                        results.append({
                            'severity': 'high', 'type': 'dependency-cve',
                            'file': 'requirements.txt', 'line': 0, 'source': cmd[2],
                            'issue': (f"{v.get('name', v.get('package', '?'))} "
                                      f"{v.get('version', '?')} - "
                                      f"{v.get('id', v.get('vulnerability_id', 'CVE unknown'))}"),
                            'snippet': '',
                        })
                    break
            except Exception:
                continue
        return results

    def _scan_env_files(self, repo_path: Path) -> List[Dict]:
        results = []
        safe_names = {'.env.example', '.env.sample', '.env.template'}
        for f in repo_path.rglob('.env*'):
            if '.git' in str(f) or f.name in safe_names:
                continue
            try:
                content = f.read_text(errors='ignore')
                has_values = any(
                    '=' in ln and not ln.strip().startswith('#') and ln.split('=', 1)[-1].strip()
                    for ln in content.split('\n')
                )
                if has_values:
                    results.append({'severity': 'high', 'type': 'exposed-env-file',
                                    'file': str(f.relative_to(repo_path)), 'line': 0, 'source': 'env-check',
                                    'issue': f'{f.name} with real values should not be committed', 'snippet': ''})
            except Exception:
                pass
        return results

    def _available_scanners(self) -> List[str]:
        scanners = ['pattern-matching', 'entropy-analysis']
        for name, cmd in [('bandit', ['python3', '-m', 'bandit', '--version']),
                           ('pip-audit', ['python3', '-m', 'pip_audit', '--version']),
                           ('safety', ['safety', '--version'])]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
                scanners.append(name)
            except Exception:
                pass
        return scanners
