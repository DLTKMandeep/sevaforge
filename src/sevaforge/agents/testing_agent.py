"""
SevaForge Testing Agent

Detects test frameworks, analyses test coverage, and generates test
improvement plans.  Combines pattern-based framework detection and
coverage parsing with LLM-powered test strategy recommendations.

Capabilities:
  - detect_framework:   Identify test framework from project files
  - analyze_coverage:   Parse and evaluate test coverage reports
  - generate_test_plan: Create a comprehensive test improvement plan
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


# ── Framework detection patterns ─────────────────────────────────────

_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "pytest": [
        r"import\s+pytest",
        r"from\s+pytest",
        r"def\s+test_\w+",
        r"@pytest\.\w+",
        r"conftest\.py",
        r"pytest\.ini",
    ],
    "unittest": [
        r"import\s+unittest",
        r"from\s+unittest",
        r"class\s+\w+\(.*TestCase\)",
        r"self\.assert\w+",
    ],
    "jest": [
        r"describe\s*\(",
        r"it\s*\(",
        r"expect\s*\(",
        r"\.test\.(js|ts)",
        r"\.spec\.(js|ts)",
        r"jest\.config",
    ],
    "vitest": [
        r"import.*from\s+['\"]vitest['\"]",
        r"vitest\.config",
    ],
    "mocha": [
        r"import.*from\s+['\"]mocha['\"]",
        r"\.mocharc",
    ],
    "go_test": [
        r"func\s+Test\w+",
        r"testing\.T\b",
        r"_test\.go",
    ],
}

# ── Coverage parsing patterns ────────────────────────────────────────

_COVERAGE_PATTERNS: dict[str, str] = {
    "pytest_total": r"TOTAL\s+\d+\s+\d+\s+(\d+)%",
    "jest_total": r"All files.*?\s+(\d+\.?\d*)%",
    "go_total": r"total:\s+\(statements\)\s+(\d+\.?\d*)%",
    "generic_percent": r"(?:coverage|Coverage)[\s:]+(\d+\.?\d*)%",
}

# ── Test quality heuristics ──────────────────────────────────────────

_QUALITY_CHECKS: dict[str, tuple[str, str]] = {
    "no_assertions": (r"def\s+test_\w+[^}]*?(?:pass|\.\.\.)\s*$", "Test function with no assertions"),
    "sleep_in_test": (r"time\.sleep\s*\(", "Blocking sleep in test — use async or mocking"),
    "hardcoded_url": (r"http://localhost:\d+", "Hardcoded URL — use fixtures or env vars"),
    "broad_except": (r"except\s*(Exception|:)\s*:", "Broad exception catch in test"),
    "print_debug": (r"print\s*\(", "Print statement in test — use logging or assertions"),
    "todo_test": (r"#\s*TODO.*test", "TODO comment about missing test"),
    "skip_no_reason": (r"@pytest\.mark\.skip\s*$", "Skipped test without reason"),
}


class TestingAgent(BaseAgent):
    SYSTEM_PROMPT = """You are a senior QA engineer specializing in test strategy and test automation.

Your analysis covers:
1. Test coverage gaps and recommendations
2. Test quality assessment (flaky tests, slow tests, missing edge cases)
3. Framework-specific best practices
4. Test architecture recommendations (unit vs integration vs e2e balance)
5. Mocking and fixture strategies
6. CI integration recommendations

