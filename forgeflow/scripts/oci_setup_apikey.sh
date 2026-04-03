#!/usr/bin/env bash
# =============================================================================
# oci_setup_apikey.sh — Generate OCI API key & print all values needed for
#                        terraform.tfvars and GitHub secrets in one shot.
#
# Usage:
#   chmod +x scripts/oci_setup_apikey.sh
#   ./scripts/oci_setup_apikey.sh
#
# Requirements: oci CLI installed and logged in (oci setup config done once)
# =============================================================================

set -euo pipefail

OCI_DIR="$HOME/.oci"
KEY_FILE="$OCI_DIR/oci_api_key.pem"
PUB_FILE="$OCI_DIR/oci_api_key_public.pem"

mkdir -p "$OCI_DIR"
chmod 700 "$OCI_DIR"

echo ""
echo "══════════════════════════════════════════════"
echo "  Sevaforge — OCI API Key Setup"
echo "══════════════════════════════════════════════"

# ── 1. Generate RSA 2048 key pair ────────────────────────────────────────────
if [ -f "$KEY_FILE" ]; then
  echo ""
  echo "⚠️  $KEY_FILE already exists."
  read -r -p "   Overwrite it? (y/N): " CONFIRM
  [[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

echo ""
echo "▶ Generating RSA 2048 private key → $KEY_FILE"
openssl genrsa -out "$KEY_FILE" 2048 2>/dev/null
chmod 600 "$KEY_FILE"

echo "▶ Deriving public key  → $PUB_FILE"
openssl rsa -pubout -in "$KEY_FILE" -out "$PUB_FILE" 2>/dev/null

# ── 2. Upload public key to OCI & grab fingerprint ───────────────────────────
echo ""
echo "▶ Uploading public key to OCI..."

USER_OCID=$(oci iam user list --query 'data[0].id' --raw-output 2>/dev/null)
if [ -z "$USER_OCID" ]; then
  echo "❌  Could not retrieve user OCID. Run 'oci setup config' first."
  exit 1
fi

UPLOAD_RESULT=$(oci iam user api-key upload \
  --user-id "$USER_OCID" \
  --key-file "$PUB_FILE" \
  2>/dev/null)

FINGERPRINT=$(echo "$UPLOAD_RESULT" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['data']['fingerprint'])")

# ── 3. Collect remaining values ───────────────────────────────────────────────
TENANCY_OCID=$(oci iam tenancy get \
  --tenancy-id "$(oci iam session validate \
    --query 'data."tenancy-id"' --raw-output 2>/dev/null)" \
  --query 'data.id' --raw-output 2>/dev/null || echo "$OCI_TENANCY")

# Fallback: read tenancy from oci config
if [ -z "$TENANCY_OCID" ] || [ "$TENANCY_OCID" = "" ]; then
  TENANCY_OCID=$(grep '^tenancy' "$OCI_DIR/config" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' ')
fi

REGION=$(grep '^region' "$OCI_DIR/config" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' ')

OBJ_NAMESPACE=$(oci os ns get --query 'data' --raw-output 2>/dev/null)

AVAIL_DOMAIN=$(oci iam availability-domain list \
  --compartment-id "$TENANCY_OCID" \
  --query 'data[0].name' --raw-output 2>/dev/null)

# Map region → short key
declare -A REGION_KEYS=(
  [us-ashburn-1]=iad   [us-phoenix-1]=phx   [us-chicago-1]=ord
  [eu-frankfurt-1]=fra [eu-amsterdam-1]=ams  [eu-zurich-1]=zrh
  [ap-sydney-1]=syd    [ap-tokyo-1]=nrt      [ap-singapore-1]=sin
  [ap-mumbai-1]=bom    [uk-london-1]=lhr     [ca-toronto-1]=yyz
  [sa-saopaulo-1]=gru  [me-dubai-1]=dxb
)
REGION_KEY="${REGION_KEYS[$REGION]:-${REGION%%-*}}"

PRIVATE_KEY_CONTENTS=$(cat "$KEY_FILE")

# ── 4. Print everything ───────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅  API key created and uploaded to OCI"
echo "══════════════════════════════════════════════"
echo ""
echo "── terraform.tfvars values ──────────────────"
echo "tenancy_ocid        = \"$TENANCY_OCID\""
echo "user_ocid           = \"$USER_OCID\""
echo "fingerprint         = \"$FINGERPRINT\""
echo "private_key_path    = \"$KEY_FILE\""
echo "region              = \"$REGION\""
echo "compartment_id      = \"$TENANCY_OCID\"   # (same as tenancy root)"
echo "availability_domain = \"$AVAIL_DOMAIN\""
echo ""
echo "── GitHub Secrets ───────────────────────────"
echo "OCI_TENANCY_OCID  → $TENANCY_OCID"
echo "OCI_USER_OCID     → $USER_OCID"
echo "OCI_FINGERPRINT   → $FINGERPRINT"
echo "OCI_REGION        → $REGION"
echo "OCI_REGION_KEY    → $REGION_KEY"
echo "OCI_NAMESPACE     → $OBJ_NAMESPACE"
echo "OCI_USERNAME      → (your OCI login email)"
echo ""
echo "── OCI_PRIVATE_KEY (paste the block below) ──"
echo "$PRIVATE_KEY_CONTENTS"
echo ""
echo "── Key files ────────────────────────────────"
echo "Private key : $KEY_FILE"
echo "Public key  : $PUB_FILE"
echo ""
echo "⚠️  Keep $KEY_FILE secret — never commit it."
echo "══════════════════════════════════════════════"
echo ""
echo "Next step: find your ARM node image OCID, then run:"
echo "  cd infrastructure/oci && cp terraform.tfvars.example terraform.tfvars"
echo "  # paste the values above, add node_image_id"
echo "  terraform init && terraform apply"
echo ""
