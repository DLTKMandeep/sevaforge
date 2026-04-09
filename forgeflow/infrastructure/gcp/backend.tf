# =============================================================================
# Terraform State — stored in GCS bucket
# The workflow creates the bucket if it doesn't exist before terraform init
# =============================================================================

terraform {
  backend "gcs" {
    bucket = "sevaforge-tfstate"
    prefix = "gcp"
  }
}
