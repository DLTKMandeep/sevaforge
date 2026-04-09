output "cluster_name" {
  value = google_container_cluster.sevaforge.name
}

output "cluster_endpoint" {
  value     = google_container_cluster.sevaforge.endpoint
  sensitive = true
}

output "cluster_ca_certificate" {
  value     = google_container_cluster.sevaforge.master_auth[0].cluster_ca_certificate
  sensitive = true
}

output "region" {
  value = var.region
}

output "project_id" {
  value = var.project_id
}

output "vpc_name" {
  value = google_compute_network.sevaforge.name
}
