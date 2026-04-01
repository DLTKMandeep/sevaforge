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
from .iam_agent import IAMAgent


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


# =============================================================================
# COMPREHENSIVE DEPLOYMENT GUIDE SECTIONS
# (appended to the base DEPLOYMENT_GUIDE_TEMPLATE at render time)
# =============================================================================

_PRE_FLIGHT_AWS = """\
### Cloud accounts & access

- [ ] AWS Account with **IAM admin** access (to create service accounts and roles)
- [ ] AWS credentials working locally: `aws sts get-caller-identity`
- [ ] Note your **12-digit AWS Account ID** — needed for ECR URLs and IAM ARNs
- [ ] Decide: OIDC role federation (recommended, no long-lived keys) OR IAM user with access keys

"""

_PRE_FLIGHT_GCP = """\
### Cloud accounts & access

- [ ] GCP Project created with billing enabled
- [ ] **Owner** or **Project IAM Admin** role on the project
- [ ] gcloud authenticated: `gcloud auth login && gcloud auth application-default login`
- [ ] Note your **Project ID** (not the project name): `gcloud config get-value project`
- [ ] Decide: Workload Identity federation (recommended) OR service account JSON key

"""

_PRE_FLIGHT_AZURE = """\
### Cloud accounts & access

- [ ] Azure Subscription with **Owner** role
- [ ] Azure CLI authenticated: `az login`
- [ ] Note your **Subscription ID**: `az account show --query id -o tsv`
- [ ] Decide: Federated credentials (recommended) OR service principal client secret

"""

_IAM_QUICKSTART_AWS = """\

---

## 🏗️ AWS IAM Setup (complete BEFORE running Terraform)

Create these service accounts in order — each subsequent one depends on
infrastructure that the previous one provisions.

### 1 · terraform-deployer  (do this FIRST — Terraform runs as this identity)

**Option A — OIDC Role (no long-lived keys, recommended for production)**
```bash
# One-time per AWS account: register GitHub as a trusted OIDC provider
aws iam create-open-id-connect-provider \\
  --url https://token.actions.githubusercontent.com \\
  --client-id-list sts.amazonaws.com \\
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# Create the IAM role with the GitHub Actions trust policy
aws iam create-role \\
  --role-name terraform-deployer \\
  --assume-role-policy-document file://infrastructure/iam/aws/terraform-deployer-trust.json

# Attach the inline policy (EKS + ECR + ACM + SecretsManager + CloudWatch)
aws iam put-role-policy \\
  --role-name terraform-deployer \\
  --policy-name TerraformDeployerPolicy \\
  --policy-document file://infrastructure/iam/aws/terraform-deployer-inline.json

# Add broad AWS managed policies needed for cluster + networking provisioning
for policy in AmazonEKSClusterPolicy AmazonVPCFullAccess AmazonEC2FullAccess \\
              ElasticLoadBalancingFullAccess AmazonRoute53FullAccess \\
              AmazonS3FullAccess IAMFullAccess; do
  aws iam attach-role-policy --role-name terraform-deployer \\
    --policy-arn arn:aws:iam::aws:policy/$policy
done

# Get the Role ARN — store as GitHub secret AWS_ROLE_ARN
aws iam get-role --role-name terraform-deployer --query 'Role.Arn' --output text
```

**Option B — IAM User (simpler setup, but uses long-lived access keys)**
```bash
aws iam create-user --user-name terraform-deployer
aws iam put-user-policy \\
  --user-name terraform-deployer \\
  --policy-name TerraformDeployerPolicy \\
  --policy-document file://infrastructure/iam/aws/terraform-deployer-inline.json

# Create keys — output contains AccessKeyId and SecretAccessKey
aws iam create-access-key --user-name terraform-deployer
# Store AccessKeyId → AWS_ACCESS_KEY_ID, SecretAccessKey → AWS_SECRET_ACCESS_KEY
```

### 2 · cicd-image-pusher  (CI builds and pushes Docker images as this identity)
```bash
# OIDC role (recommended)
aws iam create-role \\
  --role-name cicd-image-pusher \\
  --assume-role-policy-document file://infrastructure/iam/aws/cicd-image-pusher-trust.json

aws iam put-role-policy \\
  --role-name cicd-image-pusher \\
  --policy-name ECRPushPolicy \\
  --policy-document file://infrastructure/iam/aws/cicd-image-pusher-inline.json
```

### 3 · eks-node-role  (automatically created by Terraform — review before apply)
```bash
# Review the managed policy list in:
cat infrastructure/iam/aws/eks-node-role-managed.json

# After terraform apply, verify:
aws iam get-role --role-name <app-name>-eks-node-role
```

### 4 · external-secrets-operator  (after EKS cluster exists — uses IRSA)
This role is created automatically by your Terraform EKS module using IRSA
(IAM Roles for Service Accounts). It allows the ESO pod to read from
AWS Secrets Manager without any secrets stored in the cluster.
```bash
# After terraform apply, verify IRSA annotation:
kubectl get sa external-secrets -n external-secrets-system -o yaml | grep eks.amazonaws.com
```

### 5 · app-workload  (after EKS cluster + namespace exists — uses IRSA)
Fine-grained S3/SQS/DynamoDB access for your application pods.
Terraform creates this role. Scope the ARNs to your specific resources.
```bash
# After terraform apply + namespace created:
kubectl get sa <app-name> -n <app-name>-production -o yaml | grep eks.amazonaws.com
```

### Verify all IAM setup
```bash
bash scripts/verify-iam.sh
```

> Full policy documents with exact JSON: `docs/IAM_POLICIES.md`
> Policy files: `infrastructure/iam/aws/`

"""

