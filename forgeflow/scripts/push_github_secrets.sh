#!/usr/bin/env bash
# =============================================================================
# push_github_secrets.sh — Push all Sevaforge secrets to GitHub
# Reads directly from ~/.oci/config — no OCI API calls needed.
# =============================================================================

# No set -e so we never exit silently
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $1${NC}"; }
die()  { echo -e "${RED}❌  $1${NC}"; exit 1; }

echo ""
echo "══════════════════════════════════════════════════"
echo "  Sevaforge — Push secrets to GitHub"
echo "══════════════════════════════════════════════════"
echo ""

# ── Preflight ─────────────────────────────────────────────────────────────────
command -v gh  &>/dev/null || die "gh not found — run: brew install gh"
command -v git &>/dev/null || die "git not found"
gh auth status &>/dev/null || die "Not logged in — run: gh auth login"

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null)
[ -n "$REPO" ] || die "Not inside a GitHub repo. cd into the sevaforge project."
echo "Repo → ${REPO}"
echo ""

# ── Read from ~/.oci/config (no API calls) ────────────────────────────────────
OCI_CONFIG="$HOME/.oci/config"
[ -f "$OCI_CONFIG" ] || die "~/.oci/config not found — run: oci setup config"

cfg() { grep "^$1" "$OCI_CONFIG" | head -1 | cut -d= -f2 | tr -d ' \t'; }

TENANCY_OCID=$(cfg tenancy)
USER_OCID=$(cfg user)
FINGERPRINT=$(cfg fingerprint)
REGION=$(cfg region)
KEY_FILE=$(cfg key_file | sed "s|~|$HOME|")
PRIVATE_KEY=$(cat "$KEY_FILE" 2>/dev/null) || die "Cannot read key file: $KEY_FILE"

# Region → short key map
case "$REGION" in
  us-ashburn-1)   REGION_KEY=iad ;;
  us-phoenix-1)   REGION_KEY=phx ;;
  us-chicago-1)   REGION_KEY=ord ;;
  eu-frankfurt-1) REGION_KEY=fra ;;
  eu-amsterdam-1) REGION_KEY=ams ;;
  ap-sydney-1)    REGION_KEY=syd ;;
  ap-tokyo-1)     REGION_KEY=nrt ;;
  ap-singapore-1) REGION_KEY=sin ;;
  ap-mumbai-1)    REGION_KEY=bom ;;
  uk-london-1)    REGION_KEY=lhr ;;
  ca-toronto-1)   REGION_KEY=yyz ;;
  *)              REGION_KEY="${REGION%%-*}" ;;
esac

echo "▶ Values read from ~/.oci/config"
echo "  tenancy     → ${TENANCY_OCID:0:32}..."
echo "  user        → ${USER_OCID:0:32}..."
echo "  fingerprint → ${FINGERPRINT}"
echo "  region      → ${REGION} (key: ${REGION_KEY})"
echo "  key file    → ${KEY_FILE}"
echo ""

# ── Prompt for values that must be entered manually ───────────────────────────
echo "▶ Enter the following manually (input is hidden):"
echo ""

echo "  [1/5] OCI Object Storage Namespace"
echo "        → OCI Console ▸ top-right avatar ▸ Tenancy ▸ Object Storage Namespace"
read -r -p "        Paste value: " OBJ_NAMESPACE
echo ""

echo "  [2/5] OCI Auth Token"
echo "        → OCI Console ▸ Profile ▸ Auth Tokens ▸ Generate Token"
read -r -s -p "        Paste value: " OCI_AUTH_TOKEN
echo ""
echo ""

echo "  [3/5] OCI Username (your login email or IAM username)"
echo "        → OCI Console ▸ top-right avatar ▸ My Profile ▸ Username"
read -r -p "        Paste value: " OCI_USERNAME
echo ""

echo "  [4/5] Anthropic API Key"
echo "        → console.anthropic.com ▸ API Keys"
read -r -s -p "        Paste value: " ANTHROPIC_KEY
echo ""
echo ""

echo "  [5/5] GitHub Personal Access Token"
echo "        → github.com ▸ Settings ▸ Developer settings ▸ Fine-grained tokens"
echo "        Permissions needed: Secrets = Read & Write, Actions = Read"
read -r -s -p "        Paste value: " GH_TOKEN_VALUE
echo ""
echo ""

# ── Push secrets ──────────────────────────────────────────────────────────────
echo "▶ Pushing to ${REPO}..."
echo ""

push() {
  local NAME="$1" VAL="$2"
  if [ -z "$VAL" ]; then
    warn "Skipping ${NAME} — empty value"
    return
  fi
  if gh secret set "$NAME" --repo "$REPO" --body "$VAL" 2>/dev/null; then
    ok "$NAME"
  else
    warn "FAILED: ${NAME} — check gh auth scopes"
  fi
}

push "OCI_TENANCY_OCID"   "$TENANCY_OCID"
push "OCI_USER_OCID"      "$USER_OCID"
push "OCI_FINGERPRINT"    "$FINGERPRINT"
push "OCI_PRIVATE_KEY"    "$PRIVATE_KEY"
push "OCI_REGION"         "$REGION"
push "OCI_REGION_KEY"     "$REGION_KEY"
push "OCI_NAMESPACE"      "$OBJ_NAMESPACE"
push "OCI_USERNAME"       "$OCI_USERNAME"
push "OCI_AUTH_TOKEN"     "$OCI_AUTH_TOKEN"
push "OCI_COMPARTMENT_ID" "$TENANCY_OCID"
push "ANTHROPIC_API_KEY"  "$ANTHROPIC_KEY"
push "GH_TOKEN"           "$GH_TOKEN_VALUE"

echo ""
echo "══════════════════════════════════════════════════"
ok "Done! Check GitHub → Settings → Secrets → Actions"
echo ""
echo "  Next:"
echo "  1. git push origin gui-polish"
echo "  2. Actions tab → Terraform workflow → Run (plan, then apply)"
echo "  3. Push to main → CI+CD deploys automatically"
echo "══════════════════════════════════════════════════"
echo ""
