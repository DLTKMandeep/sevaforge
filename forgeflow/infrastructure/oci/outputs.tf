# =============================================================================
# Sevaforge OCI Terraform — Outputs
# =============================================================================

output "cluster_id" {
  description = "OKE cluster OCID — set as GitHub secret OKE_CLUSTER_ID"
  value       = oci_containerengine_cluster.sevaforge.id
}

output "cluster_name" {
  description = "OKE cluster display name"
  value       = oci_containerengine_cluster.sevaforge.name
}

output "kubeconfig_command" {
  description = "Run this command to generate kubeconfig (then base64-encode for GitHub secret KUBE_CONFIG)"
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.sevaforge.id} --region ${var.region} --token-version 2.0.0 --file ~/.kube/sevaforge-config && base64 -w0 ~/.kube/sevaforge-config"
}

output "ocir_endpoint" {
  description = "OCIR registry endpoint for your region"
  value       = "${replace(var.region, "-", "")}.ocir.io"
}

output "vcn_id" {
  description = "VCN OCID"
  value       = oci_core_vcn.sevaforge.id
}

output "public_subnet_id" {
  description = "Public subnet OCID (Load Balancer)"
  value       = oci_core_subnet.public.id
}

output "workers_subnet_id" {
  description = "Workers subnet OCID"
  value       = oci_core_subnet.workers.id
}