_IAM_QUICKSTART_GCP = """\

---

## 🏗️ GCP IAM Setup (complete BEFORE running Terraform)

### 1 · terraform-deployer  (FIRST — Terraform runs as this service account)

**Option A — Workload Identity (no JSON key, recommended)**
```bash
# Create the service account
gcloud iam service-accounts create terraform-deployer \\
  --display-name "ForgeFlow Terraform Deployer" \\
  --project $GCP_PROJECT_ID

# Grant all required roles (see infrastructure/iam/gcp/terraform-deployer.tf)
for role in roles/container.admin roles/compute.admin roles/iam.serviceAccountAdmin \\
            roles/iam.workloadIdentityUser roles/storage.admin \\
            roles/artifactregistry.admin roles/secretmanager.admin \\
            roles/dns.admin roles/certificatemanager.admin \\
            roles/resourcemanager.projectIamAdmin roles/monitoring.admin; do
  gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \\
    --member serviceAccount:terraform-deployer@$GCP_PROJECT_ID.iam.gserviceaccount.com \\
    --role $role
done

# Bind to the GitHub Actions workload identity pool
gcloud iam service-accounts add-iam-policy-binding \\
  terraform-deployer@$GCP_PROJECT_ID.iam.gserviceaccount.com \\
  --role roles/iam.workloadIdentityUser \\
  --member "principalSet://iam.googleapis.com/projects/$GCP_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_ORG/YOUR_REPO"
```

**Option B — Service Account Key (simpler, use for dev/POC only)**
```bash
gcloud iam service-accounts keys create /tmp/terraform-sa.json \\
  --iam-account terraform-deployer@$GCP_PROJECT_ID.iam.gserviceaccount.com

# Base64-encode and store as GCP_SA_KEY
base64 -i /tmp/terraform-sa.json | tr -d '\\n' | gh secret set GCP_SA_KEY --repo YOUR_ORG/REPO
rm /tmp/terraform-sa.json  # clean up
```

### 2 · cicd-image-pusher
```bash
gcloud iam service-accounts create cicd-image-pusher \\
  --display-name "ForgeFlow CI/CD Image Pusher" --project $GCP_PROJECT_ID

gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \\
  --member serviceAccount:cicd-image-pusher@$GCP_PROJECT_ID.iam.gserviceaccount.com \\
  --role roles/artifactregistry.writer
```

### 3 · gke-node  (automatically created by Terraform)
```bash
cat infrastructure/iam/gcp/gke-node.tf
```

### 4 · external-secrets  (created by Terraform using Workload Identity)
```bash
cat infrastructure/iam/gcp/external-secrets.tf
```

### Verify
```bash
bash scripts/verify-iam.sh
```

> Full policy documents and Terraform blocks: `docs/IAM_POLICIES.md` and `infrastructure/iam/gcp/`

"""

