#!/usr/bin/env bash
# =============================================================================
# cleanup_oci_orphans.sh
#
# Deletes all orphaned Sevaforge OCI resources created by failed Terraform runs.
# Run this ONCE from your laptop before the next terraform apply.
#
# Prerequisites: OCI CLI configured (~/.oci/config set up)
# Usage:  chmod +x scripts/cleanup_oci_orphans.sh
#         ./scripts/cleanup_oci_orphans.sh
# =============================================================================
set -uo pipefail

COMPARTMENT_ID=$(oci iam compartment list --all --query "data[?\"lifecycle-state\"=='ACTIVE'] | [0].id" --raw-output 2>/dev/null)
# Fall back to tenancy root if no sub-compartment
TENANCY_OCID=$(oci iam region-subscription list --query "data[0].\"region-name\"" --raw-output 2>/dev/null || true)
COMPARTMENT_ID=$(grep '^tenancy=' ~/.oci/config | head -1 | cut -d= -f2 | tr -d ' ')

echo "============================================"
echo " Sevaforge OCI Orphan Cleanup"
echo " Compartment: ${COMPARTMENT_ID}"
echo "============================================"
echo ""

# ── 1. Delete OKE Node Pools ────────────────────────────────────────────────
echo "▶ Scanning for OKE node pools..."
NODE_POOLS=$(oci ce node-pool list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query 'data[*].id' \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

if [ -n "${NODE_POOLS}" ]; then
  for NP in ${NODE_POOLS}; do
    echo "  Deleting node pool: ${NP}"
    oci ce node-pool delete --node-pool-id "${NP}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete (may already be gone)"
    echo "  Waiting for node pool deletion..."
    sleep 30
  done
else
  echo "  No node pools found."
fi

# ── 2. Delete OKE Clusters ───────────────────────────────────────────────────
echo ""
echo "▶ Scanning for OKE clusters..."
CLUSTERS=$(oci ce cluster list \
  --compartment-id "${COMPARTMENT_ID}" \
  --lifecycle-state ACTIVE \
  --query 'data[*].id' \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

if [ -n "${CLUSTERS}" ]; then
  for CL in ${CLUSTERS}; do
    echo "  Deleting cluster: ${CL}"
    oci ce cluster delete --cluster-id "${CL}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete"
    echo "  Waiting for cluster deletion..."
    sleep 60
  done
else
  echo "  No active clusters found."
fi

# ── 3. Delete Subnets ────────────────────────────────────────────────────────
echo ""
echo "▶ Scanning for sevaforge subnets..."
SUBNETS=$(oci network subnet list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query "data[?contains(\"display-name\",'sevaforge')].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

if [ -n "${SUBNETS}" ]; then
  for SN in ${SUBNETS}; do
    echo "  Deleting subnet: ${SN}"
    oci network subnet delete --subnet-id "${SN}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete"
  done
else
  echo "  No sevaforge subnets found."
fi

# ── 4. Delete Security Lists ─────────────────────────────────────────────────
echo ""
echo "▶ Scanning for sevaforge security lists..."
SLS=$(oci network security-list list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query "data[?contains(\"display-name\",'sevaforge')].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

for SL in ${SLS}; do
  echo "  Deleting security list: ${SL}"
  oci network security-list delete --security-list-id "${SL}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete"
done

# ── 5. Delete Route Tables ───────────────────────────────────────────────────
echo ""
echo "▶ Scanning for sevaforge route tables..."
RTS=$(oci network route-table list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query "data[?contains(\"display-name\",'sevaforge')].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

for RT in ${RTS}; do
  echo "  Deleting route table: ${RT}"
  oci network route-table delete --rt-id "${RT}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete"
done

# ── 6. Delete Internet Gateways ──────────────────────────────────────────────
echo ""
echo "▶ Scanning for sevaforge internet gateways..."
IGW_VCNS=$(oci network vcn list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query "data[?contains(\"display-name\",'sevaforge')].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

for VCN_ID in ${IGW_VCNS}; do
  IGWS=$(oci network internet-gateway list \
    --compartment-id "${COMPARTMENT_ID}" \
    --vcn-id "${VCN_ID}" \
    --query 'data[*].id' \
    --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)
  for IGW in ${IGWS}; do
    echo "  Deleting internet gateway: ${IGW}"
    oci network internet-gateway delete --ig-id "${IGW}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete"
  done
done

# ── 7. Delete VCNs ───────────────────────────────────────────────────────────
echo ""
echo "▶ Scanning for sevaforge VCNs..."
VCNS=$(oci network vcn list \
  --compartment-id "${COMPARTMENT_ID}" \
  --query "data[?contains(\"display-name\",'sevaforge')].id" \
  --raw-output 2>/dev/null | tr -d '[]"' | tr ',' '\n' | tr -d ' ' | grep -v '^$' || true)

if [ -n "${VCNS}" ]; then
  for VCN in ${VCNS}; do
    echo "  Deleting VCN: ${VCN}"
    oci network vcn delete --vcn-id "${VCN}" --force 2>/dev/null && echo "  ✓ Deleted" || echo "  ⚠ Could not delete (check for remaining dependencies)"
  done
else
  echo "  No sevaforge VCNs found."
fi

echo ""
echo "============================================"
echo " Cleanup complete."
echo " Now set up the state backend secrets and"
echo " re-run the Terraform workflow."
echo "============================================"
