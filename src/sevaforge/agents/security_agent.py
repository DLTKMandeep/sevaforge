"""
SevaForge Security Agent

Comprehensive security analysis: vulnerability scanning, secrets detection,
dependency audit, compliance checking, and threat modeling.

Capabilities:
  - vulnerability_scan:   OWASP Top 10 and CWE-based detection
  - secrets_detection:    API keys, passwords, tokens in code
  - dependency_audit:     Known CVEs in dependencies
  - compliance_check:     SOC2 / HIPAA / PCI-DSS control verification
  - threat_modeling:      STRIDE-based threat analysis
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability,
    AgentConfig,
    AgentExecutionContext,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# ── Secret Patterns ─────────────────────────────────────────────────

_SECRET_PATTERNS = {
    "aws_access_key": (r"AKIA[0-9A-Z]{16}", "critical", "AWS Access Key ID exposed"),
    "aws_secret_key": (r"(?i)aws(.{0,20})?['\"][0-9a-zA-Z/+]{40}['\"]", "critical", "AWS Secret Access Key exposed"),
    "github_token": (r"gh[pousr]_[A-Za-z0-9_]{36,}", "critical", "GitHub Personal Access Token"),
    "github_classic": (r"ghp_[A-Za-z0-9]{36}", "critical", "GitHub Classic PAT"),
    "slack_token": (r"xox[baprs]-[0-9a-zA-Z-]{10,}", "critical", "Slack API Token"),
    "stripe_key": (r"sk_live_[0-9a-zA-Z]{24,}", "critical", "Stripe Secret Key"),
    "google_api": (r"AIza[0-9A-Za-z\\-_]{35}", "high", "Google API Key"),
    "jwt_secret": (r"(?i)(jwt|token|auth)(.{0,10})?secret\s*[=:]\s*['\"].{8,}", "high", "JWT/Auth Secret in code"),
    "private_key": (r"-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----", "critical", "Private key embedded in code"),
    "generic_api_key": (r"(?i)api[_-]?key\s*[=:]\s*['\"][A-Za-z0-9]{20,}['\"]", "high", "Generic API key"),
    "password_literal": (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{4,}['\"]", "high", "Hardcoded password"),
    "connection_string": (r"(?i)(mongodb|postgres|mysql|redis)://[^\s'\"]+", "high", "Database connection string with credentials"),
    "bearer_token": (r"(?i)bearer\s+[A-Za-z0-9\\-._~+/]+=*", "high", "Bearer token in code"),
}

# ── Vulnerability Patterns (OWASP / CWE mapped) ─────────────────────

_VULN_PATTERNS = {
    "cwe-78": {
        "name": "OS Command Injection",
        "owasp": "A03:2021 Injection",
        "patterns": [
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"subprocess\.(call|run|Popen)\s*\(.*shell\s*=\s*True",
            r"commands\.getoutput\s*\(",
        ],
        "severity": "critical",
    },
    "cwe-89": {
        "name": "SQL Injection",
        "owasp": "A03:2021 Injection",
        "patterns": [
            r"execute\s*\(\s*['\"].*%s",
            r"execute\s*\(\s*f['\"]",
            r"\.format\(.*\).*execute",
            r"cursor\.execute\s*\(\s*['\"].*\+",
        ],
        "severity": "critical",
    },
    "cwe-79": {
        "name": "Cross-Site Scripting (XSS)",
        "owasp": "A03:2021 Injection",
        "patterns": [
            r"innerHTML\s*=",
            r"document\.write\s*\(",
            r"\|\s*safe\b",
            r"mark_safe\s*\(",
        ],
        "severity": "high",
    },
    "cwe-502": {
        "name": "Insecure Deserialization",
        "owasp": "A08:2021 Software and Data Integrity",
        "patterns": [
            r"pickle\.loads?\s*\(",
            r"yaml\.load\s*\((?!.*Loader)",
            r"marshal\.loads?\s*\(",
            r"shelve\.open\s*\(",
        ],
        "severity": "critical",
    },
    "cwe-327": {
        "name": "Weak Cryptography",
        "owasp": "A02:2021 Cryptographic Failures",
        "patterns": [
            r"hashlib\.md5\s*\(",
            r"hashlib\.sha1\s*\(",
            r"DES\.",
            r"RC4\.",
            r"random\.random\s*\(",
        ],
        "severity": "high",
    },
    "cwe-295": {
        "name": "Improper Certificate Validation",
        "owasp": "A02:2021 Cryptographic Failures",
        "patterns": [
            r"verify\s*=\s*False",
            r"CERT_NONE",
            r"check_hostname\s*=\s*False",
        ],
        "severity": "high",
    },
    "cwe-22": {
        "name": "Path Traversal",
        "owasp": "A01:2021 Broken Access Control",
        "patterns": [
            r"open\s*\(.*\+.*\)",
            r"os\.path\.join\s*\(.*input",
            r"send_file\s*\(.*request",
        ],
        "severity": "high",
    },
    "cwe-611": {
        "name": "XXE (XML External Entities)",
        "owasp": "A05:2021 Security Misconfiguration",
        "patterns": [
            r"xml\.etree\.ElementTree\.parse\s*\(",
            r"lxml\.etree\.parse\s*\(",
            r"xml\.dom\.minidom\.parse\s*\(",
        ],
        "severity": "high",
    },
}


class SecurityAgent(BaseAgent):
    """
    Enterprise security analysis agent.

    Combines fast pattern-based scanning with deep LLM analysis for
    comprehensive security review.
    """

    SYSTEM_PROMPT = """You are a senior application security engineer specializing in code security review.

