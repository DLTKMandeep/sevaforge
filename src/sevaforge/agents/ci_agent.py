"""
SevaForge CI Agent

Generates Continuous Integration pipeline configurations: GitHub Actions,
GitLab CI, and Dependabot configs.  Uses language detection to select
appropriate lint, test, and security scanning steps.

Capabilities:
  - generate_github_actions:  GitHub Actions CI/CD workflow YAML
  - generate_gitlab_ci:       GitLab CI pipeline YAML
  - generate_dependabot:      Dependabot dependency update config
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


# ── Language-keyed pipeline step templates ───────────────────────────

_LINT_STEPS: dict[str, str] = {
    "python": (
        "      - uses: actions/setup-python@v5\n"
        "        with:\n          python-version: '3.11'\n          cache: pip\n"
        "      - run: pip install flake8 black isort mypy\n"
        "      - run: flake8 . --count --show-source --statistics\n"
        "      - run: black --check .\n"
        "      - run: isort --check-only .\n"
    ),
    "javascript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n          cache: npm\n"
        "      - run: npm ci\n"
        "      - run: npm run lint\n"
        "      - run: npm run format:check\n"
    ),
    "typescript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n          cache: npm\n"
        "      - run: npm ci\n"
        "      - run: npx tsc --noEmit\n"
        "      - run: npm run lint\n"
    ),
    "go": (
        "      - uses: actions/setup-go@v5\n"
        "        with:\n          go-version: '1.21'\n          cache: true\n"
        "      - uses: golangci/golangci-lint-action@v4\n"
        "        with:\n          version: latest\n"
    ),
}

_TEST_STEPS: dict[str, str] = {
    "python": (
        "      - uses: actions/setup-python@v5\n"
        "        with:\n          python-version: '3.11'\n          cache: pip\n"
        "      - run: pip install -r requirements.txt && pip install pytest pytest-cov\n"
        "      - run: pytest tests/ -v --cov=src --cov-report=xml\n"
    ),
    "javascript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n          cache: npm\n"
        "      - run: npm ci\n"
        "      - run: npm run test -- --coverage\n"
    ),
    "typescript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n          cache: npm\n"
        "      - run: npm ci\n"
        "      - run: npm run test -- --coverage\n"
    ),
    "go": (
        "      - uses: actions/setup-go@v5\n"
        "        with:\n          go-version: '1.21'\n          cache: true\n"
        "      - run: go test -v -race -coverprofile=coverage.out ./...\n"
    ),
}

_SECURITY_STEPS: dict[str, str] = {
    "python": (
        "      - uses: actions/setup-python@v5\n"
        "        with:\n          python-version: '3.11'\n"
        "      - run: pip install pip-audit\n"
        "      - run: pip-audit -r requirements.txt --format=json || true\n"
    ),
    "javascript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n"
        "      - run: npm audit --json || true\n"
    ),
    "typescript": (
        "      - uses: actions/setup-node@v4\n"
        "        with:\n          node-version: '20'\n"
        "      - run: npm audit --json || true\n"
    ),
    "go": (
        "      - uses: actions/setup-go@v5\n"
        "        with:\n          go-version: '1.21'\n"
        "      - run: go install golang.org/x/vuln/cmd/govulncheck@latest && govulncheck ./... || true\n"
    ),
}

_DEPENDABOT_ECOSYSTEMS: dict[str, str] = {
    "python": '  - package-ecosystem: "pip"\n    directory: "/"\n    schedule:\n      interval: "weekly"\n',
    "javascript": '  - package-ecosystem: "npm"\n    directory: "/"\n    schedule:\n      interval: "weekly"\n',
    "typescript": '  - package-ecosystem: "npm"\n    directory: "/"\n    schedule:\n      interval: "weekly"\n',
    "go": '  - package-ecosystem: "gomod"\n    directory: "/"\n    schedule:\n      interval: "weekly"\n',
}

_CODEQL_LANGUAGES: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "javascript",
    "go": "go",
}

# ── Language detection patterns ──────────────────────────────────────

_LANG_INDICATORS: dict[str, list[str]] = {
    "python": ["import ", "from ", "def ", "class ", "requirements.txt", "pyproject.toml"],
    "javascript": ["const ", "let ", "require(", "module.exports", "package.json"],
    "typescript": ["interface ", ": string", ": number", "tsconfig.json", "import type"],
    "go": ["package main", "func ", "go.mod", "import ("],
}


class CIAgent(BaseAgent):
    """
    Generates CI pipeline configurations with pattern-based templates
    enhanced by LLM-powered optimization recommendations.
    """

    SYSTEM_PROMPT = """You are a CI/CD pipeline expert specializing in GitHub Actions, GitLab CI,
