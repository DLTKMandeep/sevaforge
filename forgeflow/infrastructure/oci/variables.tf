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
  description = "Local path to the OCI API private key (.pem)"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI region identifier (e.g. us-ashburn-1)"
  type        = string
}

variable "compartment_id" {
  description = "OCID of the compartment to deploy into (use tenancy root for simplicity)"
  type        = string
}

variable "availability_domain" {
  description = "Availability Domain name (e.g. Uocm:US-ASHBURN-AD-1) — find with: oci iam availability-domain list"
  type        = string
}

variable "kubernetes_version" {
  description = "OKE Kubernetes version"
  type        = string
  default     = "v1.29.1"
}

variable "node_image_id" {
  description = "OCID of the Oracle Linux 8 ARM image for worker nodes — find at: https://docs.oracle.com/en-us/iaas/images/"
  type        = string
  # Example (us-ashburn-1 OL8 ARM, update as needed):
  # default = "ocid1.image.oc1.iad.aaaaaaaaxxx..."
}