_IAM_QUICKSTART_AZURE = """\

---

## 🏗️ Azure IAM Setup (complete BEFORE running Terraform)

### 1 · terraform-deployer Service Principal  (FIRST)
```bash
# Create service principal — outputs JSON with clientId, clientSecret, tenantId, subscriptionId
az ad sp create-for-rbac \\
  --name "forgeflow-terraform-deployer" \\
  --role "Contributor" \\
  --scopes /subscriptions/$AZURE_SUBSCRIPTION_ID \\
  --sdk-auth > /tmp/azure-sp.json

# Store full JSON as AZURE_CREDENTIALS GitHub secret
cat /tmp/azure-sp.json | gh secret set AZURE_CREDENTIALS --repo YOUR_ORG/REPO

# Add User Access Administrator (needed for AKS RBAC and managed identity assignments)
APPID=$(cat /tmp/azure-sp.json | python3 -c "import sys,json; print(json.load(sys.stdin)['clientId'])")
az role assignment create \\
  --assignee $APPID \\
  --role "User Access Administrator" \\
  --scope /subscriptions/$AZURE_SUBSCRIPTION_ID

# Add Key Vault Administrator (needed for Key Vault secret management via Terraform)
az role assignment create \\
  --assignee $APPID \\
  --role "Key Vault Administrator" \\
  --scope /subscriptions/$AZURE_SUBSCRIPTION_ID

rm /tmp/azure-sp.json  # clean up
```

### 2 · cicd-image-pusher Service Principal
```bash
az ad sp create-for-rbac --name "forgeflow-cicd-image-pusher"

# Grant AcrPush on the ACR resource (get ACR resource ID after terraform apply)
ACR_ID=$(az acr show --name <your-acr-name> --query id -o tsv)
az role assignment create --assignee <cicd-pusher-appId> \\
  --role "AcrPush" --scope $ACR_ID
```

### 3 · AKS node managed identity  (automatically created by Terraform)
```bash
cat infrastructure/iam/azure/aks-managed-identity.json
```

### 4 · external-secrets User-Assigned Managed Identity  (created by Terraform)
```bash
cat infrastructure/iam/azure/external-secrets.json
```

### Verify
```bash
bash scripts/verify-iam.sh
```

> Full ARM role definitions: `docs/IAM_POLICIES.md` and `infrastructure/iam/azure/`

"""

_ARGOCD_GUIDE = """\

---

## 🔄 ArgoCD Setup Guide

ArgoCD was detected as your GitOps deployment engine. Complete this before the
first `git push origin main`, otherwise the CD workflow cannot sync your application.

### 1 · Install ArgoCD on your Kubernetes cluster
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f \\
  https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Wait for all pods to be ready (takes ~2 minutes)
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s
kubectl get pods -n argocd
```

### 2 · Get initial admin password
```bash
argocd admin initial-password -n argocd | head -1
# Change it immediately after first login
```

### 3 · Access the ArgoCD UI (choose one option)
```bash
# Option A — Port-forward (local access, safest)
kubectl port-forward svc/argocd-server -n argocd 8080:443 &
# Open https://localhost:8080  (accept self-signed cert on first visit)

# Option B — LoadBalancer external IP (dev clusters only)
kubectl patch svc argocd-server -n argocd -p '{"spec":{"type":"LoadBalancer"}}'
kubectl get svc argocd-server -n argocd -w  # wait for EXTERNAL-IP

# Option C — Ingress (recommended for production — apply your ingress manifest)
kubectl apply -f infrastructure/k8s/argocd/ingress.yaml
```

### 4 · Login via CLI and change password
```bash
argocd login localhost:8080 --username admin --password <initial-password> --insecure
argocd account update-password
```

### 5 · Register your GitHub repository with ArgoCD
```bash
argocd repo add https://github.com/YOUR_ORG/REPO \\
  --username git \\
  --password $GH_PAT  # your GitHub PAT with repo scope
```

### 6 · Create ArgoCD API token → store as ARGOCD_AUTH_TOKEN GitHub secret
```bash
# Create a dedicated ArgoCD account for the CD pipeline (least-privilege)
argocd account list  # should show 'admin'

# Generate token for the pipeline account
TOKEN=$(argocd account generate-token --account admin)
echo $TOKEN | gh secret set ARGOCD_AUTH_TOKEN --repo YOUR_ORG/REPO
```

### 7 · Store ArgoCD server URL → store as ARGOCD_SERVER GitHub secret
```bash
# Use your LoadBalancer IP or ingress hostname (without https://)
ARGOCD_HOST=$(kubectl get svc argocd-server -n argocd \\
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
# Or for ingress: ARGOCD_HOST="argocd.your-domain.com"

echo "$ARGOCD_HOST" | gh secret set ARGOCD_SERVER --repo YOUR_ORG/REPO
```

### 8 · Trigger the bootstrap workflow (creates Applications for staging + prod)
```bash
gh workflow run bootstrap.yml --repo YOUR_ORG/REPO
gh run watch --repo YOUR_ORG/REPO  # watch it complete
```

After bootstrap succeeds, `ARGOCD_SERVER` and `ARGOCD_AUTH_TOKEN` are confirmed
and your CD workflow can sync applications automatically.

"""

