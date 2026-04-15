"""
SecretsManagerPersona — produces the secrets inventory + generation guide.

Artifacts:
  deploy/secrets/inventory.yaml       — canonical list (from intent + scans)
  deploy/secrets/bootstrap.sh         — one-shot local script to set GH secrets
  deploy/secrets/DEPLOYMENT_SECRETS_GUIDE.md — human-readable walkthrough
"""
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .base_persona import BasePersona


# Extra env-var sniffing patterns — these aren't in the cloud baseline but
# commonly appear in app code
APP_SECRET_PATTERNS = [
    (r"\bDATABASE_URL\b", "DATABASE_URL", "Connection string for primary database"),
    (r"\bREDIS_URL\b", "REDIS_URL", "Connection string for Redis"),
    (r"\bJWT_SECRET\b", "JWT_SECRET", "Secret key for signing JWT tokens"),
    (r"\bSESSION_SECRET\b", "SESSION_SECRET", "Secret key for signing session cookies"),
    (r"\bSTRIPE_API_KEY\b", "STRIPE_API_KEY", "Stripe API key"),
    (r"\bOPENAI_API_KEY\b", "OPENAI_API_KEY", "OpenAI API key"),
    (r"\bANTHROPIC_API_KEY\b", "ANTHROPIC_API_KEY", "Anthropic API key"),
    (r"\bSENDGRID_API_KEY\b", "SENDGRID_API_KEY", "SendGrid API key"),
    (r"\bSMTP_PASSWORD\b", "SMTP_PASSWORD", "SMTP password for outbound email"),
]


