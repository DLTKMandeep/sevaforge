# =============================================================================
# Terraform Remote State — OCI Object Storage (S3-compatible, Always Free)
#
# All connection values are injected via -backend-config flags in terraform init
# (see .github/workflows/terraform.yml) so no secrets are stored in code.
#
# One-time setup (run once from your laptop):
#   1. Create the bucket:
#      oci os bucket create --name sevaforge-tfstate --versioning Enabled
#
#   2. Get your Object Storage namespace:
#      oci os ns get --query 'data' --raw-output
#
#   3. Create a Customer Secret Key (S3-compatible credentials):
#      OCI Console → Identity → Users → <your user>
#      → Customer Secret Keys → Generate Secret Key
#      Copy both the Access Key ID and the Secret shown ONCE.
#
#   4. Add these GitHub secrets:
#      OCI_NAMESPACE          = <namespace from step 2>
#      OCI_BACKEND_ACCESS_KEY = <Access Key ID from step 3>
#      OCI_BACKEND_SECRET_KEY = <Secret from step 3>
# =============================================================================

terraform {
  backend "s3" {
    # All connection values injected via -backend-config=backend.hcl at init time.
    # Static flags that must live here (cannot be passed via config file in TF 1.7):
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_requesting_account_id  = true  # prevents STS/AWS identity check
    use_path_style              = true  # required for OCI S3-compatible endpoint
  }
}
