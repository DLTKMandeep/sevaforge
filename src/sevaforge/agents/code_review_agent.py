"""
SevaForge Code Review Agent

Analyzes code for bugs, security vulnerabilities, style issues, and
performance problems.  Uses LLM for deep semantic analysis and delegates
to the SecurityAgent for vulnerability-specific checks.

Capabilities:
  - static_analysis:    Pattern-based code quality checks
  - security_review:    Security vulnerability detection (delegates to SecurityAgent)
  - style_check:        Coding standards and best practices
  - performance_review: Performance anti-pattern detection
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from sevaforge.agents.base_agent import (
    AgentCapability,
    AgentConfig,
    AgentExecutionContext,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# ── Known Code Patterns (fast pre-LLM checks) ─────────────────────

_SECURITY_PATTERNS = {
    r"eval\s*\(": "Dangerous eval() usage — potential code injection",
    r"exec\s*\(": "Dangerous exec() usage — potential code injection",
    r"subprocess\.call\(.*shell\s*=\s*True": "Shell injection risk via subprocess",
    r"os\.system\s*\(": "Shell injection risk via os.system",
    r"pickle\.loads?\s*\(": "Insecure deserialization via pickle",
    r"yaml\.load\s*\((?!.*Loader)": "Unsafe YAML loading — use yaml.safe_load",
    r"password\s*=\s*['\"]": "Hardcoded password detected",
    r"api[_-]?key\s*=\s*['\"]": "Hardcoded API key detected",
    r"SECRET\s*=\s*['\"]": "Hardcoded secret detected",
    r"md5\s*\(": "Weak hash algorithm (MD5) — use SHA-256+",
    r"sha1\s*\(": "Weak hash algorithm (SHA-1) — use SHA-256+",
    r"SELECT\s+.*\+\s*['\"]": "SQL injection risk — use parameterized queries",
    r"\.format\(.*input": "Potential format string injection",
    r"verify\s*=\s*False": "SSL verification disabled",
}

_QUALITY_PATTERNS = {
    r"except\s*:": "Bare except clause — catch specific exceptions",
    r"except\s+Exception\s*:": "Broad exception catch — be more specific",
    r"# ?TODO": "TODO comment found — address or track",
    r"# ?FIXME": "FIXME comment found — needs attention",
    r"# ?HACK": "HACK comment found — needs refactoring",
    r"print\s*\(": "print() in production code — use logging instead",
    r"import \*": "Wildcard import — import specific names",
    r"global\s+\w": "Global variable usage — consider alternatives",
    r"time\.sleep\s*\(": "Blocking sleep — consider async alternatives",
}

_PERFORMANCE_PATTERNS = {
    r"for\s+\w+\s+in\s+range\(len\(": "Iterate directly instead of range(len())",
    r"\+\s*=\s*['\"]": "String concatenation in loop — use join() or list",
    r"\.append\(.*for\s+": "Consider list comprehension instead of append loop",
    r"SELECT\s+\*\s+FROM": "SELECT * can be slow — specify needed columns",
    r"\.read\(\)": "Reading entire file at once — consider streaming for large files",
}


class CodeReviewAgent(BaseAgent):
    """
    Enterprise code review agent with LLM-powered analysis.

    Runs fast pattern-based checks first, then uses the LLM for
    deep semantic analysis of code quality, architecture, and correctness.
    """

    SYSTEM_PROMPT = """You are an expert code reviewer for enterprise Python applications.
Your task is to analyze code and provide actionable feedback.

For each issue found, report:
1. SEVERITY: critical / high / medium / low / info
2. LOCATION: file path and line number (if available)
3. TITLE: concise issue name
4. DESCRIPTION: what's wrong and why it matters
5. SUGGESTION: specific fix or improvement

Focus on:
- Bugs and logic errors
- Security vulnerabilities
- Performance problems
- Code maintainability
- Error handling gaps
- Type safety issues
- API design concerns

