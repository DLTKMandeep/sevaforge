#!/usr/bin/env bash
# =============================================================================
# setup_oci_key.sh — Generate a clean OCI API key, show fingerprint,
#                    update local config, and push to GitHub secrets.
#
# Usage: ./scripts/setup_oci_key.sh
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $1${NC}"; }
info() { echo -e "${YELLOW}▶  $1${NC}"; }

KEY="$HOME/.oci/oci_final.pem"
PUB="$HOME/.oci/oci_final_public.pem"

TENANCY="ocid1.tenancy.oc1..aaaaaaaakcquuddw7iv5ivqd56igw7eaiez3fjokjegktuxemtamu7orbyia"
USER="ocid1.user.oc1..aaaaaaaadvax7npgrlicc2dcbhpxo77gwecabzx6oowdbbxiiw3uif3hbj2a"
REGION="us-ashburn-1"
REPO="DLTKMandeep/sevaforge"

echo ""
echo "══════════════════════════════════════════════════"
echo "  Sevaforge — OCI Key Setup"
echo "══════════════════════════════════════════════════"
echo ""

# ── 1. Generate key ───────────────────────────────────────────────────────────
info "Generating new RSA 2048 key (no passphrase)..."
openssl genrsa -out "$KEY" 2048 2>/dev/null
chmod 600 "$KEY"
ok "Private key → $KEY"

# ── 2. Derive public key ──────────────────────────────────────────────────────
openssl rsa -pubout -in "$KEY" -out "$PUB" 2>/dev/null
ok "Public key  → $PUB"

# ── 3. Compute fingerprint ────────────────────────────────────────────────────
FINGERPRINT=$(openssl rsa -pubout -outform DER -in "$KEY" 2>/dev/null \
  | openssl dgst -md5 -c \
  | awk '{print $2}')
ok "Fingerprint → $FINGERPRINT"

# ── 4. Print public key for OCI Console upload ────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════"
echo "  Copy the public key below and upload to OCI:"
echo "  Console → My Profile → API Keys → Add API Key"
echo "  → Paste a public key → paste → Add"
echo ""
cat "$PUB"
echo "══════════════════════════════════════════════════"
echo ""
read -r -p "  Press ENTER once you've uploaded the key in OCI Console..."

# ── 5. Update local ~/.oci/config ────────────────────────────────────────────
info "Writing ~/.oci/config..."
cat > "$HOME/.oci/config" << EOF
[DEFAULT]
user=${USER}
fingerprint=${FINGERPRINT}
key_file=${KEY}
tenancy=${TENANCY}
region=${REGION}
EOF
chmod 600 "$HOME/.oci/config"
ok "~/.oci/config updated"

# ── 6. Test auth ──────────────────────────────────────────────────────────────
info "Testing OCI auth..."
if oci iam region list --output table 2>/dev/null; then
  ok "OCI auth working!"
else
  echo ""
  echo "❌  Auth failed. Make sure the fingerprint OCI Console showed"
  echo "    matches: ${FINGERPRINT}"
  echo "    If it differs, delete the key in OCI Console and run this script again."
  exit 1
fi

# ── 7. Push to GitHub secrets ─────────────────────────────────────────────────
info "Pushing updated secrets to GitHub..."
gh secret set OCI_PRIVATE_KEY  --repo "$REPO" --body "$(cat "$KEY")"
ok "OCI_PRIVATE_KEY"
gh secret set OCI_FINGERPRINT  --repo "$REPO" --body "$FINGERPRINT"
ok "OCI_FINGERPRINT"

echo ""
echo "══════════════════════════════════════════════════"
ok "All done! Re-run the Terraform workflow in GitHub Actions."
echo "══════════════════════════════════════════════════"
echo ""