_ESO_GUIDE_TEMPLATE = """\

---

## 🔐 External Secrets Operator (ESO) Setup

ESO was detected in your project. It syncs secrets from {secret_manager} →
Kubernetes Secrets automatically so your pods never need cloud credentials.

### 1 · Install ESO via Helm
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm install external-secrets external-secrets/external-secrets \\
  --namespace external-secrets-system \\
  --create-namespace \\
  --set installCRDs=true \\
  --wait
```

### 2 · Verify installation
```bash
kubectl get pods -n external-secrets-system
kubectl get crd | grep external-secrets.io
```

### 3 · Apply the SecretStore (after Terraform + IRSA/Workload Identity are ready)
```bash
# The SecretStore is generated by Terraform — apply after terraform apply
kubectl apply -f infrastructure/k8s/secrets/secret-store.yaml
kubectl get secretstore -A
```

### 4 · Apply ExternalSecret manifests
```bash
kubectl apply -f infrastructure/k8s/secrets/
kubectl get externalsecret -A
```

### 5 · Verify secrets are syncing
```bash
# Status should be "SecretSynced"
kubectl get externalsecret -A -o wide

# Check a specific secret
kubectl describe externalsecret <name> -n <namespace>

# Verify the Kubernetes Secret was created
kubectl get secret -n {app_name}-production
```

### 6 · Force a manual sync if needed
```bash
kubectl annotate externalsecret <name> \\
  force-sync=$(date +%s) --overwrite -n <namespace>
```

"""

_CERT_MANAGER_GUIDE = """\

---

## 🔒 cert-manager Setup (automated TLS certificates)

cert-manager was detected. It automatically provisions and renews TLS certificates
from Let's Encrypt, eliminating manual certificate management.

### 1 · Install cert-manager
```bash
kubectl apply -f \\
  https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

kubectl wait --for=condition=available deployment/cert-manager \\
  -n cert-manager --timeout=120s
kubectl get pods -n cert-manager
```

### 2 · Apply the ClusterIssuer (Let's Encrypt)
```bash
# Edit infrastructure/k8s/cert-manager/cluster-issuer.yaml to add your email
kubectl apply -f infrastructure/k8s/cert-manager/cluster-issuer.yaml
kubectl get clusterissuer
```

### 3 · Verify certificate issuance (after ingress is applied)
```bash
kubectl get certificate -A
kubectl describe certificate <app-name>-tls -n <namespace>
# Status Ready: True means TLS is live
```

"""

_INGRESS_NGINX_GUIDE = """\

---

## 🌐 ingress-nginx Setup (HTTP/S load balancing)

### 1 · Install ingress-nginx
```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \\
  --namespace ingress-nginx \\
  --create-namespace \\
  --set controller.service.type=LoadBalancer \\
  --wait
```

### 2 · Get external IP (takes ~2 minutes for cloud load balancer to provision)
```bash
kubectl get svc ingress-nginx-controller -n ingress-nginx -w
# Note the EXTERNAL-IP column value
```

### 3 · Configure DNS
Point your domain records to the external IP:
```
A record:  your-app.your-domain.com          → <EXTERNAL-IP>
A record:  your-app-staging.your-domain.com  → <EXTERNAL-IP>
```

### 4 · Apply ingress manifests
```bash
kubectl apply -f infrastructure/k8s/base/ingress.yaml
kubectl get ingress -A
```

"""

