#!/usr/bin/env bash
# =============================================================================
# ForgeFlow — GitHub Secrets Bootstrap
# Reads deploy/secrets/inventory.yaml, prompts for each value, sets via gh.
# Requires: gh CLI (authenticated), jq, yq.
# Run from repo root:  ./deploy/secrets/bootstrap.sh
# =============================================================================
set -euo pipefail
REPO="${REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
echo "=== Setting GitHub secrets for $REPO ==="

# GitHub PAT with 'repo' + 'workflow' scope for CI/CD automation
if [ -z "${GH_TOKEN:-}" ]; then
  read -r -s -p "Enter value for GH_TOKEN (GitHub PAT with 'repo' + 'workflow' scope for CI/CD automation): " GH_TOKEN
  echo
fi
gh secret set GH_TOKEN --repo "$REPO" --body "${GH_TOKEN}"
echo "✓ Set GH_TOKEN"

# JSON key for the deployer service account (IAM > Service Accounts)
if [ -z "${GCP_SA_KEY:-}" ]; then
  read -r -s -p "Enter value for GCP_SA_KEY (JSON key for the deployer service account (IAM > Service Accounts)): " GCP_SA_KEY
  echo
fi
gh secret set GCP_SA_KEY --repo "$REPO" --body "${GCP_SA_KEY}"
echo "✓ Set GCP_SA_KEY"

# GCP project id, e.g. divine-data-469116-b2
if [ -z "${GCP_PROJECT_ID:-}" ]; then
  read -r -s -p "Enter value for GCP_PROJECT_ID (GCP project id, e.g. divine-data-469116-b2): " GCP_PROJECT_ID
  echo
fi
gh secret set GCP_PROJECT_ID --repo "$REPO" --body "${GCP_PROJECT_ID}"
echo "✓ Set GCP_PROJECT_ID"

# Primary GCP region, e.g. us-central1
if [ -z "${GCP_REGION:-}" ]; then
  read -r -s -p "Enter value for GCP_REGION (Primary GCP region, e.g. us-central1): " GCP_REGION
  echo
fi
gh secret set GCP_REGION --repo "$REPO" --body "${GCP_REGION}"
echo "✓ Set GCP_REGION"

# Connection string for primary database
if [ -z "${DATABASE_URL:-}" ]; then
  read -r -s -p "Enter value for DATABASE_URL (Connection string for primary database): " DATABASE_URL
  echo
fi
gh secret set DATABASE_URL --repo "$REPO" --body "${DATABASE_URL}"
echo "✓ Set DATABASE_URL"

# Secret key for signing JWT tokens
if [ -z "${JWT_SECRET:-}" ]; then
  read -r -s -p "Enter value for JWT_SECRET (Secret key for signing JWT tokens): " JWT_SECRET
  echo
fi
gh secret set JWT_SECRET --repo "$REPO" --body "${JWT_SECRET}"
echo "✓ Set JWT_SECRET"

# Connection string for Redis
if [ -z "${REDIS_URL:-}" ]; then
  read -r -s -p "Enter value for REDIS_URL (Connection string for Redis): " REDIS_URL
  echo
fi
gh secret set REDIS_URL --repo "$REPO" --body "${REDIS_URL}"
echo "✓ Set REDIS_URL"

# Secret key for signing session cookies
if [ -z "${SESSION_SECRET:-}" ]; then
  read -r -s -p "Enter value for SESSION_SECRET (Secret key for signing session cookies): " SESSION_SECRET
  echo
fi
gh secret set SESSION_SECRET --repo "$REPO" --body "${SESSION_SECRET}"
echo "✓ Set SESSION_SECRET"

# Stripe API key
if [ -z "${STRIPE_API_KEY:-}" ]; then
  read -r -s -p "Enter value for STRIPE_API_KEY (Stripe API key): " STRIPE_API_KEY
  echo
fi
gh secret set STRIPE_API_KEY --repo "$REPO" --body "${STRIPE_API_KEY}"
echo "✓ Set STRIPE_API_KEY"

# OpenAI API key
if [ -z "${OPENAI_API_KEY:-}" ]; then
  read -r -s -p "Enter value for OPENAI_API_KEY (OpenAI API key): " OPENAI_API_KEY
  echo
fi
gh secret set OPENAI_API_KEY --repo "$REPO" --body "${OPENAI_API_KEY}"
echo "✓ Set OPENAI_API_KEY"

# Anthropic API key
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  read -r -s -p "Enter value for ANTHROPIC_API_KEY (Anthropic API key): " ANTHROPIC_API_KEY
  echo
fi
gh secret set ANTHROPIC_API_KEY --repo "$REPO" --body "${ANTHROPIC_API_KEY}"
echo "✓ Set ANTHROPIC_API_KEY"

# SendGrid API key
if [ -z "${SENDGRID_API_KEY:-}" ]; then
  read -r -s -p "Enter value for SENDGRID_API_KEY (SendGrid API key): " SENDGRID_API_KEY
  echo
fi
gh secret set SENDGRID_API_KEY --repo "$REPO" --body "${SENDGRID_API_KEY}"
echo "✓ Set SENDGRID_API_KEY"

# SMTP password for outbound email
if [ -z "${SMTP_PASSWORD:-}" ]; then
  read -r -s -p "Enter value for SMTP_PASSWORD (SMTP password for outbound email): " SMTP_PASSWORD
  echo
fi
gh secret set SMTP_PASSWORD --repo "$REPO" --body "${SMTP_PASSWORD}"
echo "✓ Set SMTP_PASSWORD"

echo "=== All secrets set ==="
