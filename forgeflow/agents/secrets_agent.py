"""
ForgeFlow Secrets Agent
=======================
Analyses the generated repository to determine every GitHub Actions secret
that is required for the CI → Test → CD → Validate lifecycle to work.

Outputs two files:
  docs/DEPLOYMENT_GUIDE.md   — Human-readable step-by-step onboarding guide
  scripts/bootstrap-secrets.sh — Interactive shell script that validates and
                                  sets each secret via the `gh` CLI

The agent is cloud-agnostic: it reads the generated .github/workflows/ files
and the forgeflow-config to determine which cloud provider is targeted, then
emits only the secrets that are actually required.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import BaseAgent


# ── Secret definitions ─────────────────────────────────────────────────────────
# Each entry: (name, description, how_to_get, required_for, optional)

AWS_SECRETS = [
    ("AWS_ACCESS_KEY_ID",
     "AWS IAM access key for pipeline operations",
     "IAM → Users → Security credentials → Create access key",
     ["Terraform infra provisioning", "ECR image push", "EKS kubeconfig update"],
     False),
    ("AWS_SECRET_ACCESS_KEY",
     "AWS IAM secret key (pair with AWS_ACCESS_KEY_ID)",
     "Shown once at IAM access key creation — store immediately",
     ["Terraform infra provisioning", "ECR image push", "EKS kubeconfig update"],
     False),
    ("AWS_REGION",
     "AWS region to deploy into (e.g. us-east-1)",
     "Choose your target region — must match Terraform variables",
     ["All AWS operations"],
     False),
    ("AWS_ACCOUNT_ID",
     "12-digit AWS account ID",
     "AWS Console top-right → Account ID, or: aws sts get-caller-identity --query Account",
     ["ECR repository URL construction", "IAM policy ARNs"],
     False),
]

GCP_SECRETS = [
    ("GCP_SA_KEY",
     "GCP service account JSON key (base64-encoded)",
     "IAM → Service Accounts → Create → Grant roles (Editor + Container Admin) → Keys → JSON → base64-encode",
     ["Terraform GKE provisioning", "GCR image push", "GKE kubeconfig"],
     False),
    ("GCP_PROJECT_ID",
     "GCP project ID (not name)",
     "GCP Console header, or: gcloud config get-value project",
     ["All GCP operations"],
     False),
    ("GCP_REGION",
     "GCP region for GKE cluster (e.g. us-central1)",
     "Match the region in your Terraform variables",
     ["GKE cluster location"],
     False),
]

AZURE_SECRETS = [
    ("AZURE_CREDENTIALS",
     "Azure service principal JSON (full JSON blob from az ad sp create-for-rbac)",
     "az ad sp create-for-rbac --name sevaforge-sp --role Contributor "
     "--scopes /subscriptions/<id> --sdk-auth",
     ["Terraform AKS provisioning", "ACR image push", "AKS kubeconfig"],
     False),
    ("AZURE_SUBSCRIPTION_ID",
     "Azure subscription ID",
     "az account show --query id -o tsv",
     ["All Azure operations"],
     False),
    ("AZURE_RESOURCE_GROUP",
     "Resource group that contains your AKS cluster",
     "Create one: az group create --name sevaforge-rg --location eastus",
     ["AKS cluster location"],
     False),
]

COMMON_SECRETS = [
    ("GH_PAT",
     "GitHub Personal Access Token with repo + write:packages + secrets scopes",
     "GitHub → Settings → Developer settings → Personal access tokens → Fine-grained "
     "→ Select repo, Read/Write on secrets and packages",
     ["Cross-repo ArgoCD bootstrap", "Writing deployment status back to PRs"],
     False),
    ("ARGOCD_SERVER",
     "ArgoCD server hostname (populated automatically by the bootstrap workflow)",
     "Run the bootstrap GitHub Actions workflow first — it writes this secret automatically",
     ["ArgoCD sync commands in CD workflow"],
     False),
    ("ARGOCD_AUTH_TOKEN",
     "ArgoCD API token (populated automatically by the bootstrap workflow)",
     "Run the bootstrap GitHub Actions workflow first — it writes this secret automatically",
     ["ArgoCD application sync and status checks"],
     False),
]

OPTIONAL_SECRETS = [
    ("SNYK_TOKEN",
     "Snyk API token for enhanced vulnerability scanning",
     "https://app.snyk.io → Account Settings → API Token",
     ["Snyk dependency and container scanning"],
     True),
    ("SLACK_WEBHOOK_URL",
     "Slack Incoming Webhook URL for deployment notifications",
     "Slack → Apps → Incoming Webhooks → Add to Workspace → Copy URL",
     ["CD pipeline success/failure notifications"],
     True),
    ("SONAR_TOKEN",
     "SonarCloud token for code quality analysis",
     "https://sonarcloud.io → My Account → Security → Generate Token",
     ["SonarCloud quality gate in CI"],
     True),
    ("DATADOG_API_KEY",
     "Datadog API key for deployment tracking metrics",
     "Datadog → Integrations → API Keys → New Key",
     ["Deployment event tracking and monitoring"],
     True),
]


# ── Deployment guide template ──────────────────────────────────────────────────
DEPLOYMENT_GUIDE_TEMPLATE = """\
# Sevaforge Deployment Guide
## {app_name} — End-to-End CI/CD Setup

