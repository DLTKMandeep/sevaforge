output "cluster_id" {
  value = oci_containerengine_cluster.sevaforge.id
}
output "cluster_name" {
  value = oci_containerengine_cluster.sevaforge.name
}
output "vcn_id" {
  value = oci_core_vcn.sevaforge.id
}
