# =============================================================================
# Terraform State — stored as GitHub Secret TF_STATE_GCP (base64-encoded)
#
# Same approach as OCI: the workflow saves/restores terraform.tfstate
# via gh secret before/after every run. No GCS bucket needed.
# =============================================================================

terraform {
  backend "local" {}
}