Provide specific, actionable recommendations with code examples where helpful."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="testing",
            name="Testing Agent",
            description="Detects test frameworks, analyses coverage, and generates test improvement plans",
            version="2.0.0",
            capabilities=[
                AgentCapability(
                    name="detect_framework",
                    description="Identify test framework from project files and code",
                ),
                AgentCapability(
                    name="analyze_coverage",
                    description="Parse and evaluate test coverage data",
                ),
                AgentCapability(
                    name="generate_test_plan",
                    description="Create a comprehensive test improvement plan",
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["testing", "coverage", "quality", "test-plan"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        analysis_type = ctx.params.get("analysis_type", "all")
        language = ctx.params.get("language", "python")
        coverage_output = ctx.params.get("coverage_output", "")

        result: dict[str, Any] = {
            "language": language,
            "analysis_type": analysis_type,
        }

        if analysis_type in ("framework", "all"):
            framework_info = self._detect_frameworks(code)
            result["frameworks"] = framework_info

        if analysis_type in ("coverage", "all"):
            coverage_data = self._parse_coverage(coverage_output or code)
            result["coverage"] = coverage_data

        if analysis_type in ("plan", "all"):
            quality_findings = self._check_test_quality(code)
            result["quality_findings"] = quality_findings
            result["quality_findings_count"] = len(quality_findings)

        test_metrics = self._compute_test_metrics(code)
        result["metrics"] = test_metrics

        try:
            prompt = self._build_test_plan_prompt(code, language, result)
            llm_response = await self.call_llm(ctx, prompt)
            result["test_plan"] = llm_response.content
            result["model_used"] = llm_response.model
            result["input_tokens"] = llm_response.input_tokens
            result["output_tokens"] = llm_response.output_tokens
            result["confidence"] = 0.85
        except Exception as exc:
            logger.warning("LLM test plan unavailable: %s", exc)
            result["test_plan"] = self._generate_fallback_plan(result)
            result["model_used"] = "pattern-only"
            result["input_tokens"] = 0
            result["output_tokens"] = 0
            result["confidence"] = 0.5

        return result

    def _detect_frameworks(self, code: str) -> list[dict[str, Any]]:
        detected = []
        for framework, patterns in _FRAMEWORK_PATTERNS.items():
            matches = 0
            for pattern in patterns:
                if re.search(pattern, code, re.MULTILINE):
                    matches += 1
            if matches > 0:
                detected.append({
                    "framework": framework,
                    "confidence": min(1.0, matches / len(patterns)),
                    "pattern_matches": matches,
                })
        detected.sort(key=lambda x: x["confidence"], reverse=True)
        return detected

    def _parse_coverage(self, text: str) -> dict[str, Any]:
        coverage_data: dict[str, Any] = {
            "total_percent": None,
            "files": [],
            "assessment": "unknown",
        }

        for name, pattern in _COVERAGE_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                coverage_data["total_percent"] = float(match.group(1))
                break

        file_pattern = re.compile(r"^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%", re.MULTILINE)
        for m in file_pattern.finditer(text):
            coverage_data["files"].append({
                "file": m.group(1),
                "statements": int(m.group(2)),
                "missing": int(m.group(3)),
                "percent": int(m.group(4)),
            })

        total = coverage_data["total_percent"]
        if total is not None:
            if total >= 80:
                coverage_data["assessment"] = "good"
            elif total >= 60:
                coverage_data["assessment"] = "adequate"
            elif total >= 40:
                coverage_data["assessment"] = "needs_improvement"
            else:
                coverage_data["assessment"] = "poor"

        return coverage_data

    def _check_test_quality(self, code: str) -> list[dict[str, Any]]:
        findings = []
        lines = code.splitlines()

        for check_name, (pattern, message) in _QUALITY_CHECKS.items():
            regex = re.compile(pattern, re.MULTILINE)
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    findings.append({
                        "check": check_name,
                        "message": message,
                        "location": f"line {line_num}",
                        "severity": "medium",
                        "source": "pattern",
                    })
        return findings

    def _compute_test_metrics(self, code: str) -> dict[str, int]:
        return {
            "total_lines": len(code.splitlines()),
            "test_functions": len(re.findall(r"(?:def\s+test_|it\s*\(|test\s*\()", code)),
            "test_classes": len(re.findall(r"class\s+Test\w+", code)),
            "assertions": len(re.findall(r"(?:assert|expect|should)\b", code)),
            "fixtures": len(re.findall(r"@pytest\.fixture|beforeEach|beforeAll", code)),
            "skipped_tests": len(re.findall(r"@pytest\.mark\.skip|\.skip\(|xit\(", code)),
        }

    def _build_test_plan_prompt(
        self, code: str, language: str, analysis: dict[str, Any],
    ) -> str:
        frameworks = analysis.get("frameworks", [])
        fw_str = ", ".join(f["framework"] for f in frameworks) if frameworks else "unknown"
        coverage = analysis.get("coverage", {})
        total_pct = coverage.get("total_percent", "unknown")
        metrics = analysis.get("metrics", {})

        return (
            f"Create a test improvement plan for this {language} project.\n\n"
            f"Detected frameworks: {fw_str}\n"
            f"Coverage: {total_pct}%\n"
            f"Test functions: {metrics.get('test_functions', 0)}\n"
            f"Assertions: {metrics.get('assertions', 0)}\n"
            f"Skipped tests: {metrics.get('skipped_tests', 0)}\n\n"
            f"Code:\n```{language}\n{code[:4000]}\n```\n\n"
            f"Provide:\n"
            f"1. Coverage gap analysis\n"
            f"2. Missing test scenarios\n"
            f"3. Test architecture recommendations\n"
            f"4. Prioritised action items\n"
        )

    def _generate_fallback_plan(self, analysis: dict[str, Any]) -> str:
        parts = ["## Test Improvement Plan (Pattern-Based)\n"]
        coverage = analysis.get("coverage", {})
        total = coverage.get("total_percent")

        if total is not None and total < 80:
            parts.append(f"- **Increase coverage** from {total}% to at least 80%")
        if analysis.get("quality_findings_count", 0) > 0:
            parts.append(f"- **Fix {analysis['quality_findings_count']} quality issues** found in test code")

        metrics = analysis.get("metrics", {})
        if metrics.get("skipped_tests", 0) > 0:
            parts.append(f"- **Review {metrics['skipped_tests']} skipped tests** and re-enable or remove")
        if metrics.get("test_functions", 0) == 0:
            parts.append("- **No test functions detected** — add tests for core functionality")

        parts.append("- Add integration tests for API endpoints")
        parts.append("- Configure test coverage reporting in CI pipeline")
        return "\n".join(parts)