Be thorough but prioritize actionable findings. Do not report style nits
unless they significantly impact readability."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="code-review",
            name="Code Review Agent",
            description="Analyzes code for bugs, security issues, style, and performance",
            version="2.0.0",
            capabilities=[
                AgentCapability(
                    name="static_analysis",
                    description="Pattern-based code quality and bug detection",
                ),
                AgentCapability(
                    name="security_review",
                    description="Security vulnerability scanning and detection",
                ),
                AgentCapability(
                    name="style_check",
                    description="Coding standards and best practices enforcement",
                ),
                AgentCapability(
                    name="performance_review",
                    description="Performance anti-pattern detection and optimization suggestions",
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["code", "review", "security", "quality"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute a code review.

        ctx.input should contain the code to review.
        ctx.params may include:
          - language: str (e.g., "python", "javascript")
          - focus: str ("security" | "performance" | "quality" | "all")
          - file_path: str (path for context)
        """
        code = ctx.input
        language = ctx.params.get("language", "python")
        focus = ctx.params.get("focus", "all")
        file_path = ctx.params.get("file_path", "unknown")

        # ── Phase 1: Fast pattern-based analysis ──
        pattern_findings = self._run_pattern_checks(code, focus)

        # ── Phase 2: LLM deep analysis ──
        prompt = self._build_review_prompt(code, language, focus, file_path, pattern_findings)

        try:
            llm_response = await self.call_llm(ctx, prompt)
            llm_analysis = llm_response.content

            # ── Phase 3: Combine results ──
            result = {
                "summary": self._extract_summary(llm_analysis),
                "findings": pattern_findings + self._parse_llm_findings(llm_analysis),
                "pattern_findings_count": len(pattern_findings),
                "llm_analysis": llm_analysis,
                "language": language,
                "focus": focus,
                "file_path": file_path,
                "lines_reviewed": len(code.splitlines()),
                "model_used": llm_response.model,
                "input_tokens": llm_response.input_tokens,
                "output_tokens": llm_response.output_tokens,
                "confidence": 0.85,
            }

            # Determine overall risk
            severities = [f.get("severity", "info") for f in result["findings"]]
            if "critical" in severities:
                result["overall_risk"] = "critical"
            elif "high" in severities:
                result["overall_risk"] = "high"
            elif "medium" in severities:
                result["overall_risk"] = "medium"
            else:
                result["overall_risk"] = "low"

            logger.info(
                "Code review complete: %d findings, risk=%s",
                len(result["findings"]), result["overall_risk"],
            )
            return result

        except Exception as exc:
            # Fall back to pattern-only results if LLM fails
            logger.warning("LLM analysis failed, returning pattern-only results: %s", exc)
            return {
                "summary": f"Pattern-based review found {len(pattern_findings)} issues (LLM unavailable)",
                "findings": pattern_findings,
                "pattern_findings_count": len(pattern_findings),
                "llm_analysis": None,
                "language": language,
                "focus": focus,
                "file_path": file_path,
                "lines_reviewed": len(code.splitlines()),
                "overall_risk": "medium" if pattern_findings else "low",
                "confidence": 0.5,
                "model_used": "pattern-only",
                "input_tokens": 0,
                "output_tokens": 0,
            }

    # ── Pattern-Based Analysis ───────────────────────────────────────

    def _run_pattern_checks(self, code: str, focus: str) -> list[dict[str, Any]]:
        """Run regex-based pattern checks on the code."""
        findings = []
        lines = code.splitlines()

        patterns: dict[str, dict[str, str]] = {}
        if focus in ("all", "security"):
            patterns.update({f"security:{k}": {"pattern": k, "message": v, "severity": "high", "category": "security"}
                            for k, v in _SECURITY_PATTERNS.items()})
        if focus in ("all", "quality"):
            patterns.update({f"quality:{k}": {"pattern": k, "message": v, "severity": "medium", "category": "quality"}
                            for k, v in _QUALITY_PATTERNS.items()})
        if focus in ("all", "performance"):
            patterns.update({f"perf:{k}": {"pattern": k, "message": v, "severity": "medium", "category": "performance"}
                            for k, v in _PERFORMANCE_PATTERNS.items()})

        for _key, info in patterns.items():
            regex = re.compile(info["pattern"], re.IGNORECASE)
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    findings.append({
                        "severity": info["severity"],
                        "location": f"line {line_num}",
                        "title": info["message"].split("—")[0].strip() if "—" in info["message"] else info["message"],
                        "description": info["message"],
                        "suggestion": info["message"].split("—")[1].strip() if "—" in info["message"] else "",
                        "category": info["category"],
                        "source": "pattern",
                    })

        return findings

    def _build_review_prompt(
        self,
        code: str,
        language: str,
        focus: str,
        file_path: str,
        pattern_findings: list[dict[str, Any]],
    ) -> str:
        """Build the LLM prompt for deep code analysis."""
        focus_instruction = {
            "security": "Focus primarily on security vulnerabilities and injection risks.",
            "performance": "Focus primarily on performance bottlenecks and optimization.",
            "quality": "Focus primarily on code quality, maintainability, and best practices.",
            "all": "Review for security, performance, quality, and correctness.",
        }.get(focus, "Review for security, performance, quality, and correctness.")

        pattern_context = ""
        if pattern_findings:
            pattern_context = f"\n\nPattern-based analysis already found {len(pattern_findings)} issues:\n"
            for f in pattern_findings[:5]:
                pattern_context += f"- [{f['severity']}] {f['title']} at {f['location']}\n"
            pattern_context += "\nDo NOT repeat these. Focus on deeper semantic issues.\n"

        return f"""Review the following {language} code from `{file_path}`.

{focus_instruction}
{pattern_context}

```{language}
{code}
```

Provide your review as a structured analysis with:
1. A 1-2 sentence summary of overall code quality
2. Specific findings (each with severity, location, title, description, suggestion)
3. An overall risk assessment (critical/high/medium/low)"""

    def _extract_summary(self, llm_text: str) -> str:
        """Extract the summary from LLM output."""
        lines = llm_text.strip().split("\n")
        for line in lines[:5]:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                return line
        return "Code review completed with LLM analysis."

    def _parse_llm_findings(self, llm_text: str) -> list[dict[str, Any]]:
        """Parse structured findings from LLM text output."""
        findings = []
        # Simple heuristic: look for severity markers
        severity_pattern = re.compile(
            r"(critical|high|medium|low|info)\s*[:\]|]\s*(.+)",
            re.IGNORECASE,
        )
        for line in llm_text.split("\n"):
            match = severity_pattern.search(line)
            if match:
                findings.append({
                    "severity": match.group(1).lower(),
                    "location": "see description",
                    "title": match.group(2).strip()[:100],
                    "description": match.group(2).strip(),
                    "suggestion": "",
                    "category": "llm_analysis",
                    "source": "llm",
                })

        return findings
