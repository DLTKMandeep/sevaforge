#!/usr/bin/env bash
# =============================================================================
# push_github_secrets.sh — Read all OCI values and push to GitHub secrets
#
# Usage:
#   chmod +x scripts/push_github_secrets.sh
#   ./scripts/push_github_secrets.sh
#
# Requirements:
#   - oci CLI configured (~/.oci/config exists)
#   - gh CLI installed and logged in (gh auth login)
#   - Run from inside the sevaforge git repo
# =============================================================================

set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
die()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Sevaforge — Push all secrets to GitHub"
echo "══════════════════════════════════════════════════"
echo ""

# ── 0. Preflight checks ───────────────────────────────────────────────────────
command -v oci  &>/dev/null || die "oci CLI not found. Run: brew install oci-cli"
command -v gh   &>/dev/null || die "gh CLI not found. Run: brew install gh"
command -v git  &>/dev/null || die "git not found"

gh auth status &>/dev/null || die "Not logged in to gh. Run: gh auth login"

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) \
  || die "Not inside a GitHub repo. cd into the sevaforge project first."

echo "Repo  → ${REPO}"
echo ""

# ── 1. Read from OCI CLI config ───────────────────────────────────────────────
OCI_CONFIG="$HOME/.oci/config"
[ -f "$OCI_CONFIG" ] || die "~/.oci/config not found. Run: oci setup config"

read_cfg() { grep "^$1" "$OCI_CONFIG" | head -1 | cut -d= -f2 | tr -d ' '; }

TENANCY_OCID=$(read_cfg tenancy)
USER_OCID=$(read_cfg user)
FINGERPRINT=$(read_cfg fingerprint)
KEY_FILE=$(read_cfg key_file | sed "s|~|$HOME|g")
REGION=$(read_cfg region)
PRIVATE_KEY=$(cat "$KEY_FILE")

echo "▶ Read OCI config"
echo "  tenancy  → ${TENANCY_OCID:0:30}..."
echo "  user     → ${USER_OCID:0:30}..."
echo "  region   → ${REGION}"
echo ""

# ── 2. Pull live values from OCI ──────────────────────────────────────────────
echo "▶ Querying OCI for namespace, compartment, auth token..."

# Try three fallback methods to get the object storage namespace
OBJ_NAMESPACE=$(oci os ns get --compartment-id "$TENANCY_OCID" --query 'data' --raw-output 2>/dev/null)

if [ -z "$OBJ_NAMESPACE" ] || [ "$OBJ_NAMESPACE" = "null" ]; then
  # Fallback 1: read from tenancy record
  OBJ_NAMESPACE=$(oci iam tenancy get \
    --tenancy-id "$TENANCY_OCID" \
    --query 'data."object-storage-namespace"' --raw-output 2>/dev/null)
fi

if [ -z "$OBJ_NAMESPACE" ] || [ "$OBJ_NAMESPACE" = "null" ]; then
  # Fallback 2: prompt user — find it at Console → Profile → Tenancy
  warn "Could not auto-fetch namespace. Find it at: OCI Console → top-right avatar → Tenancy → Object Storage Namespace"
  read -r -p "  Paste Object Storage Namespace: " OBJ_NAMESPACE
fi

OCI_USERNAME=$(oci iam user get \
  --user-id "$USER_OCID" \
  --query 'data.name' --raw-output 2>/dev/null)

# Use tenancy root as compartment (Always Free simplest path)
COMPARTMENT_ID="$TENANCY_OCID"

# Map region → short key
declare -A RKEYS=(
  [us-ashburn-1]=iad   [us-phoenix-1]=phx   [us-chicago-1]=ord
  [eu-frankfurt-1]=fra [eu-amsterdam-1]=ams  [eu-zurich-1]=zrh
  [ap-sydney-1]=syd    [ap-tokyo-1]=nrt      [ap-singapore-1]=sin
  [ap-mumbai-1]=bom    [uk-london-1]=lhr     [ca-toronto-1]=yyz
  [sa-saopaulo-1]=gru  [me-dubai-1]=dxb
)
REGION_KEY="${RKEYS[$REGION]:-${REGION%%-*}}"

echo "  namespace  → ${OBJ_NAMESPACE}"
echo "  username   → ${OCI_USERNAME}"
echo "  region key → ${REGION_KEY}"
echo ""

# ── 3. Prompt for secrets that can't be auto-read ─────────────────────────────
echo "▶ A few values need to be entered manually:"
echo ""

# Auth token (OCI write-only — cannot be read back)
echo "  OCI Auth Token (from OCI Console → Profile → Auth Tokens)"
read -r -s -p "  Paste auth token: " OCI_AUTH_TOKEN
echo ""

# Anthropic API key
echo "  Anthropic API key (from console.anthropic.com)"
read -r -s -p "  Paste Anthropic key: " ANTHROPIC_KEY
echo ""

# GitHub PAT (needs secrets:write + actions:read)
echo "  GitHub PAT (Settings → Dev settings → Fine-grained token → Secrets: R/W)"
read -r -s -p "  Paste GitHub token: " GH_TOKEN_VALUE
echo ""
echo ""

# ── 4. Push all secrets ───────────────────────────────────────────────────────
echo "▶ Pushing secrets to ${REPO}..."
echo ""

set_secret() {
  local name="$1"
  local value="$2"
  if [ -z "$value" ]; then
    warn "Skipping ${name} — empty value"
    return
  fi
  gh secret set "$name" --repo "$REPO" --body "$value"
  ok "$name"
}

set_secret "OCI_TENANCY_OCID"  "$TENANCY_OCID"
set_secret "OCI_USER_OCID"     "$USER_OCID"
set_secret "OCI_FINGERPRINT"   "$FINGERPRINT"
set_secret "OCI_PRIVATE_KEY"   "$PRIVATE_KEY"
set_secret "OCI_REGION"        "$REGION"
set_secret "OCI_REGION_KEY"    "$REGION_KEY"
set_secret "OCI_NAMESPACE"     "$OBJ_NAMESPACE"
set_secret "OCI_USERNAME"      "$OCI_USERNAME"
set_secret "OCI_AUTH_TOKEN"    "$OCI_AUTH_TOKEN"
set_secret "OCI_COMPARTMENT_ID" "$COMPARTMENT_ID"
set_secret "ANTHROPIC_API_KEY" "$ANTHROPIC_KEY"
set_secret "GH_TOKEN"          "$GH_TOKEN_VALUE"

echo ""
echo "══════════════════════════════════════════════════"
ok "All secrets pushed to GitHub!"
echo ""
echo "  Next steps:"
echo "  1. Push your branch → git push origin gui-polish"
echo "  2. GitHub Actions → 'Terraform — Provision OCI Infrastructure'"
echo "     → Run workflow → action: plan  (review)"
echo "     → Run workflow → action: apply (create cluster)"
echo "  3. Then push to main — CI → CD runs automatically"
echo "══════════════════════════════════════════════════"
echo ""
