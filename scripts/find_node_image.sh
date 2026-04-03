#!/usr/bin/env bash
# Finds the latest Oracle Linux 8 ARM image OCID for your OCI region
# and saves it directly as GitHub secret OCI_NODE_IMAGE_ID.
#
# Usage: ./scripts/find_node_image.sh

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✅  $1${NC}"; }
die() { echo -e "${RED}❌  $1${NC}"; exit 1; }

command -v oci &>/dev/null || die "oci CLI not found. Run: brew install oci-cli"
command -v gh  &>/dev/null || die "gh CLI not found. Run: brew install gh"

TENANCY=$(grep '^tenancy' ~/.oci/config | head -1 | cut -d= -f2 | tr -d ' \t')
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) \
  || die "Not inside a GitHub repo"

echo ""
echo "Searching for Oracle Linux 8 aarch64 images in your tenancy..."

IMAGE_OCID=$(oci compute image list \
  --compartment-id "$TENANCY" \
  --operating-system "Oracle Linux" \
  --operating-system-version "8" \
  --all \
  --sort-by TIMECREATED \
  --sort-order DESC \
  --query "data[?contains(\"display-name\", 'aarch64')] | [0].id" \
  --raw-output 2>/dev/null || echo "")

if [ -z "$IMAGE_OCID" ] || [ "$IMAGE_OCID" = "null" ]; then
  die "Could not find image. Check: OCI Console → Compute → Images → Platform Images → Oracle Linux 8 → aarch64"
fi

echo "Found → ${IMAGE_OCID}"
echo ""

gh secret set OCI_NODE_IMAGE_ID --repo "$REPO" --body "$IMAGE_OCID"
ok "OCI_NODE_IMAGE_ID saved to GitHub secrets"
echo ""
echo "You're done — no more manual input needed when running the Terraform workflow."