_PROMETHEUS_GUIDE = """\

---

## 📊 Prometheus + Grafana Monitoring Setup

Prometheus monitoring was detected. This installs a full observability stack.

### 1 · Install kube-prometheus-stack
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \\
  --namespace monitoring \\
  --create-namespace \\
  --set grafana.adminPassword=<choose-a-password> \\
  --wait
```

### 2 · Access Grafana dashboard
```bash
kubectl port-forward svc/kube-prometheus-stack-grafana -n monitoring 3000:80 &
# Open http://localhost:3000  — user: admin, password: <your-password>
```

### 3 · Import recommended dashboards
- Kubernetes Cluster Overview: ID `6417`
- Node Exporter Full: ID `1860`
- ArgoCD dashboard: ID `14584` (if using ArgoCD)

### 4 · Verify your app metrics are scraped
```bash
kubectl get servicemonitor -A
kubectl get prometheusrule -A
```

"""

_K8S_NAMESPACES_GUIDE = """\

---

## ☸️  Kubernetes Cluster Prep (run after terraform apply)

### 1 · Create application namespaces
```bash
APP_NAME="<your-app-name>"
kubectl create namespace ${APP_NAME}-staging   --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace ${APP_NAME}-production --dry-run=client -o yaml | kubectl apply -f -
kubectl get namespaces | grep $APP_NAME
```

### 2 · Apply RBAC for ArgoCD (if using ArgoCD GitOps)
```bash
kubectl apply -f infrastructure/k8s/rbac/
kubectl get rolebinding -A | grep argocd
```

### 3 · Label namespaces for network policies
```bash
kubectl label namespace ${APP_NAME}-staging    env=staging
kubectl label namespace ${APP_NAME}-production env=production
kubectl label namespace ${APP_NAME}-staging    app=${APP_NAME}
kubectl label namespace ${APP_NAME}-production app=${APP_NAME}
```

"""


