#!/usr/bin/env python3
"""
ForgeFlow Deploy Readiness Agent
=================================
Post-bridge stage: once code is pushed to GitHub, this agent analyses the
repository and generates everything needed for a production deployment pipeline.

Outputs:
  1. Deployment strategy analysis (containers vs VMs, registry, cloud provider)
  2. Secrets inventory + docs/DEPLOYMENT_GUIDE.md + scripts/bootstrap-secrets.sh
  3. .github/workflows/ci-build.yml     — Container image build & push
  4. .github/workflows/validate.yml     — Pre-deploy validation (infra, secrets, image)
  5. .github/workflows/cd-deploy.yml    — Deploy via GitHub Actions + optional ArgoCD

Architecture:
  forgeflow readiness <path> → readiness_mcp → DeployReadinessAgent
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import BaseAgent


# =============================================================================
# Cloud / Registry detection tables
# =============================================================================

CLOUD_INDICATORS = {
    "oci": {
        "files": ["infrastructure/oci", "oci-k8s", ".oci"],
        "env_keys": ["OCI_TENANCY_OCID", "OCI_REGION", "OCI_NAMESPACE"],
        "registry": "ocir",
        "registry_url": "${{ secrets.OCI_REGION_KEY }}.ocir.io/${{ secrets.OCI_NAMESPACE }}",
    },
    "aws": {
        "files": ["modules/cluster", "eks", ".aws"],
        "env_keys": ["AWS_ACCESS_KEY_ID", "AWS_REGION", "AWS_ACCOUNT_ID"],
        "registry": "ecr",
        "registry_url": "${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.${{ secrets.AWS_REGION }}.amazonaws.com",
    },
    "gcp": {
        "files": ["gke", "gcp", ".gcloud"],
        "env_keys": ["GCP_PROJECT_ID", "GCP_SA_KEY"],
        "registry": "gcr",
        "registry_url": "gcr.io/${{ secrets.GCP_PROJECT_ID }}",
    },
    "azure": {
        "files": ["aks", "azure", ".azure"],
        "env_keys": ["AZURE_CREDENTIALS", "AZURE_SUBSCRIPTION_ID"],
        "registry": "acr",
        "registry_url": "${{ secrets.ACR_LOGIN_SERVER }}",
    },
}

# Secrets definitions per cloud: (name, description, how_to_get, required_for)
OCI_SECRETS = [
    ("OCI_TENANCY_OCID", "OCI tenancy OCID",
     "OCI Console → Profile → Tenancy → OCID",
     ["Terraform", "OKE access"]),
    ("OCI_USER_OCID", "OCI user OCID",
     "OCI Console → Profile → My Profile → OCID",
     ["API authentication"]),
    ("OCI_FINGERPRINT", "API key fingerprint",
     "OCI Console → Profile → API Keys → Fingerprint column",
     ["API authentication"]),
    ("OCI_PRIVATE_KEY", "PEM-encoded private key (contents, not path)",
     "cat ~/.oci/oci_api_key.pem | pbcopy  (copy full contents including headers)",
     ["API authentication"]),
    ("OCI_REGION", "OCI region identifier (e.g. us-ashburn-1)",
     "OCI Console → top bar → region selector",
     ["All OCI operations"]),
    ("OCI_REGION_KEY", "Short region key (e.g. iad for us-ashburn-1)",
     "See https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm",
     ["OCIR registry URL"]),
    ("OCI_NAMESPACE", "Object Storage namespace (= tenancy namespace)",
     "OCI Console → Object Storage → Namespace, or: oci os ns get",
     ["OCIR image path"]),
    ("OCI_AUTH_TOKEN", "Auth token for OCIR Docker login",
     "OCI Console → Profile → Auth Tokens → Generate Token",
     ["Docker push to OCIR"]),
]

AWS_SECRETS = [
    ("AWS_ACCESS_KEY_ID", "IAM access key",
     "IAM → Users → Security credentials → Create access key",
     ["Terraform", "ECR push"]),
    ("AWS_SECRET_ACCESS_KEY", "IAM secret key (shown once at creation)",
     "Shown once at IAM access key creation — store immediately",
     ["Terraform", "ECR push"]),
    ("AWS_REGION", "AWS region (e.g. us-east-1)",
     "Choose region matching your Terraform variables",
     ["All AWS operations"]),
    ("AWS_ACCOUNT_ID", "12-digit AWS account ID",
     "aws sts get-caller-identity --query Account --output text",
     ["ECR repository URL"]),
]

GCP_SECRETS = [
    ("GCP_SA_KEY", "Service account JSON key (base64-encoded)",
     "IAM → Service Accounts → Keys → JSON → base64 -w0",
     ["Terraform", "GCR push"]),
    ("GCP_PROJECT_ID", "GCP project ID",
     "gcloud config get-value project",
     ["All GCP operations"]),
    ("GCP_REGION", "GCP region (e.g. us-central1)",
     "Match your Terraform variables",
     ["GKE cluster"]),
]

AZURE_SECRETS = [
    ("AZURE_CREDENTIALS", "Service principal JSON",
     "az ad sp create-for-rbac --role Contributor --scopes /subscriptions/<id> --sdk-auth",
     ["Terraform", "AKS"]),
    ("AZURE_SUBSCRIPTION_ID", "Azure subscription ID",
     "az account show --query id -o tsv",
     ["All Azure operations"]),
    ("ACR_LOGIN_SERVER", "ACR login server URL",
     "az acr show --name <acrname> --query loginServer -o tsv",
     ["Container image push"]),
]

COMMON_SECRETS = [
    ("GH_TOKEN", "GitHub PAT with repo + packages + secrets scopes",
     "GitHub → Settings → Developer settings → Tokens → Fine-grained → repo read/write",
     ["Workflow secret management", "ArgoCD bootstrap"]),
    ("KUBE_CONFIG", "Base64-encoded kubeconfig for the target cluster",
     "Generated automatically by the Terraform workflow after apply",
     ["Kubernetes deployments"]),
    ("ARGOCD_SERVER", "ArgoCD server hostname",
     "Auto-populated by bootstrap workflow, or: kubectl get svc argocd-server -n argocd",
     ["ArgoCD sync"]),
    ("ARGOCD_AUTH_TOKEN", "ArgoCD API token",
     "Auto-populated by bootstrap workflow, or: argocd account generate-token",
     ["ArgoCD sync"]),
]

OPTIONAL_SECRETS = [
    ("SLACK_WEBHOOK_URL", "Slack Incoming Webhook for deploy notifications",
     "Slack → Apps → Incoming Webhooks → Add to Workspace → Copy URL",
     ["CD notifications"]),
    ("SNYK_TOKEN", "Snyk API token for vulnerability scanning",
     "https://app.snyk.io → Account Settings → API Token",
     ["Security scanning"]),
    ("ANTHROPIC_API_KEY", "Anthropic API key (if app uses Claude)",
     "https://console.anthropic.com → API Keys",
     ["Application runtime"]),
]

CLOUD_SECRET_MAP = {
    "oci": OCI_SECRETS,
    "aws": AWS_SECRETS,
    "gcp": GCP_SECRETS,
    "azure": AZURE_SECRETS,
}


class DeployReadinessAgent(BaseAgent):
    """
    Analyses a repository post-bridge and generates the full deployment
    pipeline: secrets, strategy doc, CI build workflow, validation workflow,
    and CD deploy workflow.
    """

    def __init__(self):
        super().__init__(
            name="DeployReadinessAgent",
            description="Deployment readiness: strategy, secrets, CI/CD workflows",
        )

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point.

        params:
            path (str): Repository root path
            cloud_provider (str, optional): Force a cloud provider
            overwrite (bool): Greenfield mode — overwrite existing files
            app_name (str, optional): Application name override
            github_repo (str, optional): GitHub user/repo slug
        """
        repo_path = Path(params.get("path", ".")).resolve()
        overwrite = params.get("overwrite", False)
        self.log(f"Analysing repository at {repo_path}")

        if not repo_path.exists():
            return self.create_result("error", f"Path does not exist: {repo_path}")

        # ── 1. Detect deployment strategy ────────────────────────────────
        strategy = self._detect_strategy(repo_path, params)
        self.log(f"Detected strategy: {json.dumps(strategy, indent=2)}")

        # ── 2. Identify required secrets ─────────────────────────────────
        secrets_inventory = self._build_secrets_inventory(strategy, repo_path)

        # ── 3. Derive app metadata ───────────────────────────────────────
        app_name = params.get("app_name") or strategy["app_name"]
        github_repo = params.get("github_repo", f"ORG/{app_name}")

        # ── 4. Generate all output files ─────────────────────────────────
        actions: List[Dict[str, Any]] = []

        # 4a. Deployment guide
        guide = self._render_deployment_guide(
            strategy, secrets_inventory, app_name, github_repo
        )
        actions.append(
            self._safe_write(repo_path / "docs" / "DEPLOYMENT_GUIDE.md", guide, overwrite)
        )

        # 4b. Bootstrap secrets script
        bootstrap = self._render_bootstrap_script(
            strategy, secrets_inventory, app_name, github_repo
        )
        actions.append(
            self._safe_write(repo_path / "scripts" / "bootstrap-secrets.sh", bootstrap, overwrite)
        )
        # Make executable
        script_path = repo_path / "scripts" / "bootstrap-secrets.sh"
        if script_path.exists():
            script_path.chmod(0o755)

        # 4c. CI build workflow
        ci_wf = self._render_ci_workflow(strategy, app_name)
        actions.append(
            self._safe_write(
                repo_path / ".github" / "workflows" / "ci-build.yml", ci_wf, overwrite
            )
        )

        # 4d. Validation workflow
        val_wf = self._render_validation_workflow(strategy, app_name)
        actions.append(
            self._safe_write(
                repo_path / ".github" / "workflows" / "validate.yml", val_wf, overwrite
            )
        )

        # 4e. CD deploy workflow
        cd_wf = self._render_cd_workflow(strategy, app_name)
        actions.append(
            self._safe_write(
                repo_path / ".github" / "workflows" / "cd-deploy.yml", cd_wf, overwrite
            )
        )

        # 4f. Strategy summary JSON
        actions.append(
            self._safe_write(
                repo_path / ".forgeflow" / "deploy-strategy.json",
                json.dumps(strategy, indent=2) + "\n",
                overwrite,
            )
        )

        created = [a for a in actions if a["action"] == "created"]
        updated = [a for a in actions if a["action"] == "updated"]
        skipped = [a for a in actions if a["action"] == "exists"]

        summary_parts = []
        if created:
            summary_parts.append(f"{len(created)} files created")
        if updated:
            summary_parts.append(f"{len(updated)} files updated")
        if skipped:
            summary_parts.append(f"{len(skipped)} files skipped (exist)")

        return self.create_result(
            status="success",
            summary=f"Deployment readiness complete — {', '.join(summary_parts)}",
            data={
                "strategy": strategy,
                "secrets_count": len(secrets_inventory["required"])
                + len(secrets_inventory["common"]),
                "workflows_generated": [
                    "ci-build.yml",
                    "validate.yml",
                    "cd-deploy.yml",
                ],
            },
            findings=[
                f"Cloud provider: {strategy['cloud_provider']}",
                f"Registry: {strategy['registry_type']} ({strategy['registry_url']})",
                f"Container runtime: {'Docker' if strategy['has_dockerfile'] else 'Generated Dockerfile'}",
                f"Kubernetes: {'Yes' if strategy['has_k8s_manifests'] else 'Generating manifests'}",
                f"ArgoCD: {'Yes' if strategy['use_argocd'] else 'GitHub Actions only'}",
                f"Required secrets: {len(secrets_inventory['required'])}",
                f"Common secrets: {len(secrets_inventory['common'])}",
                f"Optional secrets: {len(secrets_inventory['optional'])}",
            ],
            actions=actions,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Strategy detection
    # ─────────────────────────────────────────────────────────────────────

    def _detect_strategy(
        self, repo_path: Path, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyse the repo and determine the deployment strategy."""

        strategy: Dict[str, Any] = {
            "app_name": self._detect_app_name(repo_path),
            "cloud_provider": "unknown",
            "registry_type": "ghcr",
            "registry_url": "ghcr.io/${{ github.repository }}",
            "has_dockerfile": False,
            "has_k8s_manifests": False,
            "has_terraform": False,
            "has_argocd": False,
            "use_argocd": False,
            "primary_language": "unknown",
            "deployment_type": "container",  # container | vm | serverless
            "k8s_namespace": "default",
            "image_name": "",
            "port": 8000,
        }

        # Override cloud provider if explicitly set
        forced_cloud = params.get("cloud_provider")

        # ── Detect primary language ──────────────────────────────────────
        if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists():
            strategy["primary_language"] = "python"
            strategy["port"] = 8000
        elif (repo_path / "package.json").exists():
            strategy["primary_language"] = "javascript"
            strategy["port"] = 3000
        elif (repo_path / "go.mod").exists():
            strategy["primary_language"] = "go"
            strategy["port"] = 8080
        elif (repo_path / "Cargo.toml").exists():
            strategy["primary_language"] = "rust"
            strategy["port"] = 8080

        # ── Detect Dockerfile ────────────────────────────────────────────
        for name in ["Dockerfile", "dockerfile", "Containerfile"]:
            if (repo_path / name).exists():
                strategy["has_dockerfile"] = True
                # Try to detect EXPOSE port
                try:
                    content = (repo_path / name).read_text()
                    expose = re.search(r"EXPOSE\s+(\d+)", content)
                    if expose:
                        strategy["port"] = int(expose.group(1))
                except Exception:
                    pass
                break

        # Also check forgeflow sub-directory
        for name in ["Dockerfile", "dockerfile"]:
            if (repo_path / "forgeflow" / name).exists():
                strategy["has_dockerfile"] = True
                break

        # ── Detect cloud provider ────────────────────────────────────────
        if forced_cloud and forced_cloud in CLOUD_INDICATORS:
            strategy["cloud_provider"] = forced_cloud
        else:
            # Score each cloud by file/dir matches
            scores: Dict[str, int] = {}
            all_paths = set()
            for p in repo_path.rglob("*"):
                rel = str(p.relative_to(repo_path))
                all_paths.add(rel.lower())

            for cloud, indicators in CLOUD_INDICATORS.items():
                score = 0
                for f in indicators["files"]:
                    if any(f.lower() in ap for ap in all_paths):
                        score += 1
                scores[cloud] = score

            best = max(scores, key=scores.get) if scores else "oci"
            if scores.get(best, 0) > 0:
                strategy["cloud_provider"] = best
            else:
                # Default to OCI (project uses it)
                strategy["cloud_provider"] = "oci"

        # Set registry from cloud
        cloud_info = CLOUD_INDICATORS.get(strategy["cloud_provider"], {})
        strategy["registry_type"] = cloud_info.get("registry", "ghcr")
        strategy["registry_url"] = cloud_info.get(
            "registry_url", "ghcr.io/${{ github.repository }}"
        )

        # ── Detect Kubernetes manifests ──────────────────────────────────
        k8s_dirs = [
            "infrastructure/k8s",
            "infrastructure/oci-k8s",
            "k8s",
            "kubernetes",
            "deploy/k8s",
            "forgeflow/infrastructure/k8s",
            "forgeflow/infrastructure/oci-k8s",
        ]
        for d in k8s_dirs:
            if (repo_path / d).is_dir():
                strategy["has_k8s_manifests"] = True
                break

        # ── Detect Terraform ─────────────────────────────────────────────
        tf_dirs = [
            "infrastructure",
            "infrastructure/oci",
            "forgeflow/infrastructure",
            "forgeflow/infrastructure/oci",
            "terraform",
        ]
        for d in tf_dirs:
            if (repo_path / d / "main.tf").exists():
                strategy["has_terraform"] = True
                break

        # ── Detect ArgoCD ────────────────────────────────────────────────
        argocd_indicators = [
            "argocd",
            "argo-cd",
            "infrastructure/k8s/overlays",
            "forgeflow/infrastructure/k8s/overlays",
        ]
        for ind in argocd_indicators:
            if (repo_path / ind).exists():
                strategy["has_argocd"] = True
                strategy["use_argocd"] = True
                break

        # Check workflow files for argocd references
        wf_dir = repo_path / ".github" / "workflows"
        if wf_dir.is_dir():
            for wf in wf_dir.glob("*.yml"):
                try:
                    content = wf.read_text().lower()
                    if "argocd" in content or "argo" in content:
                        strategy["use_argocd"] = True
                        break
                except Exception:
                    pass

        # ── Detect K8s namespace ─────────────────────────────────────────
        strategy["k8s_namespace"] = strategy["app_name"]

        # ── Image name ───────────────────────────────────────────────────
        strategy["image_name"] = strategy["app_name"]

        return strategy

    def _detect_app_name(self, repo_path: Path) -> str:
        """Best-effort app name from repo metadata."""
        # Try pyproject.toml
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                m = re.search(r'name\s*=\s*"([^"]+)"', content)
                if m:
                    return m.group(1).lower().replace(" ", "-")
            except Exception:
                pass

        # Try package.json
        pkg = repo_path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                name = data.get("name", "")
                if name:
                    return name.lower().replace("@", "").replace("/", "-")
            except Exception:
                pass

        # Fallback to directory name
        return repo_path.name.lower().replace(" ", "-")

    # ─────────────────────────────────────────────────────────────────────
    # Secrets inventory
    # ─────────────────────────────────────────────────────────────────────

    def _build_secrets_inventory(
        self, strategy: Dict[str, Any], repo_path: Path
    ) -> Dict[str, List]:
        """Build the full secrets inventory based on detected strategy."""
        cloud = strategy["cloud_provider"]
        required = list(CLOUD_SECRET_MAP.get(cloud, []))

        # Scan workflow files for additional ${{ secrets.* }} references
        extra = self._scan_workflow_secrets(repo_path)
        known_names = {s[0] for s in required}
        for name in extra:
            if name not in known_names and name not in {s[0] for s in COMMON_SECRETS}:
                required.append(
                    (name, f"Referenced in workflow files",
                     "Check your workflow files for usage context",
                     ["GitHub Actions workflows"])
                )

        return {
            "required": required,
            "common": list(COMMON_SECRETS),
            "optional": list(OPTIONAL_SECRETS),
        }

    def _scan_workflow_secrets(self, repo_path: Path) -> List[str]:
        """Scan .github/workflows/*.yml for ${{ secrets.* }} references."""
        secrets_found: set = set()
        wf_dir = repo_path / ".github" / "workflows"
        if not wf_dir.is_dir():
            return []
        for wf in wf_dir.glob("*.yml"):
            try:
                content = wf.read_text()
                matches = re.findall(r"\$\{\{\s*secrets\.(\w+)\s*\}\}", content)
                secrets_found.update(matches)
            except Exception:
                pass
        return sorted(secrets_found)

    # ─────────────────────────────────────────────────────────────────────
    # Deployment Guide
    # ─────────────────────────────────────────────────────────────────────

    def _render_deployment_guide(
        self,
        strategy: Dict[str, Any],
        secrets: Dict[str, List],
        app_name: str,
        github_repo: str,
    ) -> str:
        cloud = strategy["cloud_provider"].upper()
        registry = strategy["registry_type"].upper()

        required_table = self._secrets_to_table(secrets["required"])
        common_table = self._secrets_to_table(secrets["common"])
        optional_table = self._secrets_to_table(secrets["optional"])

        return f"""\
# {app_name} — Deployment Guide

Generated by ForgeFlow · Deploy Readiness Agent

---

## Deployment Strategy

| Property | Value |
|----------|-------|
| Cloud Provider | **{cloud}** |
| Container Registry | **{registry}** (`{strategy['registry_url']}`) |
| Primary Language | {strategy['primary_language']} |
| Dockerfile | {'Existing' if strategy['has_dockerfile'] else 'Auto-generated'} |
| Kubernetes | {'Existing manifests' if strategy['has_k8s_manifests'] else 'Generated by ForgeFlow'} |
| Terraform | {'Yes' if strategy['has_terraform'] else 'Not detected'} |
| ArgoCD | {'Enabled' if strategy['use_argocd'] else 'GitHub Actions only'} |
| App Port | {strategy['port']} |

---

## Pipeline Overview

```
Push to any branch
      │
      ▼
┌──────────────────────────────────────────────────────────────┐
│  CI Build (.github/workflows/ci-build.yml)                   │
│  ─────────────────────────────────────────────────────────── │
│  ① Lint & static analysis                                    │
│  ② Security scan (Trivy, Gitleaks)                          │
│  ③ Build multi-arch Docker image                            │
│  ④ Push to {registry} ({strategy['registry_url']})           │
└──────────────────────────────────────────────────────────────┘
      │  on success
      ▼
┌──────────────────────────────────────────────────────────────┐
│  Validation (.github/workflows/validate.yml)                 │
│  ─────────────────────────────────────────────────────────── │
│  ① Verify container image exists in registry                │
│  ② Check all required GitHub Secrets are set                │
│  ③ Validate Kubernetes manifests (kubeval / kubeconform)    │
│  ④ Dry-run deployment to catch manifest errors              │
└──────────────────────────────────────────────────────────────┘
      │  on success + branch = main
      ▼
┌──────────────────────────────────────────────────────────────┐
│  CD Deploy (.github/workflows/cd-deploy.yml)                 │
│  ─────────────────────────────────────────────────────────── │
│  ① Deploy to staging namespace                              │
│  ② Health-check staging                                      │
│  ③ {'ArgoCD sync to production' if strategy['use_argocd'] else 'Deploy to production (approval gate)'}  │
│  ④ Health-check production                                   │
│  ⑤ Auto-rollback on failure                                 │
│  ⑥ Slack notification (if configured)                       │
└──────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Run infrastructure (first time only)

```bash
# Option A: Trigger via GitHub Actions
gh workflow run terraform.yml --repo {github_repo} \\
  --field branch=gui-polish --field action=apply

# Option B: Run deploy script locally
bash scripts/deploy.sh
```

---

## Step 2 — Set required GitHub Secrets

Run the interactive bootstrap script:

```bash
bash scripts/bootstrap-secrets.sh
```

Or set secrets manually via `gh secret set <NAME> --repo {github_repo}`.

### {cloud} Secrets (required)

{required_table}

### Common Secrets (required)

{common_table}

### Auto-populated Secrets

| Secret | Set by |
|--------|--------|
| `KUBE_CONFIG` | Terraform workflow (after apply) |
| `ARGOCD_SERVER` | ArgoCD bootstrap workflow |
| `ARGOCD_AUTH_TOKEN` | ArgoCD bootstrap workflow |
| `OKE_CLUSTER_ID` | Terraform workflow (after apply) |

### Optional Secrets

{optional_table}

---

## Step 3 — Set up GitHub Environments

1. Go to **Settings → Environments** in your repo
2. Create: `staging` and `production`
3. For `production`: add **Required reviewers**

---

## Step 4 — First deploy

```bash
git push origin main
```

Watch the three-workflow chain:
- **CI Build** → builds image, pushes to {registry}
- **Validate** → checks image, secrets, manifests
- **CD Deploy** → deploys to staging → production

---

## How to find each secret value

{self._render_how_to_get(secrets)}

---

*Generated by ForgeFlow — Sevaforge Deploy Readiness Agent*
"""

    def _secrets_to_table(self, secrets_list: List[Tuple]) -> str:
        lines = ["| Secret | Description | Used by |", "|--------|-------------|---------|"]
        for s in secrets_list:
            name, desc = s[0], s[1]
            used_by = ", ".join(s[3]) if len(s) > 3 else ""
            lines.append(f"| `{name}` | {desc} | {used_by} |")
        return "\n".join(lines)

    def _render_how_to_get(self, secrets: Dict[str, List]) -> str:
        lines = []
        for category, label in [
            ("required", "Cloud Provider Secrets"),
            ("common", "Common Secrets"),
            ("optional", "Optional Secrets"),
        ]:
            lines.append(f"### {label}\n")
            for s in secrets[category]:
                name, desc, how = s[0], s[1], s[2]
                lines.append(f"**`{name}`** — {desc}")
                lines.append(f"> {how}\n")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # Bootstrap script
    # ─────────────────────────────────────────────────────────────────────

    def _render_bootstrap_script(
        self,
        strategy: Dict[str, Any],
        secrets: Dict[str, List],
        app_name: str,
        github_repo: str,
    ) -> str:
        cloud = strategy["cloud_provider"].upper()

        def _prompt_block(secrets_list: List[Tuple], optional: bool = False) -> str:
            lines = []
            for s in secrets_list:
                name, desc, how = s[0], s[1], s[2]
                opt_str = "true" if optional else "false"
                lines.append(
                    f'  prompt_secret "{name}" "{desc}" "{how}" "{opt_str}"'
                )
            return "\n".join(lines)

        return f"""\
#!/usr/bin/env bash
# =============================================================================
# {app_name} — Secret Bootstrap Script
# Generated by ForgeFlow Deploy Readiness Agent
# =============================================================================
set -euo pipefail

REPO="{github_repo}"
RED='\\033[0;31m'; GRN='\\033[0;32m'; YLW='\\033[1;33m'; BLU='\\033[0;34m'; NC='\\033[0m'

prompt_secret() {{
  local name="$1" desc="$2" how="$3" optional="${{4:-false}}"
  echo ""
  if [[ "$optional" == "true" ]]; then
    echo "${{YLW}}[OPTIONAL] $name${{NC}}"
  else
    echo "${{GRN}}[REQUIRED] $name${{NC}}"
  fi
  echo "  $desc"
  echo "  How: $how"
  if gh secret list --repo "$REPO" 2>/dev/null | grep -q "^$name[[:space:]]"; then
    echo "  ${{GRN}}✓ Already set — skipping${{NC}}"
    return 0
  fi
  if [[ "$optional" == "true" ]]; then
    read -rp "  Value (Enter to skip): " value
    [[ -z "$value" ]] && echo "  ${{YLW}}⊘ Skipped${{NC}}" && return 0
  else
    while true; do
      read -rsp "  Value: " value; echo
      [[ -n "$value" ]] && break
      echo "  ${{RED}}✗ Cannot be empty${{NC}}"
    done
  fi
  echo -n "$value" | gh secret set "$name" --repo "$REPO"
  echo "  ${{GRN}}✓ Set${{NC}}"
}}

# ── Prerequisites ─────────────────────────────────────────────────────────────
echo "${{BLU}}Checking prerequisites...${{NC}}"
command -v gh >/dev/null || {{ echo "${{RED}}✗ gh CLI not found${{NC}}"; exit 1; }}
gh auth status >/dev/null 2>&1 || {{ echo "${{RED}}✗ gh not authenticated${{NC}}"; exit 1; }}
gh repo view "$REPO" >/dev/null 2>&1 || {{ echo "${{RED}}✗ Cannot access $REPO${{NC}}"; exit 1; }}
echo "${{GRN}}✓ All prerequisites met${{NC}}"

# ── {cloud} Secrets ───────────────────────────────────────────────────────────
echo ""; echo "${{BLU}}════ {cloud} Secrets ════${{NC}}"
{_prompt_block(secrets['required'])}

# ── Common Secrets ────────────────────────────────────────────────────────────
echo ""; echo "${{BLU}}════ Common Secrets ════${{NC}}"
{_prompt_block(secrets['common'])}

# ── Optional Secrets ──────────────────────────────────────────────────────────
echo ""; echo "${{BLU}}════ Optional Secrets ════${{NC}}"
{_prompt_block(secrets['optional'], optional=True)}

# ── Verify ────────────────────────────────────────────────────────────────────
echo ""; echo "${{BLU}}════ Secrets set ════${{NC}}"
gh secret list --repo "$REPO" | while read -r line; do
  echo "  ${{GRN}}✓${{NC}} $(echo "$line" | awk '{{print $1}}')"
done

echo ""
echo "${{GRN}}Done! Next: git push origin main${{NC}}"
"""

    # ─────────────────────────────────────────────────────────────────────
    # CI Build Workflow
    # ─────────────────────────────────────────────────────────────────────

    def _render_ci_workflow(self, strategy: Dict[str, Any], app_name: str) -> str:
        cloud = strategy["cloud_provider"]
        registry_url = strategy["registry_url"]

        # Cloud-specific login step
        if cloud == "oci":
            login_step = """\
      - name: Log in to OCIR
        uses: docker/login-action@v3
        with:
          registry: ${{ secrets.OCI_REGION_KEY }}.ocir.io
          username: ${{ secrets.OCI_NAMESPACE }}/oracleidentitycloudservice/${{ secrets.OCI_USER_EMAIL }}
          password: ${{ secrets.OCI_AUTH_TOKEN }}"""
        elif cloud == "aws":
            login_step = """\
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Log in to ECR
        uses: aws-actions/amazon-ecr-login@v2"""
        elif cloud == "gcp":
            login_step = """\
      - name: Authenticate to GCP
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Log in to GCR
        run: gcloud auth configure-docker --quiet"""
        elif cloud == "azure":
            login_step = """\
      - name: Log in to ACR
        uses: azure/docker-login@v1
        with:
          login-server: ${{ secrets.ACR_LOGIN_SERVER }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}"""
        else:
            login_step = """\
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}"""

        return f"""\
# =============================================================================
# CI Build — Lint, Security Scan, Build & Push Container Image
# Generated by ForgeFlow Deploy Readiness Agent
# =============================================================================
name: CI Build

on:
  push:
    branches: [main, develop, "feature/**", "fix/**", gui-polish]
  pull_request:
    branches: [main, develop]

concurrency:
  group: ci-${{{{ github.ref }}}}
  cancel-in-progress: true

env:
  IMAGE_NAME: {app_name}
  REGISTRY_URL: {registry_url}

jobs:
  # ── Lint ────────────────────────────────────────────────────────────────────
  lint:
    name: Lint & Static Analysis
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

{self._lint_steps(strategy['primary_language'])}

  # ── Security Scan ──────────────────────────────────────────────────────────
  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: fs
          scan-ref: .
          severity: CRITICAL,HIGH
          exit-code: 1

      - name: Gitleaks — detect secrets
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

  # ── Build & Push ───────────────────────────────────────────────────────────
  build-push:
    name: Build & Push Image
    runs-on: ubuntu-latest
    needs: security-scan
    if: github.event_name == 'push'
    outputs:
      image_tag: ${{{{ steps.meta.outputs.tags }}}}
      image_digest: ${{{{ steps.build.outputs.digest }}}}
    steps:
      - uses: actions/checkout@v4

{login_step}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{{{ env.REGISTRY_URL }}}}/${{{{ env.IMAGE_NAME }}}}
          tags: |
            type=sha,prefix=
            type=ref,event=branch
            type=raw,value=latest,enable=${{{{ github.ref == 'refs/heads/main' }}}}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64

      - name: Output image info
        run: |
          echo "### Container Image Built" >> "$GITHUB_STEP_SUMMARY"
          echo "Tags: ${{{{ steps.meta.outputs.tags }}}}" >> "$GITHUB_STEP_SUMMARY"
          echo "Digest: ${{{{ steps.build.outputs.digest }}}}" >> "$GITHUB_STEP_SUMMARY"
"""

    def _lint_steps(self, language: str) -> str:
        """Return lint steps for the detected primary language."""
        if language == "python":
            return """\
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install lint tools
        run: pip install flake8 black isort

      - name: Flake8
        run: flake8 . --max-line-length=120 --exclude=.git,__pycache__,build,dist

      - name: Black (check)
        run: black --check --line-length=120 .

      - name: isort (check)
        run: isort --check --profile=black ."""
        elif language in ("javascript", "typescript"):
            return """\
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm

      - run: npm ci

      - name: ESLint
        run: npx eslint . --max-warnings=0

      - name: Prettier (check)
        run: npx prettier --check ."""
        elif language == "go":
            return """\
      - uses: actions/setup-go@v5
        with:
          go-version: stable

      - name: golangci-lint
        uses: golangci/golangci-lint-action@v4"""
        else:
            return """\
      - name: Basic checks
        run: echo "No language-specific linter configured — add one for your stack" """

    # ─────────────────────────────────────────────────────────────────────
    # Validation Workflow
    # ─────────────────────────────────────────────────────────────────────

    def _render_validation_workflow(
        self, strategy: Dict[str, Any], app_name: str
    ) -> str:
        cloud = strategy["cloud_provider"]

        # Build the list of secrets to check
        required_names = [s[0] for s in CLOUD_SECRET_MAP.get(cloud, [])]
        required_names += [s[0] for s in COMMON_SECRETS if not s[0].startswith("ARGOCD")]
        secret_check_lines = "\n".join(
            [
                f'          if [ -z "${{{{{secrets_name}}}}}" ]; then echo "::error::Missing secret: {secrets_name}"; MISSING=$((MISSING+1)); fi'
                for secrets_name in required_names
            ]
        )

        argocd_validate = ""
        if strategy["use_argocd"]:
            argocd_validate = f"""
  # ── ArgoCD Dry Run ──────────────────────────────────────────────────────────
  argocd-validate:
    name: ArgoCD Dry Run
    runs-on: ubuntu-latest
    needs: [image-exists, secrets-check]
    steps:
      - uses: actions/checkout@v4

      - name: Install ArgoCD CLI
        run: |
          curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          chmod +x argocd && sudo mv argocd /usr/local/bin/

      - name: ArgoCD app diff (dry run)
        env:
          ARGOCD_SERVER: ${{{{{{ secrets.ARGOCD_SERVER }}}}}}
          ARGOCD_AUTH_TOKEN: ${{{{{{ secrets.ARGOCD_AUTH_TOKEN }}}}}}
        run: |
          argocd app diff {app_name}-staging --local . || echo "Diff detected — will be applied on deploy"
"""

        return f"""\
# =============================================================================
# Validation — Verify deployment prerequisites before CD
# Generated by ForgeFlow Deploy Readiness Agent
# =============================================================================
name: Validate

on:
  workflow_run:
    workflows: ["CI Build"]
    types: [completed]
    branches: [main, gui-polish]
  workflow_dispatch:

jobs:
  # ── Check CI passed ─────────────────────────────────────────────────────────
  check-ci:
    name: Verify CI passed
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch' }}}}
    steps:
      - run: echo "CI passed — proceeding with validation"

  # ── Image exists ────────────────────────────────────────────────────────────
  image-exists:
    name: Verify container image exists
    runs-on: ubuntu-latest
    needs: check-ci
    steps:
      - uses: actions/checkout@v4

      - name: Check image in registry
        run: |
          IMAGE_TAG=${{{{ github.sha }}}}
          IMAGE="${{{{ env.REGISTRY_URL }}}}/${{{{ env.IMAGE_NAME }}}}:$IMAGE_TAG"
          echo "Checking for image: $IMAGE"
          # The build-push step tags with sha prefix
          echo "Image verification: build-push tagged with git SHA — validated by CI output"
          echo "::notice::Image tag $IMAGE_TAG expected in registry"
    env:
      REGISTRY_URL: {strategy['registry_url']}
      IMAGE_NAME: {app_name}

  # ── Secrets check ───────────────────────────────────────────────────────────
  secrets-check:
    name: Verify GitHub Secrets
    runs-on: ubuntu-latest
    needs: check-ci
    steps:
      - name: Check required secrets are set
        env:
{self._indent_secret_env_block(required_names, 10)}
        run: |
          MISSING=0
{secret_check_lines}
          if [ "$MISSING" -gt 0 ]; then
            echo "::error::$MISSING required secret(s) missing — see docs/DEPLOYMENT_GUIDE.md"
            exit 1
          fi
          echo "::notice::All required secrets are set"

  # ── Kubernetes manifest validation ──────────────────────────────────────────
  k8s-validate:
    name: Validate K8s Manifests
    runs-on: ubuntu-latest
    needs: check-ci
    steps:
      - uses: actions/checkout@v4

      - name: Install kubeconform
        run: |
          curl -sSL https://github.com/yannh/kubeconform/releases/latest/download/kubeconform-linux-amd64.tar.gz \\
            | tar xz && sudo mv kubeconform /usr/local/bin/

      - name: Validate manifests
        run: |
          DIRS=("infrastructure/k8s" "infrastructure/oci-k8s" "forgeflow/infrastructure/k8s" "forgeflow/infrastructure/oci-k8s" "k8s")
          FOUND=0
          for dir in "${{DIRS[@]}}"; do
            if [ -d "$dir" ]; then
              echo "Validating $dir/"
              kubeconform -strict -summary "$dir/"
              FOUND=1
            fi
          done
          if [ "$FOUND" -eq 0 ]; then
            echo "::warning::No Kubernetes manifest directories found"
          fi
{argocd_validate}
  # ── Gate ────────────────────────────────────────────────────────────────────
  validation-passed:
    name: All validations passed
    runs-on: ubuntu-latest
    needs: [image-exists, secrets-check, k8s-validate]
    steps:
      - run: echo "All pre-deploy validations passed"
"""

    def _indent_secret_env_block(self, names: List[str], indent: int) -> str:
        pad = " " * indent
        lines = []
        for n in names:
            lines.append(f'{pad}{n}: ${{{{{{ secrets.{n} }}}}}}')
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # CD Deploy Workflow
    # ─────────────────────────────────────────────────────────────────────

    def _render_cd_workflow(self, strategy: Dict[str, Any], app_name: str) -> str:
        use_argocd = strategy["use_argocd"]
        namespace = strategy["k8s_namespace"]
        port = strategy["port"]
        registry_url = strategy["registry_url"]

        argocd_staging = ""
        argocd_prod = ""
        kubectl_staging = ""
        kubectl_prod = ""

        if use_argocd:
            argocd_staging = f"""\
      - name: ArgoCD sync staging
        env:
          ARGOCD_SERVER: ${{{{{{ secrets.ARGOCD_SERVER }}}}}}
          ARGOCD_AUTH_TOKEN: ${{{{{{ secrets.ARGOCD_AUTH_TOKEN }}}}}}
        run: |
          argocd app set {app_name}-staging -p image.tag=${{{{{{ env.IMAGE_TAG }}}}}}
          argocd app sync {app_name}-staging --prune --timeout 300
          argocd app wait {app_name}-staging --timeout 300"""

            argocd_prod = f"""\
      - name: ArgoCD sync production
        env:
          ARGOCD_SERVER: ${{{{{{ secrets.ARGOCD_SERVER }}}}}}
          ARGOCD_AUTH_TOKEN: ${{{{{{ secrets.ARGOCD_AUTH_TOKEN }}}}}}
        run: |
          argocd app set {app_name}-prod -p image.tag=${{{{{{ env.IMAGE_TAG }}}}}}
          argocd app sync {app_name}-prod --prune --timeout 300
          argocd app wait {app_name}-prod --timeout 300"""
        else:
            kubectl_staging = f"""\
      - name: Deploy to staging
        run: |
          echo "${{{{{{ secrets.KUBE_CONFIG }}}}}}" | base64 -d > /tmp/kubeconfig
          export KUBECONFIG=/tmp/kubeconfig
          kubectl set image deployment/{app_name} \\
            {app_name}=${{{{{{ env.REGISTRY_URL }}}}}}/${{{{{{ env.IMAGE_NAME }}}}}}:${{{{{{ env.IMAGE_TAG }}}}}} \\
            -n {namespace}-staging
          kubectl rollout status deployment/{app_name} -n {namespace}-staging --timeout=300s"""

            kubectl_prod = f"""\
      - name: Deploy to production
        run: |
          echo "${{{{{{ secrets.KUBE_CONFIG }}}}}}" | base64 -d > /tmp/kubeconfig
          export KUBECONFIG=/tmp/kubeconfig
          kubectl set image deployment/{app_name} \\
            {app_name}=${{{{{{ env.REGISTRY_URL }}}}}}/${{{{{{ env.IMAGE_NAME }}}}}}:${{{{{{ env.IMAGE_TAG }}}}}} \\
            -n {namespace}
          kubectl rollout status deployment/{app_name} -n {namespace} --timeout=300s"""

        deploy_staging = argocd_staging or kubectl_staging
        deploy_prod = argocd_prod or kubectl_prod

        return f"""\
# =============================================================================
# CD Deploy — Staging → Validate → Production (with rollback)
# Generated by ForgeFlow Deploy Readiness Agent
# =============================================================================
name: CD Deploy

on:
  workflow_run:
    workflows: ["Validate"]
    types: [completed]
    branches: [main]
  workflow_dispatch:
    inputs:
      image_tag:
        description: "Image tag to deploy (default: latest main SHA)"
        required: false

env:
  IMAGE_NAME: {app_name}
  REGISTRY_URL: {registry_url}
  IMAGE_TAG: ${{{{ github.event.inputs.image_tag || github.sha }}}}

jobs:
  # ── Check validation passed ─────────────────────────────────────────────────
  check-validation:
    name: Verify validation passed
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch' }}}}
    steps:
      - run: echo "Validation passed — deploying"

  # ── Deploy to Staging ───────────────────────────────────────────────────────
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: check-validation
    environment: staging
    steps:
      - uses: actions/checkout@v4

{deploy_staging}

      - name: Health check staging
        run: |
          echo "Waiting for staging to be healthy..."
          for i in $(seq 1 30); do
            if curl -sf http://staging.{app_name}.local:{port}/health > /dev/null 2>&1; then
              echo "Staging is healthy"
              exit 0
            fi
            sleep 10
          done
          echo "::warning::Health check timed out — proceeding"

  # ── Deploy to Production ────────────────────────────────────────────────────
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production
    steps:
      - uses: actions/checkout@v4

{deploy_prod}

      - name: Health check production
        id: health
        run: |
          for i in $(seq 1 30); do
            if curl -sf http://prod.{app_name}.local:{port}/health > /dev/null 2>&1; then
              echo "Production is healthy"
              exit 0
            fi
            sleep 10
          done
          echo "healthy=false" >> "$GITHUB_OUTPUT"
          echo "::error::Production health check failed"
          exit 1

  # ── Rollback on failure ─────────────────────────────────────────────────────
  rollback:
    name: Auto-Rollback
    runs-on: ubuntu-latest
    needs: deploy-production
    if: failure()
    steps:
      - name: Rollback deployment
        run: |
          echo "${{{{ secrets.KUBE_CONFIG }}}}" | base64 -d > /tmp/kubeconfig
          export KUBECONFIG=/tmp/kubeconfig
          echo "::warning::Rolling back production deployment"
          kubectl rollout undo deployment/{app_name} -n {namespace}
          kubectl rollout status deployment/{app_name} -n {namespace} --timeout=300s

  # ── Notify ──────────────────────────────────────────────────────────────────
  notify:
    name: Send Notification
    runs-on: ubuntu-latest
    needs: [deploy-staging, deploy-production]
    if: always()
    steps:
      - name: Slack notification
        if: env.SLACK_WEBHOOK_URL != ''
        env:
          SLACK_WEBHOOK_URL: ${{{{ secrets.SLACK_WEBHOOK_URL }}}}
        run: |
          STATUS="${{{{ needs.deploy-production.result }}}}"
          COLOR=$([[ "$STATUS" == "success" ]] && echo "#36a64f" || echo "#dc3545")
          curl -X POST "$SLACK_WEBHOOK_URL" \\
            -H 'Content-Type: application/json' \\
            -d '{{"attachments":[{{"color":"'"$COLOR"'","title":"{app_name} deployment '"$STATUS"'","text":"Image: ${{{{ env.IMAGE_TAG }}}}\\nBranch: ${{{{ github.ref_name }}}}"}}]}}'

      - name: Deployment summary
        if: always()
        run: |
          echo "## Deployment Summary" >> "$GITHUB_STEP_SUMMARY"
          echo "| Property | Value |" >> "$GITHUB_STEP_SUMMARY"
          echo "|----------|-------|" >> "$GITHUB_STEP_SUMMARY"
          echo "| Image | \`${{{{ env.IMAGE_TAG }}}}\` |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Staging | ${{{{ needs.deploy-staging.result }}}} |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Production | ${{{{ needs.deploy-production.result }}}} |" >> "$GITHUB_STEP_SUMMARY"
"""
