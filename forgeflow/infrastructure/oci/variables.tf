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

variable "availability_domains" {
  description = "All Availability Domain names in the region — Terraform spreads nodes across all of them to work around OCI capacity limits"
  type        = list(string)
}

variable "kubernetes_version" {
  description = "OKE Kubernetes version — check supported: oci ce cluster-options get --cluster-option-id all"
  type        = string
  default     = "v1.32.1"
}

# node_image_id removed — auto-discovered via oci_core_images data source in main.tf
