#!/usr/bin/env python3
"""
ForgeFlow Deploy Intent Agent
==============================
Pre-push stage. Runs an interactive interview (or consumes an answers file in
non-interactive mode) to capture the user's deployment intent. Produces
`.sevaforge/deployment-intent.yaml` — the canonical input for all persona
agents in the deploy-design stage.

Caching: once generated, subsequent pushes skip this agent unless the user
runs `forgeflow deploy-reconfigure` which deletes the cached intent.

Architecture:
  forgeflow deploy-intent <path> → intent_mcp → DeployIntentAgent
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .base_agent import BaseAgent


# =============================================================================
# Defaults and option tables
# =============================================================================

CLOUD_OPTIONS = ["gcp", "aws", "azure", "oci"]
COMPUTE_MODELS = ["kubernetes", "vm", "serverless"]
COMPUTE_FLAVOURS = {
    "kubernetes": {
        "gcp": "gke-autopilot",
        "aws": "eks",
        "azure": "aks",
        "oci": "oke",
    },
    "vm": {
        "gcp": "gce",
        "aws": "ec2",
        "azure": "azure-vm",
        "oci": "oci-compute",
    },
    "serverless": {
        "gcp": "cloud-run",
        "aws": "lambda",
        "azure": "container-apps",
        "oci": "functions",
    },
}
OBSERVABILITY_STACKS = ["prometheus-grafana", "datadog", "cloud-native", "minimal"]
CICD_PLATFORMS = ["github-actions", "gitlab-ci", "circleci"]

LANGUAGE_INDICATORS = {
    "python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "node": ["package.json"],
    "go": ["go.mod"],
    "java": ["pom.xml", "build.gradle"],
    "ruby": ["Gemfile"],
    "rust": ["Cargo.toml"],
}

DEFAULT_PORTS = {
    "python": 8000,
    "node": 3000,
    "go": 8080,
    "java": 8080,
    "ruby": 3000,
    "rust": 8080,
    "other": 8080,
}


# =============================================================================
# DeployIntentAgent
# =============================================================================

class DeployIntentAgent(BaseAgent):
    """Conducts the pre-push deployment interview and produces intent.yaml."""

    intelligence_phase = 1
    intelligence_label = "Assisted"

    INTENT_DIR = ".sevaforge"
    INTENT_FILE = "deployment-intent.yaml"

    def __init__(self):
        super().__init__(
            name="deploy_intent_agent",
            description="Interactive deployment interview, produces deployment-intent.yaml"
        )

    # --------------------------------------------------------------------- API

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the interview (or load answers from file) and write intent.yaml.

        Params:
            path: project root (required)
            answers: dict of pre-supplied answers (optional, bypasses prompts)
            force: bool, regenerate even if cached intent exists (default False)
            interactive: bool, whether to prompt on stdin (default True)

        Returns standard agent result with:
            data.intent_path: path to the written intent file
            data.intent: the intent document
            data.cached: whether an existing intent was reused
        """
        project_path = Path(params["path"]).resolve()
        force = bool(params.get("force", False))
        interactive = bool(params.get("interactive", True))
        answers = params.get("answers") or {}

        intent_dir = project_path / self.INTENT_DIR
        intent_path = intent_dir / self.INTENT_FILE

        # Cached intent short-circuits unless force
        if intent_path.exists() and not force:
            intent = yaml.safe_load(intent_path.read_text())
            self.log(f"Reusing cached intent at {intent_path}")
            return self.create_result(
                status="success",
                summary="Reused cached deployment intent",
                data={
                    "intent_path": str(intent_path),
                    "intent": intent,
                    "cached": True,
                },
            )

        # ── Phase 3: Load run history for smart defaults ─────────────────
        try:
            from core.run_history import RunHistory
            history = RunHistory(project_path)
            past_suggestions = history.suggest_intent_defaults()
            if past_suggestions:
                self.log(f"Loaded {len(past_suggestions)} smart defaults from run history")
        except Exception:
            history = None
            past_suggestions = {}

        # Derive app facts
        derived = self._derive_app_facts(project_path)
        self.log(f"Derived app facts: {derived}")

        # Run interview (or consume answers) — pass smart defaults
        captured = self._conduct_interview(derived, answers, interactive,
                                           smart_defaults=past_suggestions)

        # Assemble the intent document
        intent = self._assemble_intent(derived, captured)

        # ── Phase 3: Record choices in run history ───────────────────────
        if history is not None:
            try:
                history.record_intent_choices(captured)
                # Track which suggestions were accepted vs changed
                for key, suggestion in past_suggestions.items():
                    accepted = (key in captured and captured[key] == suggestion["value"])
                    history.record_suggestion("deploy-intent", accepted)
                history.save()
            except Exception:
                pass  # Don't break the pipeline for history failures

        # Write it
        intent_dir.mkdir(parents=True, exist_ok=True)
        intent_path.write_text(yaml.safe_dump(intent, sort_keys=False))
        self.log(f"Wrote deployment intent to {intent_path}")

        return self.create_result(
            status="success",
            summary=f"Captured deployment intent for {intent['app']['name']} "
                    f"→ {intent['cloud']['provider']}/{intent['compute']['flavour']}",
            data={
                "intent_path": str(intent_path),
                "intent": intent,
                "cached": False,
                "smart_defaults_used": len(past_suggestions),
            },
            actions=[{"action": "created", "file": str(intent_path.relative_to(project_path))}],
        )

    # --------------------------------------------------------------- Derivation

    def _derive_app_facts(self, project_path: Path) -> Dict[str, Any]:
        """Infer app name, language, port from the code on disk."""
        # App name
        package_json = project_path / "package.json"
        pyproject = project_path / "pyproject.toml"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                app_name = data.get("name", project_path.name)
            except Exception:
                app_name = project_path.name
        elif pyproject.exists():
            m = re.search(r'name\s*=\s*"([^"]+)"', pyproject.read_text())
            app_name = m.group(1) if m else project_path.name
        else:
            app_name = project_path.name

        # Language
        language = "other"
        for lang, markers in LANGUAGE_INDICATORS.items():
            if any((project_path / m).exists() for m in markers):
                language = lang
                break

        # Port (grep for common patterns)
        port = DEFAULT_PORTS.get(language, 8080)
        port_patterns = [
            (r"PORT\s*=\s*(\d+)", 1),
            (r'listen\s*\(\s*(\d+)', 1),
            (r"port:\s*(\d+)", 1),
        ]
        for pattern, group in port_patterns:
            for code_file in list(project_path.rglob("*.py"))[:20] + \
                             list(project_path.rglob("*.js"))[:20] + \
                             list(project_path.rglob("*.go"))[:20]:
                try:
                    content = code_file.read_text(errors="ignore")
                    m = re.search(pattern, content)
                    if m:
                        port = int(m.group(group))
                        break
                except Exception:
                    continue
            else:
                continue
            break

        return {
            "app_name": self._sanitize_name(app_name),
            "language": language,
            "port": port,
        }

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Normalise to kebab-case, alnum+hyphen only."""
        s = re.sub(r"[^a-zA-Z0-9-]", "-", name).strip("-").lower()
        return s or "app"

    # --------------------------------------------------------------- Interview

    def _conduct_interview(
        self,
        derived: Dict[str, Any],
        answers: Dict[str, Any],
        interactive: bool,
        smart_defaults: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect answers either from the provided dict or via stdin prompts.

        Phase 3 (Augmented Intelligence): when smart_defaults is provided
        (from run history), past values are used as defaults instead of
        hard-coded ones. The prompt shows a 🧠 icon for learned defaults
        so the user knows the suggestion comes from their history.
        """
        smart_defaults = smart_defaults or {}

        def _smart_default(key: str, fallback: Any) -> Any:
            """Return learned default from history if available, else fallback."""
            if key in smart_defaults:
                return smart_defaults[key]["value"]
            return fallback

        def _smart_hint(key: str) -> str:
            """Return a confidence hint for smart defaults."""
            if key in smart_defaults:
                conf = smart_defaults[key]["confidence"]
                n = smart_defaults[key].get("times_used", 0)
                if conf == "stable":
                    return f" 🧠 (learned — used {n}× consistently)"
                elif conf == "recent":
                    return f" 🧠 (from last run)"
                else:
                    return " 🧠 (varies)"
            return ""

        def ask(key: str, prompt: str, default: Any, choices: Optional[List[str]] = None):
            # Pre-supplied answer wins
            if key in answers:
                return answers[key]
            # Smart default overrides hard-coded default
            effective_default = _smart_default(key, default)
            if not interactive:
                return effective_default
            hint = f" [{effective_default}]" if effective_default is not None else ""
            if choices:
                hint = f" ({'/'.join(choices)})" + hint
            learned = _smart_hint(key)
            sys.stderr.write(f"  {prompt}{hint}{learned}: ")
            sys.stderr.flush()
            raw = sys.stdin.readline().strip()
            if not raw:
                return effective_default
            if choices and raw not in choices:
                sys.stderr.write(f"  ! expected one of {choices}, using default {effective_default}\n")
                return effective_default
            return raw

        sys.stderr.write("\n=== ForgeFlow Deployment Intent Interview ===\n")
        sys.stderr.write(f"(App: {derived['app_name']} · {derived['language']} · port {derived['port']})\n")
        if smart_defaults:
            n_stable = sum(1 for s in smart_defaults.values() if s["confidence"] == "stable")
            sys.stderr.write(f"🧠 {len(smart_defaults)} smart defaults loaded from run history "
                             f"({n_stable} stable)\n")
        sys.stderr.write("\n")

        # Cloud
        provider = ask("cloud_provider", "Target cloud", "gcp", CLOUD_OPTIONS)
        project_id = ask("cloud_project_id", f"{provider.upper()} project/account id", "")
        region = ask("cloud_region", f"{provider.upper()} region", self._default_region(provider))

        # Compute
        compute_model = ask("compute_model", "Compute model", "kubernetes", COMPUTE_MODELS)
        flavour_default = COMPUTE_FLAVOURS.get(compute_model, {}).get(provider, "")
        flavour = ask("compute_flavour", "Compute flavour", flavour_default)
        replicas = int(ask("compute_replicas", "Initial replica count", 2))
        autoscale_enabled = self._as_bool(ask("autoscale_enabled", "Enable autoscaling", "yes"))
        autoscale_min = int(ask("autoscale_min", "Min replicas", replicas)) if autoscale_enabled else replicas
        autoscale_max = int(ask("autoscale_max", "Max replicas", replicas * 3)) if autoscale_enabled else replicas

        # Environments
        env_names_raw = ask("environments", "Environments (comma-separated)", "dev,prod")
        env_names = [e.strip() for e in env_names_raw.split(",") if e.strip()]
        auto_promote_devs = self._as_bool(ask("auto_promote_dev", "Auto-deploy to non-prod envs", "yes"))
        approval_envs_raw = ask("approval_envs", "Environments requiring manual approval", "prod")
        approval_envs = [e.strip() for e in approval_envs_raw.split(",") if e.strip()]

        # Secrets — always include a baseline, user can edit the yaml later
        healthcheck_path = ask("healthcheck_path", "Healthcheck path", "/health")

        # Observability
        obs_stack = ask("observability_stack", "Observability stack", "prometheus-grafana", OBSERVABILITY_STACKS)
        obs_metrics = self._as_bool(ask("observability_metrics", "Collect metrics", "yes"))
        obs_logs = self._as_bool(ask("observability_logs", "Collect logs", "yes"))
        obs_traces = self._as_bool(ask("observability_traces", "Collect traces", "no"))
        slo_avail = float(ask("slo_availability", "Availability SLO %", 99.5))
        slo_p99 = int(ask("slo_latency_p99", "Latency p99 target (ms)", 500))

        # Security
        is_k8s = compute_model == "kubernetes"
        sec_netpol = self._as_bool(ask("security_netpol", "Enable network policies", "yes" if is_k8s else "no"))
        sec_scan = self._as_bool(ask("security_image_scan", "Enable image scanning", "yes"))
        sec_iam = self._as_bool(ask("security_iam_least_priv", "Apply IAM least privilege", "yes"))
        sec_sbom = self._as_bool(ask("security_sbom", "Generate SBOM", "no"))

        # Cost
        budget = float(ask("cost_budget_usd", "Monthly budget USD (0 = no budget)", 0))
        shutdown_enabled = self._as_bool(ask("cost_shutdown_enabled", "Enable nightly auto-shutdown", "yes"))
        schedule_down = ask("cost_schedule_down", "Shutdown cron (UTC)", "0 4 * * *")
        schedule_up = ask("cost_schedule_up", "Startup cron (UTC)", "0 14 * * *")
        teardown_date = ask("cost_teardown_date", "Auto-teardown date (YYYY-MM-DD, blank for none)", "")

        # CI/CD
        cicd_platform = ask("cicd_platform", "CI/CD platform", "github-actions", CICD_PLATFORMS)
        use_argocd = self._as_bool(ask("cicd_use_argocd", "Use ArgoCD for deploys", "no"))

        sys.stderr.write("\n=== Interview complete ===\n\n")

        return {
            "cloud_provider": provider,
            "cloud_project_id": project_id,
            "cloud_region": region,
            "compute_model": compute_model,
            "compute_flavour": flavour,
            "compute_replicas": replicas,
            "autoscale_enabled": autoscale_enabled,
            "autoscale_min": autoscale_min,
            "autoscale_max": autoscale_max,
            "env_names": env_names,
            "auto_promote_devs": auto_promote_devs,
            "approval_envs": approval_envs,
            "healthcheck_path": healthcheck_path,
            "observability_stack": obs_stack,
            "observability_metrics": obs_metrics,
            "observability_logs": obs_logs,
            "observability_traces": obs_traces,
            "slo_availability": slo_avail,
            "slo_p99_ms": slo_p99,
            "security_netpol": sec_netpol,
            "security_image_scan": sec_scan,
            "security_iam_least_priv": sec_iam,
            "security_sbom": sec_sbom,
            "cost_budget_usd": budget,
            "cost_shutdown_enabled": shutdown_enabled,
            "schedule_down": schedule_down,
            "schedule_up": schedule_up,
            "teardown_date": teardown_date,
            "cicd_platform": cicd_platform,
            "cicd_use_argocd": use_argocd,
        }

    @staticmethod
    def _as_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ("y", "yes", "true", "1")

    @staticmethod
    def _default_region(cloud: str) -> str:
        return {
            "gcp": "us-central1",
            "aws": "us-east-1",
            "azure": "eastus",
            "oci": "us-ashburn-1",
        }.get(cloud, "us-central1")

    # --------------------------------------------------------------- Assembly

    def _assemble_intent(
        self,
        derived: Dict[str, Any],
        captured: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge derived + captured into a schema-conformant document."""

        # Baseline secrets — every deployment needs at minimum CI/CD creds,
        # and the persona agents can append more during the design stage.
        baseline_secrets = self._baseline_secrets_for_cloud(captured["cloud_provider"])

        # Environments
        environments = []
        for name in captured["env_names"]:
            environments.append({
                "name": name,
                "auto_promote": (name not in captured["approval_envs"]) and captured["auto_promote_devs"],
            })

        intent = {
            "version": 1,
            "app": {
                "name": derived["app_name"],
                "language": derived["language"],
                "port": derived["port"],
                "healthcheck_path": captured["healthcheck_path"],
            },
            "cloud": {
                "provider": captured["cloud_provider"],
                "project_id": captured["cloud_project_id"],
                "region": captured["cloud_region"],
            },
            "compute": {
                "model": captured["compute_model"],
                "flavour": captured["compute_flavour"],
                "replicas": captured["compute_replicas"],
                "autoscale": {
                    "enabled": captured["autoscale_enabled"],
                    "min": captured["autoscale_min"],
                    "max": captured["autoscale_max"],
                },
            },
            "environments": environments,
            "secrets": baseline_secrets,
            "observability": {
                "stack": captured["observability_stack"],
                "metrics": captured["observability_metrics"],
                "logs": captured["observability_logs"],
                "traces": captured["observability_traces"],
                "slo": {
                    "availability_target": captured["slo_availability"],
                    "latency_p99_ms": captured["slo_p99_ms"],
                },
            },
            "security": {
                "network_policies": captured["security_netpol"],
                "image_scanning": captured["security_image_scan"],
                "iam_least_privilege": captured["security_iam_least_priv"],
                "sbom": captured["security_sbom"],
            },
            "cost_controls": {
                "budget_usd_monthly": captured["cost_budget_usd"],
                "auto_shutdown": {
                    "enabled": captured["cost_shutdown_enabled"],
                    "schedule_down": captured["schedule_down"],
                    "schedule_up": captured["schedule_up"],
                },
                "teardown_date": captured["teardown_date"],
            },
            "ci_cd": {
                "platform": captured["cicd_platform"],
                "use_argocd": captured["cicd_use_argocd"],
                "require_approval_for": captured["approval_envs"],
            },
        }

        # Add metadata last so the hash is over the captured portion only
        payload_for_hash = json.dumps(intent, sort_keys=True).encode()
        intent["_meta"] = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "created_by": "deploy-intent-agent",
            "last_validated": None,
            "intent_hash": hashlib.sha256(payload_for_hash).hexdigest(),
        }
        return intent

    @staticmethod
    def _baseline_secrets_for_cloud(cloud: str) -> List[Dict[str, Any]]:
        """Return the minimum set of secrets every deployment needs."""
        common = [
            {
                "name": "GH_TOKEN",
                "description": "GitHub PAT with 'repo' + 'workflow' scope for CI/CD automation",
                "source": "github-actions",
                "required_by": ["ci_cd", "infra"],
            },
        ]
        if cloud == "gcp":
            return common + [
                {
                    "name": "GCP_SA_KEY",
                    "description": "JSON key for the deployer service account (IAM > Service Accounts)",
                    "source": "github-actions",
                    "required_by": ["infra", "cluster", "app"],
                },
                {
                    "name": "GCP_PROJECT_ID",
                    "description": "GCP project id, e.g. divine-data-469116-b2",
                    "source": "github-actions",
                    "required_by": ["infra", "cluster", "app"],
                },
                {
                    "name": "GCP_REGION",
                    "description": "Primary GCP region, e.g. us-central1",
                    "source": "github-actions",
                    "required_by": ["infra", "cluster"],
                },
            ]
        if cloud == "aws":
            return common + [
                {"name": "AWS_ACCESS_KEY_ID", "description": "IAM user access key", "source": "github-actions", "required_by": ["infra", "cluster", "app"]},
                {"name": "AWS_SECRET_ACCESS_KEY", "description": "IAM user secret", "source": "github-actions", "required_by": ["infra", "cluster", "app"]},
                {"name": "AWS_REGION", "description": "AWS region, e.g. us-east-1", "source": "github-actions", "required_by": ["infra", "cluster"]},
                {"name": "AWS_ACCOUNT_ID", "description": "12-digit AWS account id", "source": "github-actions", "required_by": ["infra"]},
            ]
        if cloud == "azure":
            return common + [
                {"name": "AZURE_CREDENTIALS", "description": "Service principal JSON (az ad sp create-for-rbac --sdk-auth)", "source": "github-actions", "required_by": ["infra", "cluster", "app"]},
                {"name": "AZURE_SUBSCRIPTION_ID", "description": "Azure subscription uuid", "source": "github-actions", "required_by": ["infra"]},
            ]
        if cloud == "oci":
            return common + [
                {"name": "OCI_TENANCY_OCID", "description": "Tenancy OCID from OCI console", "source": "github-actions", "required_by": ["infra"]},
                {"name": "OCI_USER_OCID", "description": "User OCID for deployer", "source": "github-actions", "required_by": ["infra"]},
                {"name": "OCI_FINGERPRINT", "description": "API key fingerprint", "source": "github-actions", "required_by": ["infra"]},
                {"name": "OCI_PRIVATE_KEY", "description": "Base64-encoded private key PEM (no passphrase)", "source": "github-actions", "required_by": ["infra"]},
                {"name": "OCI_REGION", "description": "OCI region, e.g. us-ashburn-1", "source": "github-actions", "required_by": ["infra"]},
                {"name": "OCI_COMPARTMENT_ID", "description": "Compartment OCID", "source": "github-actions", "required_by": ["infra"]},
            ]
        return common
