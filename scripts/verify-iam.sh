#!/usr/bin/env bash
# Verify IAM service accounts exist — sevaforge_unified (AWS)
set -euo pipefail

echo "Verifying IAM service accounts for sevaforge_unified..."
FAIL=0

check_user() {
  local name=$1
  if aws iam get-user --user-name "$name" &>/dev/null; then
    echo "  ✅ IAM user: $name"
  else
    echo "  ❌ MISSING: $name"
    FAIL=1
  fi
}

check_role() {
  local name=$1
  if aws iam get-role --role-name "$name" &>/dev/null; then
    echo "  ✅ IAM role: $name"
  else
    echo "  ❌ MISSING: $name"
    FAIL=1
  fi
}

check_user terraform-deployer
check_role cicd-image-pusher
check_role eks-node-role
check_role external-secrets-operator

if [[ $FAIL -eq 0 ]]; then
  echo ""
  echo "✅ All IAM accounts verified."
else
  echo ""
  echo "❌ Missing accounts. See docs/IAM_POLICIES.md for setup instructions."
  exit 1
fi