Generated by ForgeFlow · AIDDaaS

---

## Overview: What happens after you push to GitHub

```
Push to any branch
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  CI Workflow (.github/workflows/ci.yml)                     │
│  ─────────────────────────────────────────────────────────  │
│  ① Lint & static analysis                                   │
│  ② Security scan (Gitleaks, Trivy, {snyk_line})            │
│  ③ Build Docker image → push to {registry}                 │
└─────────────────────────────────────────────────────────────┘
      │  on success
      ▼
┌─────────────────────────────────────────────────────────────┐
│  Test Workflow (.github/workflows/test.yml)                 │
│  ─────────────────────────────────────────────────────────  │
│  ① Unit tests + coverage report                             │
│  ② Integration tests (with database + cache services)      │
│  ③ E2E tests (Playwright — full browser automation)        │
│  ④ Upload test artifacts & coverage badge                   │
└─────────────────────────────────────────────────────────────┘
      │  on success + branch = main
      ▼
┌─────────────────────────────────────────────────────────────┐
│  CD Workflow (.github/workflows/cd.yml)                     │
│  ─────────────────────────────────────────────────────────  │
│  ① Deploy to staging (ArgoCD sync)                         │
│  ② Validate staging (health check + smoke tests)           │
│  ③ Wait for production approval (GitHub Environment gate)  │
│  ④ Deploy to production (ArgoCD sync)                      │
│  ⑤ Validate production (health check + smoke tests)        │
│  ⑥ Rollback automatically if validation fails              │
│  ⑦ Notify Slack (success or failure)                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Run infrastructure bootstrap (first time only)

Before any workflow can deploy, you need cloud infrastructure:

```bash
# 1. Provision EKS/GKE/AKS cluster + networking (runs Terraform)
#    Trigger this manually in GitHub Actions:
#    Actions → "Infrastructure Provision" → Run workflow

# 2. Install ArgoCD + write its secrets back to GitHub
#    Actions → "ArgoCD Bootstrap" → Run workflow

