variable "tenancy_ocid"    { type = string }
variable "user_ocid"       { type = string }
variable "fingerprint"     { type = string }
variable "region"          { type = string }
variable "compartment_id"  { type = string }

variable "private_key_path" {
  type    = string
  default = "~/.oci/oci_api_key.pem"
}

variable "kubernetes_version" {
  type    = string
  default = "v1.32.1"
}

variable "node_shape" {
  description = "Compute shape for worker nodes. Use VM.Standard.A1.Flex (ARM/free) or VM.Standard.E2.1.Micro (AMD/free) as fallback."
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "node_ocpus" {
  description = "OCPUs per node (A1.Flex max 4 on free tier)"
  type        = number
  default     = 2
}

variable "node_memory_gbs" {
  description = "Memory in GB per node (A1.Flex max 24 on free tier)"
  type        = number
  default     = 12
}

variable "node_pool_size" {
  description = "Number of worker nodes"
  type        = number
  default     = 1
}

variable "enable_arm_pool" {
  description = "Set to false to skip ARM node pool when IAD is out of A1 capacity"
  type        = bool
  default     = true
}

variable "enable_amd_fallback" {
  description = "Set to true to create an x86 node pool as fallback when ARM is unavailable"
  type        = bool
  default     = false
}

variable "amd_fallback_shape" {
  description = "x86 flex shape for fallback pool. OKE needs at least 1 OCPU + 6 GB."
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "amd_fallback_ocpus" {
  description = "OCPUs for AMD fallback nodes"
  type        = number
  default     = 1
}

variable "amd_fallback_memory_gbs" {
  description = "Memory in GB for AMD fallback nodes (min 6 for OKE)"
  type        = number
  default     = 8
}
