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
