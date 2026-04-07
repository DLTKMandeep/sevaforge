# =============================================================================
# Sevaforge OCI Terraform — Outputs
# =============================================================================

output "vm_public_ips" {
  description = "Public IPs of both ARM VMs"
  value       = oci_core_instance.sevaforge[*].public_ip
}

output "load_balancer_ip" {
  description = "Load balancer public IP — point your DNS here"
  value       = oci_load_balancer_load_balancer.sevaforge.ip_address_details[0].ip_address
}

output "ssh_private_key" {
  description = "SSH private key to access VMs"
  value       = tls_private_key.ssh.private_key_pem
  sensitive   = true
}

output "vcn_id" {
  description = "VCN OCID"
  value       = oci_core_vcn.sevaforge.id
}