# =============================================================================
# SecretsAgent class
# =============================================================================

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
        tools        = self._detect_tools(repo_path)

        self.log(f"Detected cloud provider: {cloud}")
        self.log(f"App name: {app_name}")
        detected_tools = [k for k, v in tools.items() if v]
        self.log(f"Tools detected: {', '.join(detected_tools) or 'none'}")

        actions = []

        # ── 1. Generate comprehensive DEPLOYMENT_GUIDE.md ─────────────────────
        guide = self._render_guide(
            app_name, cloud, has_snyk, registry, domain_hint, github_user, tools
        )
        docs_path = repo_path / "docs"
        docs_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(docs_path / "DEPLOYMENT_GUIDE.md", guide, overwrite))

        # ── 2. Generate bootstrap-secrets.sh ──────────────────────────────────
        script = self._render_bootstrap_script(app_name, cloud, github_user)
        scripts_path = repo_path / "scripts"
        scripts_path.mkdir(exist_ok=True)
        script_file = scripts_path / "bootstrap-secrets.sh"
        actions.append(self._safe_write(script_file, script, overwrite))
        if script_file.exists():
            script_file.chmod(0o755)

        # ── 3. Generate IAM policies via IAMAgent ──────────────────────────────
        iam_actions: List[Dict] = []
        iam_findings: List[str] = []
        try:
            iam_agent = IAMAgent()
            iam_result = iam_agent.execute({"path": str(repo_path), "cloud": cloud})
            iam_actions = iam_result.get("actions", [])
            iam_findings = iam_result.get("findings", [])
            actions.extend(iam_actions)
        except Exception as iam_err:
            self.log(f"IAMAgent skipped: {iam_err}")
            iam_findings = [f"IAM policy generation skipped: {iam_err}"]

        # ── 4. Collect secrets manifest for callers ────────────────────────────
        secrets_manifest = self._build_manifest(cloud, has_snyk)

        req_count = len([s for s in secrets_manifest if not s['optional']])
        opt_count = len([s for s in secrets_manifest if s['optional']])

        findings = [
            f"Cloud provider detected: {cloud}",
            f"Container registry: {registry}",
            f"Tools detected: {', '.join(detected_tools) or 'none'}",
            f"Required secrets: {req_count}",
            f"Optional secrets: {opt_count}",
            "Deployment guide:    docs/DEPLOYMENT_GUIDE.md",
            "IAM policies guide:  docs/IAM_POLICIES.md",
            "Bootstrap script:    scripts/bootstrap-secrets.sh",
            "IAM verify script:   scripts/verify-iam.sh",
            "IAM policy files:    infrastructure/iam/",
        ] + iam_findings[:5]

        # Normalise action dicts — IAMAgent uses {"action","file"}, SecretsAgent uses {"status","path"}
        def _file_path_from_action(a: Dict) -> Optional[str]:
            return a.get("path") or a.get("file")

        def _is_created(a: Dict) -> bool:
            return a.get("status") == "created" or a.get("action") == "created"

        return self.create_result(
            status="success",
            summary=(
                f"Generated comprehensive deployment guide, IAM policies, and secrets bootstrap "
                f"for {app_name} ({cloud} / {registry}). "
                f"Read docs/DEPLOYMENT_GUIDE.md for the full pre-flight → production walkthrough."
            ),
            data={
                "app_name":         app_name,
                "cloud_provider":   cloud,
                "registry":         registry,
                "tools_detected":   detected_tools,
                "secrets_manifest": secrets_manifest,
                "files_generated":  [
                    _file_path_from_action(a) for a in actions
                    if _is_created(a) and _file_path_from_action(a)
                ],
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

    def _detect_tools(self, repo_path: Path) -> Dict[str, bool]:
        """Scan generated files to detect which tools/operators the project uses."""
        tools: Dict[str, bool] = {
            'argocd':       False,
            'helm':         False,
            'eso':          False,   # External Secrets Operator
            'cert_manager': False,
            'kustomize':    False,
            'ingress_nginx':False,
            'prometheus':   False,
            'flux':         False,
        }
        # Scan YAML/YML files (cap at 300 to avoid huge repos)
        yaml_files = list(repo_path.rglob("*.yaml"))[:200] + list(repo_path.rglob("*.yml"))[:100]
        for f in yaml_files:
            try:
                content = f.read_text(errors="ignore")
                if "argoproj.io" in content or "argocd-server" in content:
                    tools["argocd"] = True
                if "external-secrets.io" in content or "kind: ExternalSecret" in content or "kind: SecretStore" in content:
                    tools["eso"] = True
                if "cert-manager.io" in content or "kind: ClusterIssuer" in content or "kind: Certificate" in content:
                    tools["cert_manager"] = True
                if "kustomize.config.k8s.io" in content:
                    tools["kustomize"] = True
                if "nginx.ingress.kubernetes.io" in content or "ingress-nginx" in content:
                    tools["ingress_nginx"] = True
                if "monitoring.coreos.com" in content or "kind: ServiceMonitor" in content or "kind: PrometheusRule" in content:
                    tools["prometheus"] = True
                if "fluxcd.io" in content or "source.toolkit.fluxcd.io" in content:
                    tools["flux"] = True
            except Exception:
                pass
        # Helm: check for Chart.yaml
        if list(repo_path.rglob("Chart.yaml")):
            tools["helm"] = True
        return tools

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
        registry: str, domain_hint: str, github_user: str,
        tools: Optional[Dict[str, bool]] = None,
    ) -> str:
        if tools is None:
            tools = {}

        cloud_secrets = {
            "AWS": AWS_SECRETS, "GCP": GCP_SECRETS, "Azure": AZURE_SECRETS,
        }.get(cloud, AWS_SECRETS)

        req_rows = []
        for name, desc, how, used_for, optional in cloud_secrets + COMMON_SECRETS:
            if name in ("ARGOCD_SERVER", "ARGOCD_AUTH_TOKEN"):
                continue  # shown in auto-populated table
            req_rows.append(f"| `{name}` | {desc} | {how} |")

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

        # ── Base template (steps 1–5 + workflow triggers + troubleshooting) ────
        base = DEPLOYMENT_GUIDE_TEMPLATE.format(
            app_name=app_name,
            snyk_line=snyk_line,
            registry=registry,
            required_secrets_table=req_table,
            optional_secrets_table=opt_table,
            domain_hint=domain_hint,
        )

        # ── Pre-flight section (inserted right after the title line) ──────────
        title_end = base.find("\nGenerated by ForgeFlow")
        after_title = base.find("\n---\n\n## Overview", title_end)
        pre_flight_cloud = {
            "AWS": _PRE_FLIGHT_AWS,
            "GCP": _PRE_FLIGHT_GCP,
            "Azure": _PRE_FLIGHT_AZURE,
        }.get(cloud, _PRE_FLIGHT_AWS)

        tools_list = [
            "- [ ] `terraform` — infrastructure provisioning: `brew install terraform`",
            "- [ ] `kubectl`   — Kubernetes management: `brew install kubectl`",
            "- [ ] `helm`      — Kubernetes package manager: `brew install helm`",
            "- [ ] `gh`        — GitHub CLI (secrets + environments): `brew install gh && gh auth login`",
        ]
        cloud_cli = {"AWS": "`aws` CLI: `brew install awscli`",
                     "GCP": "`gcloud` CLI: `brew install google-cloud-sdk`",
                     "Azure": "`az` CLI: `brew install azure-cli`"}.get(cloud, "`aws` CLI")
        tools_list.append(f"- [ ] {cloud_cli}")
        if tools.get("argocd"):
            tools_list.append("- [ ] `argocd` CLI — GitOps management: `brew install argocd`")

        detected_tools_str = ", ".join(
            k.replace("_", "-") for k, v in tools.items() if v
        ) or "none detected"

        pre_flight = (
            "\n---\n\n"
            "## ✅ Pre-flight Checklist\n\n"
            f"> **Tools detected in this project:** {detected_tools_str}\n\n"
            "Complete the items below before running any deployment steps.\n\n"
            "### Tools to install\n\n"
            + "\n".join(tools_list) + "\n\n"
            + pre_flight_cloud
            + "### GitHub access\n\n"
            "- [ ] GitHub account with admin rights to create and configure repositories\n"
            "- [ ] Personal Access Token with `repo + write:packages + admin:repo_hook` scopes\n"
            "- [ ] `gh auth login` completed\n\n"
            "### IAM service accounts\n\n"
            "Read **`docs/IAM_POLICIES.md`** for the full matrix. "
            "At minimum, create **`terraform-deployer`** before running `terraform apply`.\n"
            "See the IAM Setup section at the bottom of this guide for step-by-step commands.\n"
        )

        # Insert pre_flight before the first "---" separator
        if after_title != -1:
            base = base[:after_title] + pre_flight + base[after_title:]
        else:
            base = base + pre_flight

        # ── IAM quickstart (appended at the end) ─────────────────────────────
        iam_section = {
            "AWS":   _IAM_QUICKSTART_AWS,
            "GCP":   _IAM_QUICKSTART_GCP,
            "Azure": _IAM_QUICKSTART_AZURE,
        }.get(cloud, "")

        # ── Kubernetes namespace prep (always appended) ───────────────────────
        k8s_section = _K8S_NAMESPACES_GUIDE

        # ── Tool-specific sections ────────────────────────────────────────────
        tool_sections = ""
        if tools.get("argocd"):
            tool_sections += _ARGOCD_GUIDE
        if tools.get("eso"):
            sm_name = {"AWS": "AWS Secrets Manager",
                       "GCP": "GCP Secret Manager",
                       "Azure": "Azure Key Vault"}.get(cloud, "Secret Manager")
            tool_sections += (
                _ESO_GUIDE_TEMPLATE
                .replace("{secret_manager}", sm_name)
                .replace("{app_name}", app_name)
            )
        if tools.get("cert_manager"):
            tool_sections += _CERT_MANAGER_GUIDE
        if tools.get("ingress_nginx"):
            tool_sections += _INGRESS_NGINX_GUIDE
        if tools.get("prometheus"):
            tool_sections += _PROMETHEUS_GUIDE

        return base + iam_section + k8s_section + tool_sections + (
            "\n\n---\n\n*Generated by ForgeFlow — AIDDaaS · Sevaforge*\n"
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