# After these two complete, ARGOCD_SERVER and ARGOCD_AUTH_TOKEN
# will be automatically set as GitHub secrets.
```

---

## Step 2 — Set required GitHub secrets

Run the bootstrap script (see scripts/bootstrap-secrets.sh) or set manually:

```bash
cd {app_name}/
bash scripts/bootstrap-secrets.sh
```

### Required secrets — pipeline will fail without these

{required_secrets_table}

### Auto-populated secrets — set by bootstrap workflow

| Secret | Set by |
|--------|--------|
| `ARGOCD_SERVER` | ArgoCD Bootstrap workflow |
| `ARGOCD_AUTH_TOKEN` | ArgoCD Bootstrap workflow |

### Optional secrets — enhance the pipeline

{optional_secrets_table}

---

## Step 3 — Set up GitHub Environments

The CD workflow uses GitHub Environments for deployment gates:

1. Go to **Settings → Environments** in your repository
2. Create two environments: `staging` and `production`
3. For `production`: add **Required reviewers** (yourself + teammates)
4. This creates a manual approval gate before production deploys

---

## Step 4 — First deployment

```bash
git push origin main
```

Watch the three workflows chain:
- **Actions → CI** → should pass in ~5 minutes
- **Actions → Tests** → starts automatically after CI
- **Actions → CD** → deploys to staging, waits for production approval

---

## Step 5 — Validate your deployment

After CD completes, your app is running at:

```
Staging:    https://{app_name}-staging.{domain_hint}
Production: https://{app_name}.{domain_hint}
```

Check ArgoCD dashboard:
```bash
# Port-forward ArgoCD UI locally
kubectl port-forward svc/argocd-server -n argocd 8080:443
# Open https://localhost:8080
```

---

## Workflow triggers reference

| Event | CI | Tests | CD |
|-------|----|-------|----|
| Push to any branch | ✓ | ✗ | ✗ |
| PR opened/updated | ✓ | ✗ | ✗ |
| CI passes | → | ✓ | ✗ |
| Tests pass on `main` | → | → | ✓ |
| Manual trigger | ✓ | ✓ | ✓ |

---

## Troubleshooting

**CI fails at security scan**
→ Run `trivy fs .` locally to find vulnerabilities before pushing.

**Tests fail at integration**
→ Check if database migrations are in sync: `alembic upgrade head` (Python) or equivalent.

**CD fails at ArgoCD sync**
→ Check `ARGOCD_SERVER` and `ARGOCD_AUTH_TOKEN` secrets are set correctly.
→ ArgoCD UI → Application → Sync Status for detailed error.

**Deployment validation fails**
→ CD will auto-rollback to the previous image tag.
→ Check pod logs: `kubectl logs -n {app_name} -l app={app_name} --previous`

---

*Generated by ForgeFlow — AIDDaaS · Sevaforge*
"""


BOOTSTRAP_SCRIPT_TEMPLATE = """\
#!/usr/bin/env bash
# =============================================================================
# Sevaforge Secret Bootstrap Script — {app_name}
# =============================================================================
# Sets all required GitHub Actions secrets for the CI/CD/CD lifecycle.
# Run this ONCE before your first push to main.
#
# Prerequisites:
#   - gh CLI installed and authenticated (gh auth login)
#   - You are inside the cloned repository directory
#
# Usage:
#   bash scripts/bootstrap-secrets.sh
# =============================================================================

set -euo pipefail

REPO="{github_user}/{app_name}"
RED='\\033[0;31m'
GRN='\\033[0;32m'
YLW='\\033[1;33m'
BLU='\\033[0;34m'
NC='\\033[0;0m'

print_header() {{
  echo ""
  echo "${{BLU}}════════════════════════════════════════${{NC}}"
  echo "${{BLU}}  $1${{NC}}"
  echo "${{BLU}}════════════════════════════════════════${{NC}}"
}}

prompt_secret() {{
  local name="$1"
  local description="$2"
  local how_to_get="$3"
  local optional="${{4:-false}}"

  echo ""
  if [[ "$optional" == "true" ]]; then
    echo "${{YLW}}[OPTIONAL] $name${{NC}}"
  else
    echo "${{GRN}}[REQUIRED] $name${{NC}}"
  fi
  echo "  $description"
  echo "  How to get it: $how_to_get"
  echo ""

  # Check if already set
  if gh secret list --repo "$REPO" 2>/dev/null | grep -q "^$name[[:space:]]"; then
    echo "  ${{GRN}}✓ Already set — skipping (use --force to overwrite)${{NC}}"
    return 0
  fi

  if [[ "$optional" == "true" ]]; then
    read -rp "  Enter value (or press Enter to skip): " value
    if [[ -z "$value" ]]; then
      echo "  ${{YLW}}⊘ Skipped${{NC}}"
      return 0
    fi
  else
    while true; do
      read -rsp "  Enter value: " value
      echo ""
      if [[ -n "$value" ]]; then break; fi
      echo "  ${{RED}}✗ Value cannot be empty for required secret${{NC}}"
    done
  fi

  echo -n "$value" | gh secret set "$name" --repo "$REPO"
  echo "  ${{GRN}}✓ Set successfully${{NC}}"
}}

validate_prerequisites() {{
  print_header "Checking prerequisites"

  if ! command -v gh &>/dev/null; then
    echo "${{RED}}✗ gh CLI not found — install from https://cli.github.com/${{NC}}"
    exit 1
  fi
  echo "${{GRN}}✓ gh CLI found${{NC}}"

  if ! gh auth status &>/dev/null; then
    echo "${{RED}}✗ gh CLI not authenticated — run: gh auth login${{NC}}"
    exit 1
  fi
  echo "${{GRN}}✓ gh CLI authenticated${{NC}}"

  # Confirm repo access
  if ! gh repo view "$REPO" &>/dev/null; then
    echo "${{RED}}✗ Cannot access repo $REPO — check your PAT scopes${{NC}}"
    exit 1
  fi
  echo "${{GRN}}✓ Repository access confirmed: $REPO${{NC}}"
}}

set_cloud_secrets() {{
  print_header "{cloud_provider} Secrets"
{cloud_secret_prompts}
}}

set_common_secrets() {{
  print_header "Common Secrets"
{common_secret_prompts}
}}

set_optional_secrets() {{
  print_header "Optional Secrets (enhance the pipeline)"
{optional_secret_prompts}
}}

verify_secrets() {{
  print_header "Verification — secrets currently set"
  echo ""
  gh secret list --repo "$REPO" | while read -r line; do
    name=$(echo "$line" | awk '{{print $1}}')
    echo "  ${{GRN}}✓${{NC}} $name"
  done
  echo ""
}}

print_next_steps() {{
  print_header "Next Steps"
  echo ""
  echo "  1. Run the Infrastructure workflow (first time only):"
  echo "     ${{BLU}}gh workflow run infra.yml --repo $REPO${{NC}}"
  echo ""
  echo "  2. After infra completes, run ArgoCD Bootstrap:"
  echo "     ${{BLU}}gh workflow run bootstrap.yml --repo $REPO${{NC}}"
  echo ""
  echo "  3. Push your first commit to main:"
  echo "     ${{BLU}}git push origin main${{NC}}"
  echo ""
  echo "  4. Watch the three-workflow chain in GitHub Actions:"
  echo "     ${{BLU}}gh run watch --repo $REPO${{NC}}"
  echo ""
  echo "  Full guide: docs/DEPLOYMENT_GUIDE.md"
  echo ""
}}

# ── Main ──────────────────────────────────────────────────────────────────────
validate_prerequisites
set_cloud_secrets
set_common_secrets
set_optional_secrets
verify_secrets
print_next_steps

echo "${{GRN}}Bootstrap complete!${{NC}}"
"""


class SecretsAgent(BaseAgent):
    """
    Analyses generated repository to detect required secrets and generates:
    1. docs/DEPLOYMENT_GUIDE.md  — human-readable end-to-end onboarding guide
    2. scripts/bootstrap-secrets.sh — interactive secret-setting CLI script
    """

    def __init__(self):
        super().__init__(
            name="secrets-agent",
            description="Generates secrets manifest and deployment bootstrap guide"
        )

    # ── Public interface ───────────────────────────────────────────────────────

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get("path", ".")).expanduser().resolve()
        overwrite  = params.get("overwrite", False)
        github_user = params.get("github_user", "your-github-username")

        app_name     = self._detect_app_name(repo_path)
        cloud        = self._detect_cloud_provider(repo_path)
        has_snyk     = self._has_snyk(repo_path)
        registry     = self._detect_registry(repo_path, cloud)
        domain_hint  = self._detect_domain_hint(repo_path, app_name)

        self.log(f"Detected cloud provider: {cloud}")
        self.log(f"App name: {app_name}")

        actions = []

        # Generate DEPLOYMENT_GUIDE.md
        guide = self._render_guide(
            app_name, cloud, has_snyk, registry, domain_hint, github_user
        )
        docs_path = repo_path / "docs"
        docs_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(docs_path / "DEPLOYMENT_GUIDE.md", guide, overwrite))

        # Generate bootstrap-secrets.sh
        script = self._render_bootstrap_script(app_name, cloud, github_user)
        scripts_path = repo_path / "scripts"
        scripts_path.mkdir(exist_ok=True)
        script_file = scripts_path / "bootstrap-secrets.sh"
        actions.append(self._safe_write(script_file, script, overwrite))

        # Make bootstrap script executable
        if script_file.exists():
            script_file.chmod(0o755)

        # Collect the secrets manifest for callers (e.g. bridge agent / UI)
        secrets_manifest = self._build_manifest(cloud, has_snyk)

        findings = [
            f"Cloud provider detected: {cloud}",
            f"Container registry: {registry}",
            f"Required secrets: {len([s for s in secrets_manifest if not s['optional']])}",
            f"Optional secrets: {len([s for s in secrets_manifest if s['optional']])}",
            "Bootstrap script: scripts/bootstrap-secrets.sh",
            "Deployment guide: docs/DEPLOYMENT_GUIDE.md",
        ]

        return self.create_result(
            status="success",
            summary=(
                f"Generated deployment guide and secrets bootstrap for {app_name} "
                f"({cloud} / {registry}). "
                f"Run scripts/bootstrap-secrets.sh to set GitHub Actions secrets."
            ),
            data={
                "app_name":        app_name,
                "cloud_provider":  cloud,
                "registry":        registry,
                "secrets_manifest": secrets_manifest,
                "files_generated": [a["path"] for a in actions if a.get("status") == "created"],
            },
            findings=findings,
            actions=actions,
        )

    # ── Detection helpers ──────────────────────────────────────────────────────

    def _detect_app_name(self, repo_path: Path) -> str:
        return repo_path.name or "app"

    def _detect_cloud_provider(self, repo_path: Path) -> str:
        """Read generated Terraform files to determine target cloud."""
        tf_files = list(repo_path.rglob("*.tf"))
        for tf in tf_files:
            try:
                content = tf.read_text()
                if "aws_" in content or "eks" in content.lower():
                    return "AWS"
                if "google_" in content or "gke" in content.lower():
                    return "GCP"
                if "azurerm_" in content or "aks" in content.lower():
                    return "Azure"
            except Exception:
                pass

        # Fall back to checking workflow files
        wf_dir = repo_path / ".github" / "workflows"
        if wf_dir.exists():
            for wf in wf_dir.glob("*.yml"):
                try:
                    content = wf.read_text()
                    if "aws-actions" in content or "AWS_ACCESS_KEY" in content:
                        return "AWS"
                    if "google-github-actions" in content or "GCP_SA_KEY" in content:
                        return "GCP"
                    if "azure/login" in content or "AZURE_CREDENTIALS" in content:
                        return "Azure"
                except Exception:
                    pass

        return "AWS"  # sensible default

    def _has_snyk(self, repo_path: Path) -> bool:
        wf_dir = repo_path / ".github" / "workflows"
        if not wf_dir.exists():
            return False
        for wf in wf_dir.glob("*.yml"):
            try:
                if "snyk" in wf.read_text().lower():
                    return True
            except Exception:
                pass
        return False

    def _detect_registry(self, repo_path: Path, cloud: str) -> str:
        if cloud == "GCP":
            return "Google Artifact Registry (gcr.io)"
        if cloud == "Azure":
            return "Azure Container Registry (ACR)"
        # Check if GHCR is used in workflow
        wf_dir = repo_path / ".github" / "workflows"
        if wf_dir.exists():
            for wf in wf_dir.glob("*.yml"):
                try:
                    if "ghcr.io" in wf.read_text():
                        return "GitHub Container Registry (ghcr.io)"
                except Exception:
                    pass
        return "Amazon ECR"

    def _detect_domain_hint(self, repo_path: Path, app_name: str) -> str:
        """Try to find configured domain from ingress manifests."""
        for manifest in repo_path.rglob("ingress.yaml"):
            try:
                content = manifest.read_text()
                match = re.search(r'host:\s*([^\s]+)', content)
                if match:
                    return match.group(1).replace(app_name + ".", "")
            except Exception:
                pass
        return "your-domain.com"

    # ── Manifest builder ───────────────────────────────────────────────────────

    def _build_manifest(self, cloud: str, has_snyk: bool) -> List[Dict[str, Any]]:
        """Return ordered list of all secrets with metadata."""
        cloud_secrets = {
            "AWS": AWS_SECRETS,
            "GCP": GCP_SECRETS,
            "Azure": AZURE_SECRETS,
        }.get(cloud, AWS_SECRETS)

        manifest = []
        for name, desc, how, used_for, optional in cloud_secrets + COMMON_SECRETS:
            manifest.append({
                "name": name, "description": desc,
                "how_to_get": how, "used_for": used_for,
                "optional": optional, "category": cloud if not optional else "Optional",
                "auto_populated": name in ("ARGOCD_SERVER", "ARGOCD_AUTH_TOKEN"),
            })

        optional_list = list(OPTIONAL_SECRETS)
        if not has_snyk:
            optional_list = [s for s in optional_list if s[0] != "SNYK_TOKEN"]

        for name, desc, how, used_for, optional in optional_list:
            manifest.append({
                "name": name, "description": desc,
                "how_to_get": how, "used_for": used_for,
                "optional": True, "category": "Optional",
                "auto_populated": False,
            })

        return manifest

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render_guide(
        self, app_name: str, cloud: str, has_snyk: bool,
        registry: str, domain_hint: str, github_user: str
    ) -> str:
        cloud_secrets = {
            "AWS": AWS_SECRETS, "GCP": GCP_SECRETS, "Azure": AZURE_SECRETS,
        }.get(cloud, AWS_SECRETS)

        req_rows = []
        for name, desc, how, used_for, optional in cloud_secrets + COMMON_SECRETS:
            if name in ("ARGOCD_SERVER", "ARGOCD_AUTH_TOKEN"):
                continue  # shown in auto-populated table
            req_rows.append(
                f"| `{name}` | {desc} | {how} |"
            )

        opt_rows = []
        for name, desc, how, used_for, optional in OPTIONAL_SECRETS:
            opt_rows.append(f"| `{name}` | {desc} | {how} |")

        req_table = (
            "| Secret | Description | How to get it |\n"
            "|--------|-------------|----------------|\n"
            + "\n".join(req_rows)
        )
        opt_table = (
            "| Secret | Description | How to get it |\n"
            "|--------|-------------|----------------|\n"
            + "\n".join(opt_rows)
        )

        snyk_line = "Snyk" if has_snyk else "Trivy"

        return DEPLOYMENT_GUIDE_TEMPLATE.format(
            app_name=app_name,
            snyk_line=snyk_line,
            registry=registry,
            required_secrets_table=req_table,
            optional_secrets_table=opt_table,
            domain_hint=domain_hint,
        )

    def _render_bootstrap_script(
        self, app_name: str, cloud: str, github_user: str
    ) -> str:
        cloud_secrets = {
            "AWS": AWS_SECRETS, "GCP": GCP_SECRETS, "Azure": AZURE_SECRETS,
        }.get(cloud, AWS_SECRETS)

        def make_prompt(name, desc, how, optional=False):
            return (
                f'  prompt_secret "{name}" \\\n'
                f'    "{desc}" \\\n'
                f'    "{how}" \\\n'
                f'    "{str(optional).lower()}"'
            )

        cloud_prompts = "\n\n".join(
            make_prompt(n, d, h, opt) for n, d, h, _, opt in cloud_secrets
        )
        common_prompts = "\n\n".join(
            make_prompt(n, d, h, opt) for n, d, h, _, opt in COMMON_SECRETS
            if n not in ("ARGOCD_SERVER", "ARGOCD_AUTH_TOKEN")
        )
        optional_prompts = "\n\n".join(
            make_prompt(n, d, h, True) for n, d, h, _, opt in OPTIONAL_SECRETS
        )

        return BOOTSTRAP_SCRIPT_TEMPLATE.format(
            app_name=app_name,
            github_user=github_user,
            cloud_provider=cloud,
            cloud_secret_prompts=cloud_prompts,
            common_secret_prompts=common_prompts,
            optional_secret_prompts=optional_prompts,
        )