and modern DevOps practices.

When given a project description and language, you:
1. Recommend optimal CI pipeline stages (lint, test, security, build)
2. Suggest caching strategies for faster builds
3. Identify security scanning tools appropriate for the stack
4. Recommend parallelization opportunities
5. Suggest dependency management best practices

Provide specific, actionable YAML configuration advice."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="ci-pipeline",
            name="CI Pipeline Agent",
            description="Generates CI pipeline configs (GitHub Actions, GitLab CI, Dependabot)",
            version="2.0.0",
            capabilities=[
                AgentCapability(
                    name="generate_github_actions",
                    description="Generate GitHub Actions CI workflow YAML",
                ),
                AgentCapability(
                    name="generate_gitlab_ci",
                    description="Generate GitLab CI pipeline YAML",
                ),
                AgentCapability(
                    name="generate_dependabot",
                    description="Generate Dependabot dependency update configuration",
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["ci", "pipeline", "github-actions", "gitlab-ci", "devops"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Generate CI pipeline configurations.

        ctx.input: project description or source code to analyse
        ctx.params:
          - language: str (python/javascript/typescript/go)
          - platform: str (github/gitlab/all)
          - app_name: str
          - include_dependabot: bool
        """
        code = ctx.input
        language = ctx.params.get("language", "").lower() or self._detect_language(code)
        platform = ctx.params.get("platform", "all").lower()
        app_name = ctx.params.get("app_name", "my-app")
        include_dependabot = ctx.params.get("include_dependabot", True)

        configs: dict[str, str] = {}

        # ── Pattern-based generation ──
        if platform in ("github", "all"):
            configs["github_actions"] = self._generate_github_actions(language, app_name)

        if platform in ("gitlab", "all"):
            configs["gitlab_ci"] = self._generate_gitlab_ci(language, app_name)

        if include_dependabot and platform in ("github", "all"):
            configs["dependabot"] = self._generate_dependabot_config(language)

        # ── LLM enhancement ──
        llm_recommendations = None
        try:
            prompt = self._build_optimisation_prompt(code, language, platform, app_name)
            llm_response = await self.call_llm(ctx, prompt)
            llm_recommendations = llm_response.content
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM optimisation unavailable: %s", exc)
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        return {
            "configs": configs,
            "language": language,
            "platform": platform,
            "app_name": app_name,
            "files_generated": len(configs),
            "llm_recommendations": llm_recommendations,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.9 if llm_recommendations else 0.7,
        }

    # ── Language Detection ───────────────────────────────────────────

    def _detect_language(self, code: str) -> str:
        """Detect primary language from code content."""
        scores: dict[str, int] = {}
        for lang, indicators in _LANG_INDICATORS.items():
            score = sum(1 for ind in indicators if ind in code)
            if score > 0:
                scores[lang] = score
        return max(scores, key=scores.get) if scores else "python"

    # ── GitHub Actions Generation ────────────────────────────────────

    def _generate_github_actions(self, language: str, app_name: str) -> str:
        """Generate a GitHub Actions CI workflow."""
        lint = _LINT_STEPS.get(language, _LINT_STEPS["python"])
        test = _TEST_STEPS.get(language, _TEST_STEPS["python"])
        security = _SECURITY_STEPS.get(language, _SECURITY_STEPS["python"])

        return (
            f"name: CI Pipeline\n\n"
            f"on:\n  push:\n    branches: [main, develop]\n"
            f"  pull_request:\n    branches: [main]\n\n"
            f"concurrency:\n  group: ci-${{{{ github.ref }}}}\n  cancel-in-progress: true\n\n"
            f"jobs:\n"
            f"  lint:\n    name: Lint\n    runs-on: ubuntu-latest\n    steps:\n"
            f"      - uses: actions/checkout@v4\n{lint}\n"
            f"  security:\n    name: Security Scan\n    runs-on: ubuntu-latest\n    steps:\n"
            f"      - uses: actions/checkout@v4\n{security}\n"
            f"  test:\n    name: Test\n    runs-on: ubuntu-latest\n"
            f"    needs: [lint, security]\n    steps:\n"
            f"      - uses: actions/checkout@v4\n{test}\n"
            f"  build:\n    name: Build\n    runs-on: ubuntu-latest\n"
            f"    needs: test\n"
            f"    if: github.ref == 'refs/heads/main' && github.event_name == 'push'\n"
            f"    steps:\n      - uses: actions/checkout@v4\n"
            f"      - uses: docker/setup-buildx-action@v3\n"
            f"      - uses: docker/build-push-action@v6\n"
            f"        with:\n          context: .\n          push: false\n"
            f"          tags: {app_name}:${{{{ github.sha }}}}\n"
            f"          cache-from: type=gha\n          cache-to: type=gha,mode=max\n"
        )

    # ── GitLab CI Generation ─────────────────────────────────────────

    def _generate_gitlab_ci(self, language: str, app_name: str) -> str:
        """Generate a GitLab CI pipeline."""
        image_map = {
            "python": "python:3.11-slim",
            "javascript": "node:20-alpine",
            "typescript": "node:20-alpine",
            "go": "golang:1.21",
        }
        default_image = image_map.get(language, "python:3.11-slim")

        return (
            f"stages:\n  - lint\n  - test\n  - security\n  - build\n\n"
            f"default:\n  image: {default_image}\n\n"
            f"lint:\n  stage: lint\n  script:\n"
            f"    - echo 'Running linters for {language}'\n\n"
            f"test:unit:\n  stage: test\n  script:\n"
            f"    - echo 'Running tests for {language}'\n"
            f"  coverage: '/TOTAL.*\\s+(\\d+%)/' \n\n"
            f"security:sast:\n  stage: security\n"
            f"  image: returntocorp/semgrep\n"
            f"  script:\n    - semgrep --config=auto .\n"
            f"  allow_failure: true\n\n"
            f"build:docker:\n  stage: build\n"
            f"  image: docker:stable\n  services:\n    - docker:dind\n"
            f"  script:\n    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .\n"
            f"  rules:\n    - if: $CI_COMMIT_BRANCH == 'main'\n"
        )

    # ── Dependabot Config ────────────────────────────────────────────

    def _generate_dependabot_config(self, language: str) -> str:
        """Generate Dependabot configuration."""
        ecosystem = _DEPENDABOT_ECOSYSTEMS.get(language, _DEPENDABOT_ECOSYSTEMS["python"])
        return (
            f"version: 2\nupdates:\n"
            f'  - package-ecosystem: "github-actions"\n'
            f'    directory: "/"\n    schedule:\n      interval: "weekly"\n'
            f"    commit-message:\n      prefix: \"ci(deps)\"\n\n"
            f"{ecosystem}"
            f"    commit-message:\n      prefix: \"chore(deps)\"\n"
        )

    # ── LLM Prompt ───────────────────────────────────────────────────

    def _build_optimisation_prompt(
        self, code: str, language: str, platform: str, app_name: str,
    ) -> str:
        """Build prompt for LLM pipeline optimisation."""
        return (
            f"Analyze this {language} project '{app_name}' and recommend CI pipeline optimizations.\n\n"
            f"Platform: {platform}\n"
            f"Language: {language}\n\n"
            f"Project code/description:\n```\n{code[:3000]}\n```\n\n"
            f"Provide specific recommendations for:\n"
            f"1. Build caching strategy\n"
            f"2. Test parallelization\n"
            f"3. Security scanning tools\n"
            f"4. Pipeline stage ordering\n"
            f"5. Any language-specific best practices\n"
        )
