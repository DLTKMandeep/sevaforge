# =============================================================================
# Sevaforge OCI Terraform — Variables
# =============================================================================

variable "tenancy_ocid" {
  description = "OCID of your OCI tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI user (API key owner)"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the OCI API key"
  type        = string
}

variable "private_key_path" {
  description = "Path to the OCI API private key"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI region (e.g. us-ashburn-1)"
  type        = string
}

variable "compartment_id" {
  description = "OCID of the compartment (use tenancy root)"
  type        = string
}

variable "ocir_image" {
  description = "Full OCIR image path (e.g. iad.ocir.io/namespace/sevaforge:latest)"
  type        = string
  default     = "iad.ocir.io/placeholder/sevaforge:latest"
}