Your analysis must cover:
1. OWASP Top 10 vulnerabilities
2. CWE-mapped weaknesses
3. Authentication and authorization flaws
4. Data exposure risks
5. Insecure configurations
6. Supply chain risks (dependency issues)
7. Cryptographic weaknesses

For each finding, provide:
- CWE ID (if applicable)
- OWASP category
- Severity (critical/high/medium/low)
- Evidence (the specific code pattern)
- Impact (what an attacker could do)
- Remediation (specific fix with code example)

Prioritize findings by exploitability and impact. Do not report theoretical
risks without evidence in the code."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="security",
            name="Security Agent",
            description="Comprehensive security analysis — vulnerabilities, secrets, compliance",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="vulnerability_scan", description="OWASP Top 10 and CWE-based vulnerability detection"),
                AgentCapability(name="secrets_detection", description="Detect exposed API keys, passwords, tokens"),
                AgentCapability(name="dependency_audit", description="Check dependencies for known CVEs"),
                AgentCapability(name="compliance_check", description="SOC2/HIPAA/PCI-DSS control verification"),
                AgentCapability(name="threat_modeling", description="STRIDE-based threat analysis"),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["security", "vulnerability", "compliance", "secrets"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        scan_type = ctx.params.get("scan_type", "full")
        language = ctx.params.get("language", "python")
        file_path = ctx.params.get("file_path", "unknown")

        findings = []
        summary_parts = []

        if scan_type in ("full", "secrets"):
            secret_findings = self._scan_secrets(code)
            findings.extend(secret_findings)
            if secret_findings:
                summary_parts.append(f"{len(secret_findings)} exposed secrets")

        if scan_type in ("full", "vulnerabilities"):
            vuln_findings = self._scan_vulnerabilities(code)
            findings.extend(vuln_findings)
            if vuln_findings:
                summary_parts.append(f"{len(vuln_findings)} vulnerabilities")

        prompt = self._build_security_prompt(code, language, file_path, scan_type, findings)
        try:
            llm_response = await self.call_llm(ctx, prompt)
            llm_findings = self._parse_llm_security_findings(llm_response.content)
            findings.extend(llm_findings)
            if llm_findings:
                summary_parts.append(f"{len(llm_findings)} LLM-detected issues")

            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM security analysis unavailable: %s", exc)
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        risk_score = self._calculate_risk_score(findings)

        severity_counts = {}
        for f in findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        summary = f"Security scan: {', '.join(summary_parts) if summary_parts else 'no issues found'}"

        return {
            "summary": summary,
            "findings": findings,
            "total_findings": len(findings),
            "severity_counts": severity_counts,
            "risk_score": risk_score,
            "risk_level": "critical" if risk_score >= 80 else "high" if risk_score >= 60 else "medium" if risk_score >= 30 else "low",
            "scan_type": scan_type,
            "language": language,
            "file_path": file_path,
            "lines_scanned": len(code.splitlines()),
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.9 if model_used != "pattern-only" else 0.6,
        }

    def _scan_secrets(self, code: str) -> list[dict[str, Any]]:
        findings = []
        lines = code.splitlines()

        for secret_type, (pattern, severity, description) in _SECRET_PATTERNS.items():
            regex = re.compile(pattern)
            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                if regex.search(line):
                    masked_line = regex.sub("[REDACTED]", line).strip()
                    findings.append({
                        "severity": severity,
                        "category": "secrets",
                        "type": secret_type,
                        "location": f"line {line_num}",
                        "title": description,
                        "description": f"{description} at line {line_num}",
                        "evidence": masked_line[:120],
                        "remediation": "Move to environment variables or a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)",
                        "source": "pattern",
                    })

        return findings

    def _scan_vulnerabilities(self, code: str) -> list[dict[str, Any]]:
        findings = []
        lines = code.splitlines()

        for cwe_id, vuln_info in _VULN_PATTERNS.items():
            for pattern in vuln_info["patterns"]:
                regex = re.compile(pattern, re.IGNORECASE)
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        findings.append({
                            "severity": vuln_info["severity"],
                            "category": "vulnerability",
                            "cwe": cwe_id.upper(),
                            "owasp": vuln_info["owasp"],
                            "location": f"line {line_num}",
                            "title": vuln_info["name"],
                            "description": f"{vuln_info['name']} ({cwe_id.upper()}) — {vuln_info['owasp']}",
                            "evidence": line.strip()[:120],
                            "source": "pattern",
                        })

        return findings

    def _calculate_risk_score(self, findings: list[dict[str, Any]]) -> int:
        if not findings:
            return 0

        weights = {"critical": 25, "high": 15, "medium": 8, "low": 3, "info": 1}
        score = 0
        for f in findings:
            severity = f.get("severity", "info")
            score += weights.get(severity, 1)

        return min(100, score)

    def _build_security_prompt(
        self, code: str, language: str, file_path: str,
        scan_type: str, existing_findings: list[dict[str, Any]],
    ) -> str:
        existing_context = ""
        if existing_findings:
            existing_context = f"\n\nPattern-based scanning found {len(existing_findings)} issues already. " \
                               "Focus on deeper semantic vulnerabilities that patterns cannot detect.\n"

        return f"""Perform a {scan_type} security analysis on this {language} code from `{file_path}`.
{existing_context}
```{language}
{code}
```

Report findings with: severity, CWE ID, OWASP category, evidence, impact, and remediation.
Focus on issues that require semantic understanding (logic flaws, auth bypasses, race conditions, etc.)."""

    def _parse_llm_security_findings(self, text: str) -> list[dict[str, Any]]:
        findings = []
        cwe_pattern = re.compile(r"CWE-(\d+)", re.IGNORECASE)
        severity_pattern = re.compile(r"(critical|high|medium|low)", re.IGNORECASE)

        sections = text.split("\n\n")
        for section in sections:
            cwe_match = cwe_pattern.search(section)
            sev_match = severity_pattern.search(section)
            if cwe_match or sev_match:
                title_line = section.strip().split("\n")[0][:100]
                findings.append({
                    "severity": sev_match.group(1).lower() if sev_match else "medium",
                    "category": "vulnerability",
                    "cwe": f"CWE-{cwe_match.group(1)}" if cwe_match else "",
                    "location": "see description",
                    "title": title_line.lstrip("#- ").strip(),
                    "description": section.strip()[:500],
                    "source": "llm",
                })

        return findings
