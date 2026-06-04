"""
SevaForge Deploy Intent Agent

Pre-deployment interview agent that captures deployment intent through
code analysis and structured questionnaire. Produces a canonical intent
document consumed by all downstream deploy-design agents.

Capabilities:
  - capture_intent:    Conduct deployment interview and collect answers
  - derive_app_facts:  Infer app name, language, port from code patterns
  - validate_intent:   Validate a completed intent document for consistency
"""

from __future__ import annotations

import hashlib
import json
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


# ── Option Tables & Defaults ───────────────────────────────────────

CLOUD_OPTIONS = ["gcp", "aws", "azure", "oci"]
COMPUTE_MODELS = ["kubernetes", "serverless", "vm"]

COMPUTE_FLAVOURS: dict[str, dict[str, str]] = {
    "kubernetes": {"gcp": "gke-autopilot", "aws": "eks", "azure": "aks", "oci": "oke"},
    "vm":         {"gcp": "gce", "aws": "ec2", "azure": "azure-vm", "oci": "oci-compute"},
    "serverless": {"gcp": "cloud-run", "aws": "lambda", "azure": "container-apps", "oci": "functions"},
}

DEFAULT_REGIONS: dict[str, str] = {
    "gcp": "us-central1",
    "aws": "us-east-1",
    "azure": "eastus",
    "oci": "us-ashburn-1",
}

OBSERVABILITY_STACKS = ["prometheus-grafana", "datadog", "cloud-native", "minimal"]

LANGUAGE_INDICATORS: dict[str, list[str]] = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "node":   ["package.json"],
    "go":     ["go.mod"],
    "java":   ["pom.xml", "build.gradle"],
    "ruby":   ["Gemfile"],
    "rust":   ["Cargo.toml"],
}

DEFAULT_PORTS: dict[str, int] = {
    "python": 8000, "node": 3000, "go": 8080,
    "java": 8080, "ruby": 3000, "rust": 8080, "other": 8080,
}

# ── Detection Patterns ─────────────────────────────────────────────

_PORT_PATTERNS = [
    re.compile(r"PORT\s*=\s*(\d+)"),
    re.compile(r"listen\s*\(\s*(\d+)"),
    re.compile(r"port:\s*(\d+)"),
    re.compile(r"--port[= ](\d+)"),
    re.compile(r"\.bind\(\s*['\"].*:(\d+)"),
]

_APP_NAME_PATTERNS = [
    re.compile(r'"name"\s*:\s*"([^"]+)"'),          # package.json
    re.compile(r"name\s*=\s*['\"]([^'\"]+)['\"]"),   # pyproject.toml / setup.py
    re.compile(r"module\s+(\S+)"),                    # go.mod
]

_LANGUAGE_FILE_PATTERNS: dict[str, re.Pattern[str]] = {
    "python": re.compile(r"\.(py)$"),
    "node":   re.compile(r"\.(js|ts|tsx)$"),
    "go":     re.compile(r"\.(go)$"),
    "java":   re.compile(r"\.(java|kt)$"),
    "ruby":   re.compile(r"\.(rb)$"),
    "rust":   re.compile(r"\.(rs)$"),
}

# ── Intent Document Schema ─────────────────────────────────────────

_INTENT_SECTIONS = [
    "app", "cloud", "compute", "environments",
    "secrets", "observability", "security", "cost_controls", "ci_cd",
]

