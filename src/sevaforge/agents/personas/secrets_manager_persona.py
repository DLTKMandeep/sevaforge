"""
SecretsManagerPersona -- Inventories required secrets from the deployment
intent and source code patterns, generates bootstrap scripts and
acquisition guides.
"""

from __future__ import annotations

import logging
import re
import textwrap
from typing import Any

from sevaforge.agents.base_agent import (
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)
from sevaforge.agents.personas.base_persona import BasePersona

logger = logging.getLogger(__name__)

# Regex patterns for common application secrets found in source code
APP_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "DATABASE_URL": re.compile(
        r"""(?:DATABASE_URL|DB_URL|SQLALCHEMY_DATABASE_URI)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "REDIS_URL": re.compile(
        r"""(?:REDIS_URL|REDIS_URI|CACHE_URL)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "JWT_SECRET": re.compile(
        r"""(?:JWT_SECRET|JWT_KEY|SECRET_KEY|TOKEN_SECRET)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "API_KEY": re.compile(
        r"""(?:API_KEY|APIKEY|API_SECRET)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "AWS_ACCESS_KEY_ID": re.compile(
        r"""AWS_ACCESS_KEY_ID\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "AWS_SECRET_ACCESS_KEY": re.compile(
        r"""AWS_SECRET_ACCESS_KEY\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "SMTP_PASSWORD": re.compile(
        r"""(?:SMTP_PASSWORD|MAIL_PASSWORD|EMAIL_PASSWORD)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "SENTRY_DSN": re.compile(
        r"""SENTRY_DSN\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
    "STRIPE_SECRET_KEY": re.compile(
        r"""(?:STRIPE_SECRET_KEY|STRIPE_KEY)\s*[=:]\s*['"]?(\S+)""", re.IGNORECASE,
    ),
}


class SecretsManagerPersona(BasePersona):
    """Inventories secrets and generates bootstrap scripts."""

    persona_name = "secrets-manager"
    owned_paths = ["deploy/secrets/"]

    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="persona-secrets-manager",
                name="Secrets Manager Persona",
                description=(
                    "Inventories required secrets from intent and source code "
                    "patterns, generates bootstrap scripts and acquisition guides."
                ),
                capabilities=[
                    AgentCapability(
                        name="inventory_secrets",
                        description="Scan intent and source snippets for required secrets",
                    ),
                    AgentCapability(
                        name="generate_bootstrap_script",
                        description="Produce a shell script to populate GitHub / cloud secrets",
                    ),
                    AgentCapability(
                        name="generate_acquisition_guide",
                        description="Produce a Markdown guide for obtaining each secret",
                    ),
                ],
                tags=["persona", "secrets", "security", "bootstrap"],
            )
        )

    # ------------------------------------------------------------------

    async def _produce_artifacts(
        self,
        intent: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        findings: list[str] = []

        cloud = intent.get("cloud", params.get("cloud", "gcp")).lower()
        repo = intent.get("repo", params.get("repo", "org/repo"))
        source_snippets: list[str] = intent.get(
            "source_snippets", params.get("source_snippets", []),
        )

        # -- Inventory ---------------------------------------------------
        inventory = self._inventory_secrets(intent, source_snippets)
        findings.append(f"Discovered {len(inventory)} required secret(s).")

        # Inventory manifest
        inv_yaml = self._render_inventory_yaml(inventory)
        artifacts.append(
            self.write_artifact("deploy/secrets/inventory.yml", inv_yaml)
        )

        # -- Bootstrap script --------------------------------------------
        bootstrap = self._generate_bootstrap_script(repo, cloud, inventory)
        artifacts.append(
            self.write_artifact("deploy/secrets/bootstrap-secrets.sh", bootstrap)
        )

        # -- Acquisition guide -------------------------------------------
        guide = self._generate_acquisition_guide(inventory)
        artifacts.append(
            self.write_artifact("deploy/secrets/SECRETS_GUIDE.md", guide)
        )

        return {"artifacts": artifacts, "findings": findings}

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def _inventory_secrets(
        self,
        intent: dict[str, Any],
        source_snippets: list[str],
    ) -> list[dict[str, str]]:
        """Build a list of {name, source, description} dicts."""
        seen: set[str] = set()
        inventory: list[dict[str, str]] = []

        # 1. Secrets declared explicitly in intent
        for secret in intent.get("secrets", []):
            name = secret if isinstance(secret, str) else secret.get("name", "")
            if name and name not in seen:
                seen.add(name)
                inventory.append({
                    "name": name,
                    "source": "intent",
                    "description": f"Declared in deployment intent",
                })

        # 2. Cloud infrastructure secrets (always needed)
        infra_secrets = self._cloud_infra_secrets(intent)
        for sec in infra_secrets:
            if sec["name"] not in seen:
                seen.add(sec["name"])
                inventory.append(sec)

        # 3. Scan source snippets for APP_SECRET_PATTERNS
        for snippet in source_snippets:
            for secret_name, pattern in APP_SECRET_PATTERNS.items():
                if pattern.search(snippet) and secret_name not in seen:
                    seen.add(secret_name)
                    inventory.append({
                        "name": secret_name,
                        "source": "source-scan",
                        "description": f"Detected via pattern match in source code",
                    })

        return inventory

    @staticmethod
    def _cloud_infra_secrets(intent: dict[str, Any]) -> list[dict[str, str]]:
        cloud = intent.get("cloud", "gcp").lower()
        secrets: list[dict[str, str]] = []

        if cloud == "gcp":
            secrets.extend([
                {"name": "GCP_PROJECT", "source": "infra", "description": "GCP project ID"},
                {"name": "GCP_REGION", "source": "infra", "description": "GCP region"},
                {"name": "WIF_PROVIDER", "source": "infra", "description": "Workload Identity Federation provider"},
                {"name": "SA_EMAIL", "source": "infra", "description": "GCP service account email"},
            ])
        elif cloud == "aws":
            secrets.extend([
                {"name": "AWS_REGION", "source": "infra", "description": "AWS region"},
                {"name": "AWS_ROLE_ARN", "source": "infra", "description": "IAM role ARN for GitHub OIDC"},
            ])
        elif cloud == "azure":
            secrets.extend([
                {"name": "AZURE_SUBSCRIPTION_ID", "source": "infra", "description": "Azure subscription ID"},
                {"name": "AZURE_TENANT_ID", "source": "infra", "description": "Azure tenant ID"},
                {"name": "AZURE_CLIENT_ID", "source": "infra", "description": "Azure service principal client ID"},
            ])

        return secrets

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_inventory_yaml(inventory: list[dict[str, str]]) -> str:
        lines = ["# Secret inventory -- generated by SevaForge secrets-manager", "secrets:"]
        for sec in inventory:
            lines.append(f"  - name: {sec['name']}")
            lines.append(f"    source: {sec['source']}")
            lines.append(f"    description: \"{sec['description']}\"")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _generate_bootstrap_script(
        repo: str,
        cloud: str,
        inventory: list[dict[str, str]],
    ) -> str:
        header = textwrap.dedent(f"""\
            #!/usr/bin/env bash
            # Bootstrap secrets -- generated by SevaForge secrets-manager
            # Usage: ./bootstrap-secrets.sh
            #
            # Prerequisites:
            #   - GitHub CLI (gh) authenticated
            #   - Access to secret values
            set -euo pipefail

            REPO="{repo}"

        """)

        body_lines: list[str] = []
        for sec in inventory:
            body_lines.append(f'# {sec["description"]}')
            body_lines.append(
                f'echo "Setting {sec["name"]}..."'
            )
            body_lines.append(
                f'gh secret set {sec["name"]} --repo "$REPO" --body "${{{{SECRET_{sec["name"]}:-REPLACE_ME}}}}"'
            )
            body_lines.append("")

        footer = textwrap.dedent("""\
            echo "Done. All secrets have been set."
            echo "Verify with: gh secret list --repo $REPO"
        """)

        return header + "\n".join(body_lines) + "\n" + footer

    @staticmethod
    def _generate_acquisition_guide(
        inventory: list[dict[str, str]],
    ) -> str:
        lines = [
            "# Secrets Acquisition Guide",
            "",
            "Generated by SevaForge secrets-manager persona.",
            "",
            "## Required Secrets",
            "",
        ]

        acquisition_hints: dict[str, str] = {
            "GCP_PROJECT": "Find in GCP Console > Dashboard or `gcloud config get-value project`.",
            "GCP_REGION": "Choose a region from `gcloud compute regions list`.",
            "WIF_PROVIDER": "Create via `gcloud iam workload-identity-pools providers create ...`.",
            "SA_EMAIL": "Create via `gcloud iam service-accounts create ...`.",
            "AWS_REGION": "e.g. us-east-1. See AWS Regions documentation.",
            "AWS_ROLE_ARN": "Create an IAM role with GitHub OIDC trust policy.",
            "DATABASE_URL": "Format: `postgresql://user:pass@host:5432/dbname`.",
            "REDIS_URL": "Format: `redis://host:6379/0`.",
            "JWT_SECRET": "Generate with `openssl rand -hex 32`.",
            "API_KEY": "Obtain from the relevant API provider dashboard.",
            "SMTP_PASSWORD": "Obtain from your email service provider.",
            "SENTRY_DSN": "Find in Sentry > Project Settings > Client Keys.",
            "STRIPE_SECRET_KEY": "Find in Stripe Dashboard > Developers > API Keys.",
        }

        for i, sec in enumerate(inventory, 1):
            hint = acquisition_hints.get(sec["name"], "Consult your team or service provider.")
            lines.append(f"### {i}. `{sec['name']}`")
            lines.append(f"- **Source**: {sec['source']}")
            lines.append(f"- **Description**: {sec['description']}")
            lines.append(f"- **How to obtain**: {hint}")
            lines.append("")

        return "\n".join(lines)
