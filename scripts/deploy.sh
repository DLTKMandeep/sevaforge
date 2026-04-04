#!/usr/bin/env bash
# =============================================================================
# deploy.sh — full Sevaforge OCI setup in one command
# Cleans orphans, creates state bucket, sets all secrets, pushes, triggers apply
# Usage: ./scripts/deploy.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
info() { echo -e "${BLUE}▶ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

REPO="DLTKMandeep/sevaforge"
BUCKET="sevaforge-tfstate"
KEY_NAME="terraform-state"

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
command -v oci  >/dev/null || die "OCI CLI not found. Run: pip install oci-cli"
command -v gh   >/dev/null || die "GitHub CLI not found. Run: brew install gh"
command -v git  >/dev/null || die "git not found"

oci iam region list --output table > /dev/null 2>&1 || die "OCI auth failed — check ~/.oci/config"
gh auth status > /dev/null 2>&1 || die "GitHub CLI not authenticated — run: gh auth login"

COMPARTMENT_ID=$(grep '^tenancy=' ~/.oci/config | head -1 | cut -d= -f2 | tr -d ' ')
USER_OCID=$(grep '^user=' ~/.oci/config | head -1 | cut -d= -f2 | tr -d ' ')
REGION=$(grep '^region=' ~/.oci/config | head -1 | cut -d= -f2 | tr -d ' ')

[ -z "$COMPARTMENT_ID" ] && die "Cannot read tenancy from ~/.oci/config"
[ -z "$USER_OCID" ]      && die "Cannot read user from ~/.oci/config"
[ -z "$REGION" ]         && die "Cannot read region from ~/.oci/config"

info "Tenancy : $COMPARTMENT_ID"
info "User    : $USER_OCID"
info "Region  : $REGION"
echo ""

# ── 1. Push latest code ───────────────────────────────────────────────────────
info "Pushing latest code..."
cd "$(git rev-parse --show-toplevel)"
git push origin gui-polish 2>&1 | tail -3
git push origin main       2>&1 | tail -3
ok "Code pushed"

# ── 2. Clean up ALL orphaned sevaforge OCI resources ─────────────────────────
info "Cleaning up orphaned OCI resources..."

delete_node_pools() {
  NPS=$(oci ce node-pool list --compartment-id "$COMPARTMENT_ID" \
    --query 'data[*].id' --raw-output 2>/dev/null \
    | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)
  for NP in $NPS; do
    warn "Deleting node pool $NP"
    oci ce node-pool delete --node-pool-id "$NP" --force 2>/dev/null || true
    sleep 15
  done
}

delete_clusters() {
  CLS=$(oci ce cluster list --compartment-id "$COMPARTMENT_ID" \
    --lifecycle-state ACTIVE \
    --query 'data[*].id' --raw-output 2>/dev/null \
    | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)
  for CL in $CLS; do
    warn "Deleting cluster $CL"
    oci ce cluster delete --cluster-id "$CL" --force 2>/dev/null || true
    sleep 30
  done
}

delete_vcn_resources() {
  VCNS=$(oci network vcn list --compartment-id "$COMPARTMENT_ID" \
    --query "data[?contains(\"display-name\",'sevaforge')].id" \
    --raw-output 2>/dev/null \
    | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

  for VCN in $VCNS; do
    # subnets
    for SN in $(oci network subnet list --compartment-id "$COMPARTMENT_ID" --vcn-id "$VCN" \
      --query 'data[*].id' --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$'); do
      warn "Deleting subnet $SN"; oci network subnet delete --subnet-id "$SN" --force 2>/dev/null || true
    done
    # security lists (skip default)
    for SL in $(oci network security-list list --compartment-id "$COMPARTMENT_ID" --vcn-id "$VCN" \
      --query "data[?contains(\"display-name\",'sevaforge')].id" \
      --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$'); do
      warn "Deleting security list $SL"; oci network security-list delete --security-list-id "$SL" --force 2>/dev/null || true
    done
    # route tables (skip default)
    for RT in $(oci network route-table list --compartment-id "$COMPARTMENT_ID" --vcn-id "$VCN" \
      --query "data[?contains(\"display-name\",'sevaforge')].id" \
      --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$'); do
      warn "Deleting route table $RT"; oci network route-table delete --rt-id "$RT" --force 2>/dev/null || true
    done
    # internet gateways
    for IGW in $(oci network internet-gateway list --compartment-id "$COMPARTMENT_ID" --vcn-id "$VCN" \
      --query 'data[*].id' --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$'); do
      warn "Deleting IGW $IGW"; oci network internet-gateway delete --ig-id "$IGW" --force 2>/dev/null || true
    done
    warn "Deleting VCN $VCN"
    oci network vcn delete --vcn-id "$VCN" --force 2>/dev/null || true
  done
}

delete_node_pools
delete_clusters
delete_vcn_resources
ok "Orphaned resources cleaned"

# ── 3. Create state bucket ────────────────────────────────────────────────────
info "Creating Terraform state bucket: $BUCKET"
EXISTING=$(oci os bucket list --compartment-id "$COMPARTMENT_ID" \
  --query "data[?name=='$BUCKET'].name" --raw-output 2>/dev/null | tr -d '[]"' | tr -d ' ' || true)

if [ "$EXISTING" = "$BUCKET" ]; then
  ok "Bucket already exists — skipping"
else
  oci os bucket create \
    --compartment-id "$COMPARTMENT_ID" \
    --name "$BUCKET" \
    --versioning Enabled 2>/dev/null
  ok "Bucket created"
fi

# ── 4. Get Object Storage namespace ──────────────────────────────────────────
info "Getting Object Storage namespace..."
NAMESPACE=$(oci os ns get --query 'data' --raw-output)
ok "Namespace: $NAMESPACE"

# ── 5. Create Customer Secret Key for S3 backend ─────────────────────────────
info "Creating Customer Secret Key for Terraform state backend..."

# Remove any old key with same name to avoid confusion
OLD_KEY_ID=$(oci iam customer-secret-key list --user-id "$USER_OCID" \
  --query "data[?\"display-name\"=='$KEY_NAME'].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr -d ' ' | head -1 || true)

if [ -n "$OLD_KEY_ID" ]; then
  warn "Removing old key $OLD_KEY_ID"
  oci iam customer-secret-key delete --user-id "$USER_OCID" \
    --customer-secret-key-id "$OLD_KEY_ID" --force 2>/dev/null || true
fi

KEY_JSON=$(oci iam customer-secret-key create \
  --user-id "$USER_OCID" \
  --display-name "$KEY_NAME")

ACCESS_KEY=$(echo "$KEY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])")
SECRET_KEY=$(echo "$KEY_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['key'])")

[ -z "$ACCESS_KEY" ] && die "Failed to get access key from OCI response"
[ -z "$SECRET_KEY" ] && die "Failed to get secret key from OCI response"
ok "Customer Secret Key created"

# ── 6. Push all GitHub secrets ────────────────────────────────────────────────
info "Pushing GitHub secrets..."

push_secret() {
  local name="$1" value="$2"
  printf '%s' "$value" | gh secret set "$name" --repo "$REPO" 2>/dev/null \
    && ok "  $name" || warn "  $name — failed (check gh auth scopes)"
}

push_secret "OCI_NAMESPACE"          "$NAMESPACE"
push_secret "OCI_BACKEND_ACCESS_KEY" "$ACCESS_KEY"
push_secret "OCI_BACKEND_SECRET_KEY" "$SECRET_KEY"

# ── 7. Trigger Terraform apply ────────────────────────────────────────────────
info "Triggering Terraform apply workflow..."
gh workflow run terraform.yml \
  --repo "$REPO" \
  --ref main \
  --field branch=gui-polish \
  --field action=apply

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} All done! Terraform apply is running.${NC}"
echo -e "${GREEN} Watch it at:${NC}"
echo -e "${BLUE} https://github.com/$REPO/actions${NC}"
echo -e "${GREEN}============================================${NC}"
