"""
SevaForge Deploy Validator Agent

Post-orchestrator validation gate that cross-checks deployment artifacts
for consistency before the push stage.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime
from typing import Any

from sevaforge.agents.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)

logger = logging.getLogger(__name__)

_CRON_REGEX = re.compile(r"^(\S+\s+){4}\S+$")
_TERRAFORM_VAR_DECL = re.compile(r'variable\s+"(\w+)"')
_TERRAFORM_VAR_REF = re.compile(r"var\.(\w+)")
_SECRET_REF_PATTERNS = [
    re.compile(r"\$\{\{\s*secrets\.(\w+)\s*\}\}"),
    re.compile(r"secret(?:Ref)?:\s*(\w+)"),
    re.compile(r"os\.(?:environ|getenv)\(\s*['\"](\w+)"),
    re.compile(r"process\.env\.(\w+)"),
]
CLOUD_REGISTRY_MAP: dict[str, str] = {"gcp": "gcr.io/", "aws": ".dkr.ecr.", "azure": ".azurecr.io/", "oci": ".ocir.io/"}


class DeployValidatorAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a deployment validation engineer. Explain clearly why checks fail and provide actionable steps to fix."

    def __init__(self) -> None:
        super().__init__(AgentConfig(
            agent_id="deploy-validator",
            name="Deploy Validator Agent",
            description="Post-orchestrator validation gate",
            version="2.0.0",
            capabilities=[
                AgentCapability(name="validate_secrets", description="Check secrets inventory consistency"),
                AgentCapability(name="validate_terraform", description="Verify Terraform variable declarations"),
                AgentCapability(name="validate_configs", description="Run cron, date, SLO, and image repo checks"),
                AgentCapability(name="full_validation", description="Execute all 7 validation checks"),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["deployment", "validation", "secrets", "terraform", "compliance"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        action = ctx.params.get("action", "full")
        intent = ctx.params.get("intent", {})
        if action == "secrets":
            result = self._check_secrets_consistency(intent, ctx.input)
            return self._wrap_single_check("secrets_consistency", result, ctx)
        if action == "terraform":
            tf_code = ctx.params.get("terraform_code", ctx.input)
            result = self._check_terraform_vars(tf_code)
            return self._wrap_single_check("terraform_vars_declared", result, ctx)
        if action == "configs":
            return self._run_config_checks(intent, ctx)
        return await self._run_full_validation(ctx, intent)

    async def _run_full_validation(self, ctx, intent):
        code = ctx.input
        tf_code = ctx.params.get("terraform_code", "")
        helm_values = ctx.params.get("helm_values", {})
        checks = [
            ("secrets_consistency", self._check_secrets_consistency(intent, code)),
            ("cron_schedules_valid", self._check_cron_schedules(intent)),
            ("dates_are_future", self._check_dates(intent)),
            ("slo_realistic", self._check_slo(intent)),
            ("intent_hash_matches", self._check_intent_hash(intent)),
            ("terraform_vars_declared", self._check_terraform_vars(tf_code)),
            ("image_repo_matches_cloud", self._check_image_repo(intent, helm_values)),
        ]
        passed = [name for name, (ok, _) in checks if ok]
        failed = [(name, msg) for name, (ok, msg) in checks if not ok]
        failure_analysis = None
        model_used = "pattern-only"
        input_tokens = output_tokens = 0
        if failed:
            try:
                llm_response = await self.call_llm(ctx, self._build_failure_prompt(failed, intent))
                failure_analysis = llm_response.content
                model_used = llm_response.model
                input_tokens = llm_response.input_tokens
                output_tokens = llm_response.output_tokens
            except Exception:
                pass
        return {"valid": len(failed) == 0, "checks_total": len(checks), "checks_passed": len(passed), "checks_failed": len(failed), "passed": passed, "failed": [{"check": n, "error": m} for n, m in failed], "failure_analysis": failure_analysis, "model_used": model_used, "input_tokens": input_tokens, "output_tokens": output_tokens, "confidence": 1.0 if not failed else 0.9}

    def _check_secrets_consistency(self, intent, code):
        secrets_list = intent.get("secrets", [])
        if not secrets_list:
            return (True, "")
        inventoried = {s["name"] for s in secrets_list if isinstance(s, dict) and "name" in s}
        stale = {name for name in inventoried if name not in code}
        if stale:
            return (False, f"Inventoried but never referenced: {sorted(stale)}")
        return (True, "")

    def _check_cron_schedules(self, intent):
        shutdown = intent.get("cost_controls", {}).get("auto_shutdown", {})
        if not shutdown.get("enabled"):
            return (True, "")
        for name in ("schedule_down", "schedule_up"):
            expr = shutdown.get(name, "")
            if not expr or not _CRON_REGEX.match(expr.strip()):
                return (False, f"{name} is not a valid 5-field cron: {expr!r}")
        return (True, "")

    def _check_dates(self, intent):
        td = intent.get("cost_controls", {}).get("teardown_date", "")
        if not td:
            return (True, "")
        try:
            d = datetime.fromisoformat(td).date()
        except (ValueError, TypeError):
            return (False, f"teardown_date is not ISO: {td!r}")
        if d <= date.today():
            return (False, f"teardown_date is in the past: {td}")
        return (True, "")

    def _check_slo(self, intent):
        slo = intent.get("observability", {}).get("slo", {})
        avail = slo.get("availability_target")
        if avail is not None and not (0 < avail <= 100):
            return (False, f"availability_target must be in (0, 100], got {avail}")
        p99 = slo.get("latency_p99_ms")
        if p99 is not None and p99 <= 0:
            return (False, f"latency_p99_ms must be > 0, got {p99}")
        return (True, "")

    def _check_intent_hash(self, intent):
        stored = intent.get("_meta", {}).get("intent_hash")
        if not stored:
            return (True, "")
        intent_copy = {k: v for k, v in intent.items() if k != "_meta"}
        computed = hashlib.sha256(json.dumps(intent_copy, sort_keys=True).encode()).hexdigest()
        if stored != computed:
            return (False, "intent was edited after design")
        return (True, "")

    def _check_terraform_vars(self, tf_code):
        if not tf_code.strip():
            return (True, "")
        declared = set(_TERRAFORM_VAR_DECL.findall(tf_code))
        referenced = set(_TERRAFORM_VAR_REF.findall(tf_code))
        missing = referenced - declared
        if missing:
            return (False, f"Undeclared variables: {sorted(missing)}")
        return (True, "")

    def _check_image_repo(self, intent, helm_values):
        cloud = intent.get("cloud", {}).get("provider", "")
        repo = (helm_values.get("image") or {}).get("repository", "")
        if not repo or not cloud:
            return (True, "")
        expected = CLOUD_REGISTRY_MAP.get(cloud)
        if expected and expected not in repo:
            return (False, f"image.repository '{repo}' doesn't match {cloud} registry")
        return (True, "")

    def _wrap_single_check(self, check_name, result, ctx):
        ok, msg = result
        return {"valid": ok, "check": check_name, "error": msg if not ok else None, "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 1.0}

    def _run_config_checks(self, intent, ctx):
        helm_values = ctx.params.get("helm_values", {})
        checks = [("cron_schedules_valid", self._check_cron_schedules(intent)), ("dates_are_future", self._check_dates(intent)), ("slo_realistic", self._check_slo(intent)), ("image_repo_matches_cloud", self._check_image_repo(intent, helm_values))]
        passed = [n for n, (ok, _) in checks if ok]
        failed = [(n, m) for n, (ok, m) in checks if not ok]
        return {"valid": len(failed) == 0, "passed": passed, "failed": [{"check": n, "error": m} for n, m in failed], "model_used": "pattern-only", "input_tokens": 0, "output_tokens": 0, "confidence": 1.0}

    def _build_failure_prompt(self, failed, intent):
        lines = "\n".join(f"  - {n}: {m}" for n, m in failed)
        cloud = intent.get("cloud", {}).get("provider", "unknown")
        return f"The following validation checks failed:\n{lines}\n\nTarget: {cloud}\n\nFor each failure, explain why it matters and provide the exact fix."
