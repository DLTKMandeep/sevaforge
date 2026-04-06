# =============================================================================
# Terraform State — stored as GitHub Secret TF_STATE (base64-encoded)
#
# The workflow saves/restores terraform.tfstate via gh secret before/after
# every run. No object storage bucket or extra credentials needed.
# Local backend is used inside the runner; state persists via the secret.
# =============================================================================

terraform {
  backend "local" {}
}