class SecretsManagerPersona(BasePersona):
    """Produces the secrets inventory, bootstrap script, and acquisition guide."""

    persona_name = "secrets-manager"
    owned_paths = ["deploy/secrets/"]

    def __init__(self):
        super().__init__(
            name="secrets_manager_persona",
            description="Inventories all secrets and generates bootstrap artefacts",
        )

    # ------------------------------------------------------------ main method

    def produce_artifacts(self, overwrite=True):
        # Seed from intent's baseline
        secrets: List[Dict[str, Any]] = list(self.intent.get("secrets") or [])

        # Augment by scanning app code
        scanned = self._scan_app_for_secrets()
        existing_names = {s["name"] for s in secrets}
        for name, desc in scanned:
            if name in existing_names:
                continue
            secrets.append({
                "name": name,
                "description": desc,
                "source": "github-actions",
                "required_by": ["app"],
            })
            existing_names.add(name)

        # Write inventory
        inv_action = self.write_file(
            "deploy/secrets/inventory.yaml",
            yaml.safe_dump({"secrets": secrets}, sort_keys=False),
            overwrite=overwrite,
        )

        # Write bootstrap script
        bootstrap_action = self.write_file(
            "deploy/secrets/bootstrap.sh",
            self._render_bootstrap(secrets),
            overwrite=overwrite,
        )
        # chmod +x on disk (best-effort; safe_write returns after writing)
        bootstrap_path = self.project_path / "deploy/secrets/bootstrap.sh"
        try:
            bootstrap_path.chmod(0o755)
        except Exception:
            pass

        # Write acquisition guide
        guide_action = self.write_file(
            "deploy/secrets/DEPLOYMENT_SECRETS_GUIDE.md",
            self._render_guide(secrets),
            overwrite=overwrite,
        )

        findings = []
        if not scanned:
            findings.append("No app-level secrets detected in source — using cloud baseline only")
        else:
            findings.append(f"Detected {len(scanned)} app-level secret(s) from source scan")

        return (
            [inv_action, bootstrap_action, guide_action],
            findings,
            {"secret_count": len(secrets), "scanned_from_source": [n for n, _ in scanned]},
        )

    # ---------------------------------------------------------------- helpers

    def _scan_app_for_secrets(self) -> List[tuple]:
        """Grep source files for likely secret references."""
        found = []
        seen = set()
        candidates = []
        for pattern in ("*.py", "*.js", "*.ts", "*.go", "*.env.example"):
            candidates.extend(self.project_path.rglob(pattern))
        # Cap the scan to avoid exploding on huge repos
        for file in candidates[:200]:
            try:
                content = file.read_text(errors="ignore")
            except Exception:
                continue
            for rx, name, desc in APP_SECRET_PATTERNS:
                if name in seen:
                    continue
                if re.search(rx, content):
                    found.append((name, desc))
                    seen.add(name)
        return found

    def _render_bootstrap(self, secrets: List[Dict[str, Any]]) -> str:
        """Emit a bash script that sets every secret via gh CLI."""
        repo = "${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
        lines = [
            "#!/usr/bin/env bash",
            "# =============================================================================",
            "# ForgeFlow — GitHub Secrets Bootstrap",
            "# Reads deploy/secrets/inventory.yaml, prompts for each value, sets via gh.",
            "# Requires: gh CLI (authenticated), jq, yq.",
            "# Run from repo root:  ./deploy/secrets/bootstrap.sh",
            "# =============================================================================",
            "set -euo pipefail",
            f'REPO="{repo}"',
            'echo "=== Setting GitHub secrets for $REPO ==="',
            "",
        ]
        for sec in secrets:
            name = sec["name"]
            desc = sec.get("description", "")
            lines.extend([
                f'# {desc}',
                f'if [ -z "${{{name}:-}}" ]; then',
                f'  read -r -s -p "Enter value for {name} ({desc}): " {name}',
                f'  echo',
                f'fi',
                f'gh secret set {name} --repo "$REPO" --body "${{{name}}}"',
                f'echo "✓ Set {name}"',
                "",
            ])
        lines.append('echo "=== All secrets set ==="')
        return "\n".join(lines) + "\n"

    def _render_guide(self, secrets: List[Dict[str, Any]]) -> str:
        """Emit a markdown walkthrough for acquiring each secret."""
        cloud = self.intent["cloud"]["provider"]
        project_id = self.intent["cloud"].get("project_id", "<project-id>")

        guide = [
            f"# Deployment Secrets Guide — {self.intent['app']['name']}",
            "",
            f"This guide walks through every GitHub secret required for deploying to **{cloud.upper()}**.",
            "Run `./deploy/secrets/bootstrap.sh` to set them all interactively, or set them one at a time with `gh secret set`.",
            "",
            "| Secret | Required by | Source |",
            "|---|---|---|",
        ]
        for sec in secrets:
            req = ", ".join(sec.get("required_by", []))
            guide.append(f"| `{sec['name']}` | {req} | {sec.get('source', 'github-actions')} |")

        guide += [
            "",
            "## How to obtain each secret",
            "",
        ]
        for sec in secrets:
            guide += [
                f"### `{sec['name']}`",
                "",
                sec.get("description", ""),
                "",
                self._acquisition_steps(sec["name"], cloud, project_id),
                "",
            ]

        guide += [
            "## Rotation policy",
            "",
            "- Rotate every 90 days: `GH_TOKEN`, cloud service-account keys, JWT/session secrets.",
            "- Rotate on employee offboarding: any secret owned by the departing user.",
            "- Rotate immediately if leaked: all of the above.",
            "",
            "## Storage",
            "",
            "All secrets live in **GitHub Actions secrets** for this repository. For production-grade "
            "workloads, migrate sensitive values (database URLs, JWT secrets) to a managed secret store:",
            "- GCP: Secret Manager",
            "- AWS: Secrets Manager / SSM Parameter Store",
            "- Azure: Key Vault",
            "- Self-hosted: HashiCorp Vault",
            "",
        ]
        return "\n".join(guide) + "\n"

    @staticmethod
    def _acquisition_steps(name: str, cloud: str, project_id: str) -> str:
        """Cloud-specific acquisition walkthrough for each common secret."""
        steps = {
            "GH_TOKEN": (
                "1. Go to https://github.com/settings/tokens?type=beta\n"
                "2. Create a fine-grained PAT with **Actions: read/write**, **Contents: read/write**, "
                "**Metadata: read** on this repo\n"
                "3. Copy the token and set it via `gh secret set GH_TOKEN`"
            ),
            "GCP_SA_KEY": (
                f"1. `gcloud iam service-accounts create sevaforge-deployer --project={project_id}`\n"
                f"2. `gcloud projects add-iam-policy-binding {project_id} "
                f"--member=serviceAccount:sevaforge-deployer@{project_id}.iam.gserviceaccount.com "
                "--role=roles/editor`\n"
                f"3. `gcloud iam service-accounts keys create gcp-sa-key.json "
                f"--iam-account=sevaforge-deployer@{project_id}.iam.gserviceaccount.com`\n"
                "4. `gh secret set GCP_SA_KEY < gcp-sa-key.json`\n"
                "5. Delete the local key file: `rm gcp-sa-key.json`"
            ),
            "GCP_PROJECT_ID": f"Your project id: `{project_id}`. Find it with `gcloud projects list`.",
            "GCP_REGION": "Pick a region near your users; `us-central1` is the default for free-tier friendliness.",
            "AWS_ACCESS_KEY_ID": (
                "1. IAM console → Users → Create user `sevaforge-deployer`\n"
                "2. Attach policy `PowerUserAccess` (or a scoped custom policy)\n"
                "3. Security credentials → Create access key → CLI\n"
                "4. Copy both values into `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`"
            ),
            "DATABASE_URL": (
                "If you are using a managed database, copy the connection string from your provider's console "
                "(e.g. Cloud SQL, RDS, Atlas). Format: `postgres://user:pass@host:5432/dbname`"
            ),
            "JWT_SECRET": (
                "Generate a 32-byte random string:\n"
                "```\nopenssl rand -base64 32\n```"
            ),
            "SESSION_SECRET": "Same as JWT_SECRET — generate with `openssl rand -base64 32`.",
            "OPENAI_API_KEY": "https://platform.openai.com/api-keys → Create new secret key.",
            "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys → Create Key.",
        }
        return steps.get(name, "See the service's own documentation for how to obtain this credential.")
