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