_CLOUD_BASELINE_SECRETS: dict[str, list[dict[str, Any]]] = {
    "gcp": [
        {"name": "GCP_SA_KEY", "description": "JSON key for deployer service account", "required_by": ["infra", "cluster"]},
        {"name": "GCP_PROJECT_ID", "description": "GCP project id", "required_by": ["infra", "cluster", "app"]},
        {"name": "GCP_REGION", "description": "Primary GCP region", "required_by": ["infra"]},
    ],
    "aws": [
        {"name": "AWS_ACCESS_KEY_ID", "description": "IAM user access key", "required_by": ["infra", "cluster"]},
        {"name": "AWS_SECRET_ACCESS_KEY", "description": "IAM user secret", "required_by": ["infra", "cluster"]},
        {"name": "AWS_REGION", "description": "AWS region", "required_by": ["infra"]},
        {"name": "AWS_ACCOUNT_ID", "description": "12-digit AWS account id", "required_by": ["infra"]},
    ],
    "azure": [
        {"name": "AZURE_CREDENTIALS", "description": "Service principal JSON", "required_by": ["infra", "cluster"]},
        {"name": "AZURE_SUBSCRIPTION_ID", "description": "Azure subscription uuid", "required_by": ["infra"]},
    ],
    "oci": [
        {"name": "OCI_TENANCY_OCID", "description": "Tenancy OCID", "required_by": ["infra"]},
        {"name": "OCI_USER_OCID", "description": "User OCID for deployer", "required_by": ["infra"]},
        {"name": "OCI_FINGERPRINT", "description": "API key fingerprint", "required_by": ["infra"]},
        {"name": "OCI_PRIVATE_KEY", "description": "Base64-encoded private key PEM", "required_by": ["infra"]},
        {"name": "OCI_REGION", "description": "OCI region", "required_by": ["infra"]},
        {"name": "OCI_COMPARTMENT_ID", "description": "Compartment OCID", "required_by": ["infra"]},
    ],
}


