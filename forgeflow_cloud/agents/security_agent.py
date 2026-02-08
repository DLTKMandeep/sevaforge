#!/usr/bin/env python3
"""
Security Agent - Scans for security vulnerabilities.
Mapped to: scan command → security_mcp
"""
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .base_agent import BaseAgent


# Security patterns to detect
SECURITY_PATTERNS = {
    'hardcoded-secret': [
        (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password'),
        (r'api[_-]?key\s*=\s*["\'][\w-]+["\']', 'Hardcoded API key'),
        (r'secret\s*=\s*["\'][^"\']+["\']', 'Hardcoded secret'),
        (r'AWS_ACCESS_KEY_ID\s*=\s*["\']?AKI[A-Z0-9]{16}', 'AWS Access Key'),
        (r'private_key\s*=\s*["\']', 'Private key in code'),
    ],
    'sql-injection': [
        (r'execute\([^)]*%[sd][^)]*\)', 'Potential SQL injection'),
        (r'cursor\.execute\([^)]*\+[^)]*\)', 'SQL string concatenation'),
        (r'f["\'].*SELECT.*\{', 'SQL in f-string'),
    ],
    'command-injection': [
        (r'os\.system\([^)]*\+[^)]*\)', 'Command injection via os.system'),
        (r'subprocess\.call\([^)]*shell\s*=\s*True', 'Shell injection risk'),
        (r'eval\([^)]*input', 'Eval with user input'),
    ],
    'insecure-config': [
        (r'DEBUG\s*=\s*True', 'Debug mode enabled'),
        (r'verify\s*=\s*False', 'SSL verification disabled'),
        (r'ALLOWED_HOSTS\s*=\s*\[\s*["\']\\*["\']', 'Wildcard allowed hosts'),
    ]
}

SEVERITY_MAP = {
    'hardcoded-secret': 'critical',
    'sql-injection': 'high',
    'command-injection': 'high',
    'insecure-config': 'medium'
}


class SecurityAgent(BaseAgent):
    """Agent that scans for security vulnerabilities."""
    
    def __init__(self):
        super().__init__(
            name="security_agent",
            description="Scans repository for security vulnerabilities, secrets, and risks"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Run security scan on repository."""
        repo_path = Path(params.get('path', '.'))
        severity_threshold = params.get('severity_threshold', 'medium')
        vulnerabilities = []
        
        self.log(f"Scanning {repo_path.absolute()} for security issues...")
        
        severity_levels = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
        threshold_level = severity_levels.get(severity_threshold.lower(), 2)
        
        # Scan Python files
        vulnerabilities.extend(self._scan_python_files(repo_path, threshold_level, severity_levels))
        
        # Scan for .env files with secrets
        vulnerabilities.extend(self._scan_env_files(repo_path))
        
        # Build summary
        by_severity = {}
        for v in vulnerabilities:
            sev = v['severity']
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        # Create docs directory
        docs_dir = repo_path / 'docs'
        docs_dir.mkdir(exist_ok=True)
        
        status = 'success' if not vulnerabilities else 'warning'
        summary = f"Found {len(vulnerabilities)} security issues" if vulnerabilities else "No security issues found"
        
        self.log(summary)
        
        return self.create_result(
            status=status,
            summary=summary,
            data={
                'total': len(vulnerabilities),
                'by_severity': by_severity,
                'threshold': severity_threshold,
                'vulnerabilities': vulnerabilities[:20]  # Limit for display
            },
            findings=[
                f"{v['severity'].upper()}: {v['file']}:{v['line']} - {v['issue']}"
                for v in vulnerabilities[:10]
            ]
        )
    
    def _scan_python_files(self, repo_path: Path, threshold_level: int, 
                           severity_levels: Dict[str, int]) -> List[Dict[str, Any]]:
        """Scan Python files for security vulnerabilities."""
        vulnerabilities = []
        
        for py_file in repo_path.rglob('*.py'):
            if any(skip in str(py_file) for skip in ['__pycache__', 'venv', '.venv', 'node_modules']):
                continue
            
            try:
                content = py_file.read_text()
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    for vuln_type, patterns in SECURITY_PATTERNS.items():
                        for pattern, description in patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                severity = SEVERITY_MAP.get(vuln_type, 'medium')
                                if severity_levels.get(severity, 0) >= threshold_level:
                                    vulnerabilities.append({
                                        'severity': severity,
                                        'type': vuln_type,
                                        'file': str(py_file.relative_to(repo_path)),
                                        'line': line_num,
                                        'issue': description,
                                        'snippet': line.strip()[:60]
                                    })
            except Exception:
                pass
        
        return vulnerabilities
    
    def _scan_env_files(self, repo_path: Path) -> List[Dict[str, Any]]:
        """Scan for exposed environment files."""
        vulnerabilities = []
        
        for env_file in repo_path.rglob('.env*'):
            if env_file.name != '.env.example':
                vulnerabilities.append({
                    'severity': 'high',
                    'type': 'exposed-env',
                    'file': str(env_file.relative_to(repo_path)),
                    'line': 0,
                    'issue': 'Environment file should not be committed',
                    'snippet': f'{env_file.name} found in repository'
                })
        
        return vulnerabilities