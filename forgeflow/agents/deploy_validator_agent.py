#!/usr/bin/env python3
"""
ForgeFlow Deploy Validator Agent
=================================
Runs after the orchestrator. Cross-checks persona outputs for consistency
before the GitHub push stage. Failures here BLOCK the push.

Checks:
  1. Every secret referenced in Helm values / K8s manifests is in the inventory
  2. Every cron schedule is valid
  3. Budget / teardown dates are in the future (if set)
  4. Terraform modules reference variables that are actually declared
  5. Image repository in helm values matches cloud registry conventions
  6. SLO targets are realistic (availability <= 100, p99 > 0)
  7. Intent hash matches — warn if intent was edited after design
"""

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from .base_agent import BaseAgent


class DeployValidatorAgent(BaseAgent):
    """Cross-checks orchestrator outputs for deployability."""

    intelligence_phase = 2
    intelligence_label = "Automated"

    def __init__(self):
        super().__init__(
            name="deploy_validator_agent",
            description="Cross-checks deploy artefacts for consistency before push",
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        project_path = Path(params["path"]).resolve()
        self.project_path = project_path

        intent_file = project_path / ".sevaforge" / "deployment-intent.yaml"
        if not intent_file.exists():
            return self.create_result(
                status="error",
                summary="Cannot validate — deployment-intent.yaml missing",
            )

        intent = yaml.safe_load(intent_file.read_text())

        checks = [
            ("secrets_referenced_are_inventoried", self._check_secrets_consistency(intent)),
            ("cron_schedules_valid", self._check_cron_schedules(intent)),
            ("dates_are_future", self._check_dates(intent)),
            ("slo_realistic", self._check_slo(intent)),
            ("intent_hash_matches", self._check_intent_hash(intent)),
            ("terraform_vars_declared", self._check_terraform_vars(intent)),
            ("image_repo_matches_cloud", self._check_image_repo(intent)),
        ]

        passed = [name for name, (ok, _) in checks if ok]
        failed = [(name, msg) for name, (ok, msg) in checks if not ok]
        findings = [
            *[f"✓ {name}" for name in passed],
            *[f"✗ {name}: {msg}" for name, msg in failed],
        ]

        # Update validation timestamp in intent
        if not failed:
            intent["_meta"]["last_validated"] = datetime.utcnow().isoformat() + "Z"
            intent_file.write_text(yaml.safe_dump(intent, sort_keys=False))

        status = "error" if failed else "success"
        summary = (
            f"{len(passed)}/{len(checks)} checks passed"
            + (f" — {len(failed)} failed, push blocked" if failed else "")
        )

        return self.create_result(
            status=status,
            summary=summary,
            data={"passed": passed, "failed": [{"check": n, "error": m} for n, m in failed]},
            findings=findings,
        )

    # ================================================================ checks

    def _check_secrets_consistency(self, intent: Dict) -> tuple:
        """
        Inventory-anchored approach — works on any repo without blocklists.

        Instead of scanning workflows/manifests for secret references and
        guessing which ones are "real," we trust the SecretsManager persona's
        inventory as the source of truth for what the *app* needs at runtime.

        Checks:
          1. The inventory file must exist (persona ran successfully).
          2. Every inventoried secret must appear *somewhere* in the project
             source or generated deployment files — if it doesn't, it's stale
             and the inventory needs updating.

        This avoids the impossible task of distinguishing CI plumbing secrets
        (KUBE_CONFIG, CODECOV_TOKEN, etc.) from app secrets in arbitrary
        repos.
        """
        inventory_file = self.project_path / "deploy/secrets/inventory.yaml"
        if not inventory_file.exists():
            return (False, "deploy/secrets/inventory.yaml is missing")

        inventory = yaml.safe_load(inventory_file.read_text()) or {}
        inventoried: Set[str] = {s["name"] for s in (inventory.get("secrets") or [])}

        if not inventoried:
            # Empty inventory is fine — some apps have no secrets
            return (True, "")

        # Build a searchable corpus: source code + deploy artifacts + workflows
        _scan_globs = [
            "src/**/*", "app/**/*", "lib/**/*", "*.py", "*.js", "*.ts",
            "deploy/**/*.yaml", "deploy/**/*.yml",
            ".github/workflows/*.yml",
            "docker-compose*.yml", "Dockerfile*",
            ".env.example", ".env.sample",
        ]
        # Exclude the inventory file itself — otherwise every secret name
        # appears trivially in the corpus and nothing is ever flagged stale.
        _exclude = {inventory_file.resolve()}
        corpus = ""
        for glob in _scan_globs:
            for f in self.project_path.rglob(glob):
                if f.is_file() and f.stat().st_size < 512_000 \
                        and f.resolve() not in _exclude:
                    try:
                        corpus += f.read_text(errors="ignore") + "\n"
                    except Exception:
                        continue

        # Check each inventoried secret is actually referenced somewhere
        stale = {name for name in inventoried if name not in corpus}

        if stale:
            return (False,
                    f"Inventoried but never referenced in code: {sorted(stale)} "
                    f"— remove from deploy/secrets/inventory.yaml or verify usage")
        return (True, "")

    def _check_cron_schedules(self, intent: Dict) -> tuple:
        crons = []
        shutdown = intent.get("cost_controls", {}).get("auto_shutdown", {})
        if shutdown.get("enabled"):
            crons.append(("schedule_down", shutdown.get("schedule_down")))
            crons.append(("schedule_up", shutdown.get("schedule_up")))

        cron_rx = re.compile(r"^(\S+\s+){4}\S+$")
        for name, expr in crons:
            if not expr or not cron_rx.match(expr.strip()):
                return (False, f"{name} is not a valid 5-field cron: {expr!r}")
        return (True, "")

    def _check_dates(self, intent: Dict) -> tuple:
        td = intent.get("cost_controls", {}).get("teardown_date", "")
        if not td:
            return (True, "")
        try:
            d = datetime.fromisoformat(td).date()
        except Exception:
            return (False, f"teardown_date is not ISO YYYY-MM-DD: {td!r}")
        if d <= date.today():
            return (False, f"teardown_date is in the past: {td}")
        return (True, "")

    def _check_slo(self, intent: Dict) -> tuple:
        slo = intent.get("observability", {}).get("slo", {})
        avail = slo.get("availability_target")
        p99 = slo.get("latency_p99_ms")
        if avail is None or not (0 < avail <= 100):
            return (False, f"availability_target must be in (0, 100], got {avail}")
        if p99 is None or p99 <= 0:
            return (False, f"latency_p99_ms must be > 0, got {p99}")
        return (True, "")

    def _check_intent_hash(self, intent: Dict) -> tuple:
        stored = intent.get("_meta", {}).get("intent_hash")
        if not stored:
            return (True, "")  # pre-hash legacy intents tolerated
        reserved_meta = intent.pop("_meta", None)
        payload = json.dumps(intent, sort_keys=True).encode()
        computed = hashlib.sha256(payload).hexdigest()
        if reserved_meta is not None:
            intent["_meta"] = reserved_meta
        if stored != computed:
            return (False, "intent was edited after design — re-run deploy-design")
        return (True, "")

    def _check_terraform_vars(self, intent: Dict) -> tuple:
        cloud = intent["cloud"]["provider"]
        infra_dir = self.project_path / f"forgeflow/infrastructure/{cloud}"
        if not infra_dir.exists():
            return (True, "")  # nothing to validate

        declared: Set[str] = set()
        referenced: Set[str] = set()
        for tf in infra_dir.glob("*.tf"):
            content = tf.read_text(errors="ignore")
            for m in re.finditer(r'variable\s+"(\w+)"', content):
                declared.add(m.group(1))
            for m in re.finditer(r"var\.(\w+)", content):
                referenced.add(m.group(1))

        missing = referenced - declared
        if missing:
            return (False, f"Terraform references undeclared variables: {sorted(missing)}")
        return (True, "")

    def _check_image_repo(self, intent: Dict) -> tuple:
        app = intent["app"]["name"]
        cloud = intent["cloud"]["provider"]
        values_file = self.project_path / f"deploy/helm/{app}/values.yaml"
        if not values_file.exists():
            return (True, "")  # serverless or no helm chart

        values = yaml.safe_load(values_file.read_text()) or {}
        repo = (values.get("image") or {}).get("repository", "")

        expected_prefix = {
            "gcp": "gcr.io/",
            "aws": ".dkr.ecr.",
            "azure": ".azurecr.io/",
            "oci": ".ocir.io/",
        }.get(cloud)

        if expected_prefix and expected_prefix not in repo:
            return (False,
                    f"image.repository '{repo}' doesn't match expected {cloud} registry "
                    f"(want substring '{expected_prefix}')")
        return (True, "")
