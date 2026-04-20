#!/usr/bin/env bash
# =============================================================================
# Sevaforge Secret Bootstrap Script — sevaforge_unified
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

REPO="your-github-username/sevaforge_unified"
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0;0m'

print_header() {
  echo ""
  echo "${BLU}════════════════════════════════════════${NC}"
  echo "${BLU}  $1${NC}"
  echo "${BLU}════════════════════════════════════════${NC}"
}

prompt_secret() {
  local name="$1"
  local description="$2"
  local how_to_get="$3"
  local optional="${4:-false}"

  echo ""
  if [[ "$optional" == "true" ]]; then
    echo "${YLW}[OPTIONAL] $name${NC}"
  else
    echo "${GRN}[REQUIRED] $name${NC}"
  fi
  echo "  $description"
  echo "  How to get it: $how_to_get"
  echo ""

  # Check if already set
  if gh secret list --repo "$REPO" 2>/dev/null | grep -q "^$name[[:space:]]"; then
    echo "  ${GRN}✓ Already set — skipping (use --force to overwrite)${NC}"
    return 0
  fi

  if [[ "$optional" == "true" ]]; then
    read -rp "  Enter value (or press Enter to skip): " value
    if [[ -z "$value" ]]; then
      echo "  ${YLW}⊘ Skipped${NC}"
      return 0
    fi
  else
    while true; do
      read -rsp "  Enter value: " value
      echo ""
      if [[ -n "$value" ]]; then break; fi
      echo "  ${RED}✗ Value cannot be empty for required secret${NC}"
    done
  fi

  echo -n "$value" | gh secret set "$name" --repo "$REPO"
  echo "  ${GRN}✓ Set successfully${NC}"
}

validate_prerequisites() {
  print_header "Checking prerequisites"

  if ! command -v gh &>/dev/null; then
    echo "${RED}✗ gh CLI not found — install from https://cli.github.com/${NC}"
    exit 1
  fi
  echo "${GRN}✓ gh CLI found${NC}"

  if ! gh auth status &>/dev/null; then
    echo "${RED}✗ gh CLI not authenticated — run: gh auth login${NC}"
    exit 1
  fi
  echo "${GRN}✓ gh CLI authenticated${NC}"

  # Confirm repo access
  if ! gh repo view "$REPO" &>/dev/null; then
    echo "${RED}✗ Cannot access repo $REPO — check your PAT scopes${NC}"
    exit 1
  fi
  echo "${GRN}✓ Repository access confirmed: $REPO${NC}"
}

set_cloud_secrets() {
  print_header "AWS Secrets"
  prompt_secret "AWS_ACCESS_KEY_ID" \
    "AWS IAM access key for pipeline operations" \
    "IAM → Users → Security credentials → Create access key" \
    "false"

  prompt_secret "AWS_SECRET_ACCESS_KEY" \
    "AWS IAM secret key (pair with AWS_ACCESS_KEY_ID)" \
    "Shown once at IAM access key creation — store immediately" \
    "false"

  prompt_secret "AWS_REGION" \
    "AWS region to deploy into (e.g. us-east-1)" \
    "Choose your target region — must match Terraform variables" \
    "false"

  prompt_secret "AWS_ACCOUNT_ID" \
    "12-digit AWS account ID" \
    "AWS Console top-right → Account ID, or: aws sts get-caller-identity --query Account" \
    "false"
}

set_common_secrets() {
  print_header "Common Secrets"
  prompt_secret "GH_PAT" \
    "GitHub Personal Access Token with repo + write:packages + secrets scopes" \
    "GitHub → Settings → Developer settings → Personal access tokens → Fine-grained → Select repo, Read/Write on secrets and packages" \
    "false"
}

set_optional_secrets() {
  print_header "Optional Secrets (enhance the pipeline)"
  prompt_secret "SNYK_TOKEN" \
    "Snyk API token for enhanced vulnerability scanning" \
    "https://app.snyk.io → Account Settings → API Token" \
    "true"

  prompt_secret "SLACK_WEBHOOK_URL" \
    "Slack Incoming Webhook URL for deployment notifications" \
    "Slack → Apps → Incoming Webhooks → Add to Workspace → Copy URL" \
    "true"

  prompt_secret "SONAR_TOKEN" \
    "SonarCloud token for code quality analysis" \
    "https://sonarcloud.io → My Account → Security → Generate Token" \
    "true"

  prompt_secret "DATADOG_API_KEY" \
    "Datadog API key for deployment tracking metrics" \
    "Datadog → Integrations → API Keys → New Key" \
    "true"
}

verify_secrets() {
  print_header "Verification — secrets currently set"
  echo ""
  gh secret list --repo "$REPO" | while read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    echo "  ${GRN}✓${NC} $name"
  done
  echo ""
}

print_next_steps() {
  print_header "Next Steps"
  echo ""
  echo "  1. Run the Infrastructure workflow (first time only):"
  echo "     ${BLU}gh workflow run infra.yml --repo $REPO${NC}"
  echo ""
  echo "  2. After infra completes, run ArgoCD Bootstrap:"
  echo "     ${BLU}gh workflow run bootstrap.yml --repo $REPO${NC}"
  echo ""
  echo "  3. Push your first commit to main:"
  echo "     ${BLU}git push origin main${NC}"
  echo ""
  echo "  4. Watch the three-workflow chain in GitHub Actions:"
  echo "     ${BLU}gh run watch --repo $REPO${NC}"
  echo ""
  echo "  Full guide: docs/DEPLOYMENT_GUIDE.md"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────
validate_prerequisites
set_cloud_secrets
set_common_secrets
set_optional_secrets
verify_secrets
print_next_steps

echo "${GRN}Bootstrap complete!${NC}"
