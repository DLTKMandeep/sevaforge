output "cluster_id" {
  value = oci_containerengine_cluster.sevaforge.id
}
output "cluster_name" {
  value = oci_containerengine_cluster.sevaforge.name
}
output "vcn_id" {
  value = oci_core_vcn.sevaforge.id
}
output "arm_node_pool_id" {
  value = var.enable_arm_pool ? oci_containerengine_node_pool.arm[0].id : null
}
output "amd_node_pool_id" {
  value = var.enable_amd_fallback ? oci_containerengine_node_pool.amd_fallback[0].id : null
}
output "active_node_pool" {
  description = "Which node pool is currently active"
  value       = var.enable_arm_pool ? "arm" : (var.enable_amd_fallback ? "amd_fallback" : "none")
}
