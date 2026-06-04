"""
SevaForge Normalization Agent

Standardizes repository structure by generating or fixing common config files
(.gitignore, .editorconfig, pre-commit), detecting code style inconsistencies,
and recommending normalization improvements.

Capabilities:
  - analyze_repo_structure:  Audit a repo for missing standard config files
  - generate_configs:        Generate language-appropriate config templates
  - fix_style_issues:        Detect and fix tabs/spaces, line endings, etc.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)

logger = logging.getLogger(__name__)


# -- Language-keyed .gitignore templates -------------------------------------

_GITIGNORE_TEMPLATES: dict[str, str] = {
    "python": (
        "__pycache__/\n*.py[cod]\n*$py.class\n*.egg-info/\ndist/\nbuild/\n"
        ".eggs/\n*.egg\n.venv/\nvenv/\nenv/\n.env\n*.so\n.mypy_cache/\n"
        ".pytest_cache/\n.coverage\nhtmlcov/\n.tox/\n"
    ),
    "node": (
        "node_modules/\ndist/\nbuild/\n.env\n.env.local\n*.log\n"
        "npm-debug.log*\nyarn-debug.log*\nyarn-error.log*\n"
        ".next/\n.nuxt/\ncoverage/\n.cache/\n"
    ),
    "go": (
        "bin/\npkg/\n*.exe\n*.exe~\n*.dll\n*.so\n*.dylib\n*.test\n"
        "*.out\nvendor/\n.env\ncoverage.out\n"
    ),
    "java": (
        "target/\n*.class\n*.jar\n*.war\n*.ear\n.gradle/\nbuild/\n"
        ".idea/\n*.iml\n.settings/\n.project\n.classpath\n"
    ),
}

# -- Language-keyed .editorconfig templates ----------------------------------

_EDITORCONFIG_TEMPLATES: dict[str, str] = {
    "python": (
        "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\n"
        "insert_final_newline = true\ntrim_trailing_whitespace = true\n\n"
        "[*.py]\nindent_style = space\nindent_size = 4\nmax_line_length = 120\n\n"
        "[*.{yml,yaml,json}]\nindent_style = space\nindent_size = 2\n"
    ),
    "node": (
        "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\n"
        "insert_final_newline = true\ntrim_trailing_whitespace = true\n\n"
        "[*.{js,ts,jsx,tsx}]\nindent_style = space\nindent_size = 2\n\n"
        "[*.{json,yml,yaml}]\nindent_style = space\nindent_size = 2\n"
    ),
    "go": (
        "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\n"
        "insert_final_newline = true\ntrim_trailing_whitespace = true\n\n"
        "[*.go]\nindent_style = tab\nindent_size = 4\n\n"
        "[*.{yml,yaml,json}]\nindent_style = space\nindent_size = 2\n"
    ),
    "java": (
        "root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\n"
        "insert_final_newline = true\ntrim_trailing_whitespace = true\n\n"
        "[*.java]\nindent_style = space\nindent_size = 4\n\n"
        "[*.{xml,yml,yaml,json}]\nindent_style = space\nindent_size = 2\n"
    ),
}

# -- Language-keyed pre-commit templates -------------------------------------

_PRECOMMIT_TEMPLATES: dict[str, str] = {
    "python": (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v4.5.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace\n"
        "      - id: end-of-file-fixer\n"
        "      - id: check-yaml\n"
        "      - id: check-added-large-files\n"
        "  - repo: https://github.com/psf/black\n"
        "    rev: '24.3.0'\n"
        "    hooks:\n"
        "      - id: black\n"
        "  - repo: https://github.com/charliermarsh/ruff-pre-commit\n"
        "    rev: v0.3.0\n"
        "    hooks:\n"
        "      - id: ruff\n"
    ),
    "node": (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v4.5.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace\n"
        "      - id: end-of-file-fixer\n"
        "      - id: check-json\n"
        "  - repo: https://github.com/pre-commit/mirrors-eslint\n"
        "    rev: v8.56.0\n"
        "    hooks:\n"
        "      - id: eslint\n"
    ),
    "go": (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v4.5.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace\n"
        "      - id: end-of-file-fixer\n"
        "  - repo: https://github.com/dnephin/pre-commit-golang\n"
        "    rev: v0.5.1\n"
        "    hooks:\n"
        "      - id: go-fmt\n"
        "      - id: go-vet\n"
    ),
    "java": (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v4.5.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace\n"
        "      - id: end-of-file-fixer\n"
        "      - id: check-xml\n"
    ),
}

# -- Standard config files every repo should have ---------------------------

_STANDARD_FILES = [
    ".gitignore",
    ".editorconfig",
    ".pre-commit-config.yaml",
    "README.md",
    "LICENSE",
    ".github/CODEOWNERS",
]

# -- Style issue patterns ----------------------------------------------------

_STYLE_PATTERNS: dict[str, tuple[str, str, str]] = {
    # (regex, severity, description)
    "tabs_in_py": (r"\t", "medium", "Tab character found (prefer spaces in Python)"),
    "crlf_ending": (r"\r\n", "low", "Windows line ending (CRLF) — standardize to LF"),
    "trailing_whitespace": (r"[ \t]+$", "low", "Trailing whitespace"),
    "multiple_blank_lines": (r"\n{4,}", "low", "More than two consecutive blank lines"),
    "no_final_newline_marker": (r"\S$", "low", "File may not end with a newline"),
}


class NormalizationAgent(BaseAgent):
    """
    Repository normalization agent.

    Audits a repository for missing standard files, generates language-
    appropriate configuration templates, and detects code style issues.
    """

    SYSTEM_PROMPT = (
        "You are a senior engineering standards lead. Your job is to ensure "
        "repositories follow consistent structure, configuration, and code "
        "style conventions. Provide concrete file contents — not just advice. "
        "Prioritize practical, team-friendly defaults over opinionated configs."
    )

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="normalization",
            name="Normalization Agent",
            description="Standardizes repo structure — gitignore, editorconfig, pre-commit, style fixes",
            version="1.0.0",
            capabilities=[
                AgentCapability(
                    name="analyze_repo_structure",
                    description="Audit a repo for missing standard config files",
                    input_schema={"file_list": "str", "language": "str"},
                    output_schema={"missing_files": "list", "style_issues": "list"},
                ),
                AgentCapability(
                    name="generate_configs",
                    description="Generate language-appropriate config file templates",
                    input_schema={"language": "str", "config_type": "str"},
                    output_schema={"configs": "dict"},
                ),
                AgentCapability(
                    name="fix_style_issues",
                    description="Detect and report code style issues (tabs vs spaces, line endings)",
                    input_schema={"code": "str", "language": "str"},
                    output_schema={"issues": "list", "fixed_code": "str"},
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["normalization", "style", "config", "standards"],
        ))

    # -- execute --------------------------------------------------------------

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Execute normalization analysis.

        ctx.input: file listing, code content, or repo description
        ctx.params:
          - action: "analyze" | "generate" | "fix_style"  (default "analyze")
          - language: str  (python, node, go, java)
          - file_list: list[str]  (existing file paths for gap analysis)
        """
        action = ctx.params.get("action", "analyze")
        language = ctx.params.get("language", "python")

        if action == "generate":
            return self._generate_configs(language)

        if action == "fix_style":
            return self._detect_style_issues(ctx.input, language)

        # Default: analyze
        file_list = ctx.params.get("file_list", [])
        if isinstance(file_list, str):
            file_list = [f.strip() for f in file_list.split("\n") if f.strip()]

        missing = self._find_missing_files(file_list)
        style_issues = self._detect_style_issues(ctx.input, language)
        configs = self._generate_configs(language)

        # LLM: suggest additional improvements
        prompt = self._build_analysis_prompt(
            ctx.input, language, file_list, missing, style_issues,
        )
        try:
            llm_response = await self.call_llm(ctx, prompt)
            suggestions = self._parse_suggestions(llm_response.content)
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM unavailable for normalization analysis: %s", exc)
            suggestions = []
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        return {
            "missing_files": missing,
            "style_issues": style_issues.get("issues", []),
            "total_style_issues": style_issues.get("total_issues", 0),
            "generated_configs": configs.get("configs", {}),
            "suggestions": suggestions,
            "language": language,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.85 if model_used != "pattern-only" else 0.65,
        }

    # -- Missing file detection -----------------------------------------------

    def _find_missing_files(self, file_list: list[str]) -> list[dict[str, str]]:
        """Compare existing files against the standard set."""
        normalized = {f.lstrip("./").lower() for f in file_list}
        missing: list[dict[str, str]] = []
        for expected in _STANDARD_FILES:
            if expected.lower() not in normalized:
                missing.append({
                    "file": expected,
                    "severity": "high" if expected in (".gitignore", "README.md") else "medium",
                    "reason": f"Standard config file '{expected}' is missing from the repository",
                })
        return missing

    # -- Config generation ----------------------------------------------------

    def _generate_configs(self, language: str) -> dict[str, Any]:
        """Generate all standard config files for the given language."""
        lang = language.lower()
        configs: dict[str, str] = {}

        configs[".gitignore"] = _GITIGNORE_TEMPLATES.get(lang, _GITIGNORE_TEMPLATES["python"])
        configs[".editorconfig"] = _EDITORCONFIG_TEMPLATES.get(lang, _EDITORCONFIG_TEMPLATES["python"])
        configs[".pre-commit-config.yaml"] = _PRECOMMIT_TEMPLATES.get(lang, _PRECOMMIT_TEMPLATES["python"])

        return {
            "configs": configs,
            "language": language,
            "total_files": len(configs),
            "model_used": "template",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.95,
        }

    # -- Style issue detection ------------------------------------------------

    def _detect_style_issues(self, code: str, language: str) -> dict[str, Any]:
        """Detect code style inconsistencies."""
        issues: list[dict[str, Any]] = []
        lines = code.splitlines()

        for issue_id, (pattern, severity, description) in _STYLE_PATTERNS.items():
            # Skip tab check for Go (tabs are canonical)
            if issue_id == "tabs_in_py" and language.lower() == "go":
                continue

            regex = re.compile(pattern)
            hit_count = 0
            first_line = 0
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    hit_count += 1
                    if first_line == 0:
                        first_line = line_num

            if hit_count > 0:
                issues.append({
                    "id": issue_id,
                    "severity": severity,
                    "description": description,
                    "occurrences": hit_count,
                    "first_line": first_line,
                    "source": "pattern",
                })

        # Check indent consistency
        indent_tabs = sum(1 for l in lines if l.startswith("\t"))
        indent_spaces = sum(1 for l in lines if re.match(r"^ {2,}", l))
        if indent_tabs > 0 and indent_spaces > 0:
            issues.append({
                "id": "mixed_indentation",
                "severity": "high",
                "description": f"Mixed indentation: {indent_tabs} tab-indented lines, "
                               f"{indent_spaces} space-indented lines",
                "occurrences": indent_tabs + indent_spaces,
                "first_line": 1,
                "source": "pattern",
            })

        return {
            "issues": issues,
            "total_issues": len(issues),
            "language": language,
            "lines_checked": len(lines),
            "model_used": "pattern",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 0.9,
        }

    # -- LLM prompt -----------------------------------------------------------

    def _build_analysis_prompt(
        self, code: str, language: str, file_list: list[str],
        missing: list[dict[str, str]], style_result: dict[str, Any],
    ) -> str:
        missing_names = ", ".join(m["file"] for m in missing) if missing else "none"
        style_count = style_result.get("total_issues", 0)

        return (
            f"Analyze this {language} repository for normalization improvements.\n\n"
            f"Missing standard files: {missing_names}\n"
            f"Style issues detected: {style_count}\n"
            f"Existing files:\n{chr(10).join(file_list[:30]) if file_list else '(not provided)'}\n\n"
            f"Code sample:\n```{language}\n{code[:3000]}\n```\n\n"
            "Suggest additional normalization improvements beyond what the "
            "pattern scanner found. Consider:\n"
            "- CI linting configuration\n"
            "- Dependency lock file presence\n"
            "- Docker / containerization standards\n"
            "- Security scanning integration\n"
            "- Commit message conventions"
        )

    def _parse_suggestions(self, text: str) -> list[str]:
        """Extract normalization suggestions from LLM output."""
        suggestions: list[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped and len(stripped) > 15 and any(
                kw in stripped.lower()
                for kw in ["add", "create", "configure", "enable", "set up", "consider", "recommend"]
            ):
                suggestions.append(stripped.lstrip("- #*0123456789.").strip()[:200])
                if len(suggestions) >= 10:
                    break
        return suggestions