class DeployIntentAgent(BaseAgent):
    """
    Pre-deployment interview agent.

    Analyzes code to derive application facts, then captures the full
    deployment intent (cloud, compute, environments, observability,
    security, cost controls) via structured parameters or LLM-assisted
    recommendation.
    """

    SYSTEM_PROMPT = (
        "You are a deployment architect conducting a pre-deployment interview.\n"
        "Given code analysis results and user preferences, recommend the optimal\n"
        "deployment configuration. Consider:\n"
        "1. Language and framework best practices for containerization\n"
        "2. Cloud provider strengths for the workload type\n"
        "3. Cost optimization (right-sizing, spot instances, autoscaling)\n"
        "4. Security posture (least privilege, network policies, image scanning)\n"
        "5. Observability stack that matches team maturity\n"
        "6. Environment promotion strategy (dev -> staging -> prod)\n\n"
        "Be specific with recommendations. Include concrete values for replicas,\n"
        "resource limits, SLO targets, and autoscaling thresholds."
    )

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="deploy-intent",
            name="Deploy Intent Agent",
            description="Pre-deployment interview agent — captures deployment intent from code analysis",
            version="2.0.0",
            capabilities=[
                AgentCapability(
                    name="capture_intent",
                    description="Conduct deployment interview and assemble intent document",
                    input_schema={"type": "object", "properties": {"code": {"type": "string"}, "answers": {"type": "object"}}},
                    output_schema={"type": "object", "properties": {"intent": {"type": "object"}, "cached": {"type": "boolean"}}},
                ),
                AgentCapability(
                    name="derive_app_facts",
                    description="Infer app name, language, and port from code patterns",
                    input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
                    output_schema={"type": "object", "properties": {"app_name": {"type": "string"}, "language": {"type": "string"}, "port": {"type": "integer"}}},
                ),
                AgentCapability(
                    name="validate_intent",
                    description="Validate a completed intent document for structural correctness",
                    input_schema={"type": "object", "properties": {"intent": {"type": "object"}}},
                    output_schema={"type": "object", "properties": {"valid": {"type": "boolean"}, "errors": {"type": "array"}}},
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["deployment", "intent", "interview", "cloud", "infrastructure"],
        ))

    # ── Execute ─────────────────────────────────────────────────────

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        action = ctx.params.get("action", "capture")

        if action == "derive":
            return self._derive_app_facts(ctx.input)

        if action == "validate":
            intent = ctx.params.get("intent", {})
            return self._validate_intent_document(intent)

        return await self._capture_intent(ctx)

    async def _capture_intent(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        code = ctx.input
        answers = ctx.params.get("answers", {})
        derived = self._derive_app_facts(code)
        captured = self._merge_answers(derived, answers)
        prompt = self._build_recommendation_prompt(code, derived, captured)
        try:
            llm_response = await self.call_llm(ctx, prompt)
            recommendations = llm_response.content
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM unavailable for intent recommendations: %s", exc)
            recommendations = None
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        intent = self._assemble_intent(derived, captured)

        return {
            "intent": intent,
            "derived_facts": derived,
            "recommendations": recommendations,
            "cached": False,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.85 if recommendations else 0.6,
        }

    def _derive_app_facts(self, code: str) -> dict[str, Any]:
        language = "other"
        lang_scores: dict[str, int] = {}
        for lang, pattern in _LANGUAGE_FILE_PATTERNS.items():
            count = len(pattern.findall(code))
            if count > 0:
                lang_scores[lang] = count
        for lang, markers in LANGUAGE_INDICATORS.items():
            for marker in markers:
                if marker in code:
                    lang_scores[lang] = lang_scores.get(lang, 0) + 5
        if lang_scores:
            language = max(lang_scores, key=lang_scores.get)  # type: ignore[arg-type]

        app_name = "app"
        for pattern in _APP_NAME_PATTERNS:
            m = pattern.search(code)
            if m:
                app_name = self._sanitize_name(m.group(1))
                break

        port = DEFAULT_PORTS.get(language, 8080)
        for pattern in _PORT_PATTERNS:
            m = pattern.search(code)
            if m:
                try:
                    port = int(m.group(1))
                except ValueError:
                    pass
                break

        return {"app_name": app_name, "language": language, "port": port}

    @staticmethod
    def _sanitize_name(name: str) -> str:
        s = re.sub(r"[^a-zA-Z0-9-]", "-", name).strip("-").lower()
        return s or "app"

    def _merge_answers(self, derived: dict[str, Any], answers: dict[str, Any]) -> dict[str, Any]:
        provider = answers.get("cloud_provider", "gcp")
        compute = answers.get("compute_model", "kubernetes")
        replicas = int(answers.get("compute_replicas", 2))

        return {
            "cloud_provider": provider,
            "cloud_project_id": answers.get("cloud_project_id", ""),
            "cloud_region": answers.get("cloud_region", DEFAULT_REGIONS.get(provider, "us-central1")),
            "compute_model": compute,
            "compute_flavour": answers.get("compute_flavour", COMPUTE_FLAVOURS.get(compute, {}).get(provider, "")),
            "compute_replicas": replicas,
            "autoscale_enabled": answers.get("autoscale_enabled", True),
            "autoscale_min": int(answers.get("autoscale_min", replicas)),
            "autoscale_max": int(answers.get("autoscale_max", replicas * 3)),
            "env_names": answers.get("env_names", ["dev", "prod"]),
            "auto_promote_devs": answers.get("auto_promote_devs", True),
            "approval_envs": answers.get("approval_envs", ["prod"]),
            "healthcheck_path": answers.get("healthcheck_path", "/health"),
            "observability_stack": answers.get("observability_stack", "prometheus-grafana"),
            "observability_metrics": answers.get("observability_metrics", True),
            "observability_logs": answers.get("observability_logs", True),
            "observability_traces": answers.get("observability_traces", False),
            "slo_availability": float(answers.get("slo_availability", 99.5)),
            "slo_p99_ms": int(answers.get("slo_p99_ms", 500)),
            "security_netpol": answers.get("security_netpol", compute == "kubernetes"),
            "security_image_scan": answers.get("security_image_scan", True),
            "security_iam_least_priv": answers.get("security_iam_least_priv", True),
            "security_sbom": answers.get("security_sbom", False),
            "cost_budget_usd": float(answers.get("cost_budget_usd", 0)),
            "cost_shutdown_enabled": answers.get("cost_shutdown_enabled", True),
            "schedule_down": answers.get("schedule_down", "0 4 * * *"),
            "schedule_up": answers.get("schedule_up", "0 14 * * *"),
            "teardown_date": answers.get("teardown_date", ""),
            "cicd_platform": answers.get("cicd_platform", "github-actions"),
            "cicd_use_argocd": answers.get("cicd_use_argocd", False),
        }

    def _assemble_intent(self, derived: dict[str, Any], captured: dict[str, Any]) -> dict[str, Any]:
        environments = []
        for name in captured["env_names"]:
            environments.append({
                "name": name,
                "auto_promote": (name not in captured["approval_envs"]) and captured["auto_promote_devs"],
            })

        common_secret = {"name": "GH_TOKEN", "description": "GitHub PAT for CI/CD", "required_by": ["ci_cd", "infra"]}
        cloud_secrets = [common_secret] + _CLOUD_BASELINE_SECRETS.get(captured["cloud_provider"], [])

        intent: dict[str, Any] = {
            "version": 1,
            "app": {"name": derived["app_name"], "language": derived["language"], "port": derived["port"], "healthcheck_path": captured["healthcheck_path"]},
            "cloud": {"provider": captured["cloud_provider"], "project_id": captured["cloud_project_id"], "region": captured["cloud_region"]},
            "compute": {"model": captured["compute_model"], "flavour": captured["compute_flavour"], "replicas": captured["compute_replicas"], "autoscale": {"enabled": captured["autoscale_enabled"], "min": captured["autoscale_min"], "max": captured["autoscale_max"]}},
            "environments": environments,
            "secrets": cloud_secrets,
            "observability": {"stack": captured["observability_stack"], "metrics": captured["observability_metrics"], "logs": captured["observability_logs"], "traces": captured["observability_traces"], "slo": {"availability_target": captured["slo_availability"], "latency_p99_ms": captured["slo_p99_ms"]}},
            "security": {"network_policies": captured["security_netpol"], "image_scanning": captured["security_image_scan"], "iam_least_privilege": captured["security_iam_least_priv"], "sbom": captured["security_sbom"]},
            "cost_controls": {"budget_usd_monthly": captured["cost_budget_usd"], "auto_shutdown": {"enabled": captured["cost_shutdown_enabled"], "schedule_down": captured["schedule_down"], "schedule_up": captured["schedule_up"]}, "teardown_date": captured["teardown_date"]},
            "ci_cd": {"platform": captured["cicd_platform"], "use_argocd": captured["cicd_use_argocd"], "require_approval_for": captured["approval_envs"]},
        }

        payload_for_hash = json.dumps(intent, sort_keys=True).encode()
        intent["_meta"] = {
            "created_by": "deploy-intent-agent",
            "intent_hash": hashlib.sha256(payload_for_hash).hexdigest(),
            "last_validated": None,
        }
        return intent

    def _validate_intent_document(self, intent: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        for section in _INTENT_SECTIONS:
            if section not in intent:
                errors.append(f"Missing required section: {section}")
        cloud = intent.get("cloud", {})
        if cloud.get("provider") and cloud["provider"] not in CLOUD_OPTIONS:
            errors.append(f"Unknown cloud provider: {cloud['provider']}")
        compute = intent.get("compute", {})
        if compute.get("model") and compute["model"] not in COMPUTE_MODELS:
            errors.append(f"Unknown compute model: {compute['model']}")
        slo = intent.get("observability", {}).get("slo", {})
        avail = slo.get("availability_target")
        if avail is not None and not (0 < avail <= 100):
            errors.append(f"availability_target must be in (0, 100], got {avail}")
        p99 = slo.get("latency_p99_ms")
        if p99 is not None and p99 <= 0:
            errors.append(f"latency_p99_ms must be > 0, got {p99}")
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "sections_present": [s for s in _INTENT_SECTIONS if s in intent],
            "model_used": "validation",
            "input_tokens": 0,
            "output_tokens": 0,
            "confidence": 1.0,
        }

    def _build_recommendation_prompt(self, code: str, derived: dict[str, Any], captured: dict[str, Any]) -> str:
        return (
            f"Analyze this {derived['language']} application and recommend deployment optimizations.\n\n"
            f"Derived facts:\n"
            f"  - App: {derived['app_name']}\n"
            f"  - Language: {derived['language']}\n"
            f"  - Port: {derived['port']}\n\n"
            f"Current configuration:\n"
            f"  - Cloud: {captured['cloud_provider']} / {captured['cloud_region']}\n"
            f"  - Compute: {captured['compute_model']} ({captured['compute_flavour']})\n"
            f"  - Replicas: {captured['compute_replicas']} (autoscale {captured['autoscale_min']}-{captured['autoscale_max']})\n"
            f"  - Observability: {captured['observability_stack']}\n"
            f"  - SLO: {captured['slo_availability']}% availability, {captured['slo_p99_ms']}ms p99\n\n"
            f"Code sample:\n```{derived['language']}\n{code[:3000]}\n```\n\n"
            f"Provide:\n"
            f"1. Resource sizing recommendations (CPU, memory limits)\n"
            f"2. Autoscaling policy tuning\n"
            f"3. Security hardening suggestions specific to this stack\n"
            f"4. Cost optimization opportunities\n"
            f"5. Any configuration concerns or anti-patterns detected"
        )
