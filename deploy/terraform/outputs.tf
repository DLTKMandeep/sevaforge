###############################################################################
# SevaForge - Outputs
###############################################################################

# -----------------------------------------------------------------------------
# GKE Cluster
# -----------------------------------------------------------------------------

output "gke_cluster_name" {
  description = "Name of the GKE cluster"
  value       = google_container_cluster.main.name
}

output "gke_cluster_endpoint" {
  description = "Endpoint of the GKE cluster API server"
  value       = google_container_cluster.main.endpoint
  sensitive   = true
}

output "gke_cluster_ca_certificate" {
  description = "Base64-encoded CA certificate for the GKE cluster"
  value       = google_container_cluster.main.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "gke_cluster_location" {
  description = "Location of the GKE cluster"
  value       = google_container_cluster.main.location
}

# -----------------------------------------------------------------------------
# Cloud SQL
# -----------------------------------------------------------------------------

output "sql_instance_name" {
  description = "Name of the primary Cloud SQL instance"
  value       = google_sql_database_instance.primary.name
}

output "sql_instance_connection_name" {
  description = "Connection name for Cloud SQL Proxy"
  value       = google_sql_database_instance.primary.connection_name
}

output "sql_private_ip" {
  description = "Private IP address of the primary Cloud SQL instance"
  value       = google_sql_database_instance.primary.private_ip_address
  sensitive   = true
}

output "sql_replica_private_ip" {
  description = "Private IP address of the Cloud SQL read replica"
  value       = google_sql_database_instance.read_replica.private_ip_address
  sensitive   = true
}

output "sql_database_name" {
  description = "Name of the application database"
  value       = google_sql_database.main.name
}

output "sql_user_name" {
  description = "Name of the application database user"
  value       = google_sql_user.app.name
}

# -----------------------------------------------------------------------------
# Redis
# -----------------------------------------------------------------------------

output "redis_host" {
  description = "Hostname of the Redis instance"
  value       = google_redis_instance.main.host
  sensitive   = true
}

output "redis_port" {
  description = "Port of the Redis instance"
  value       = google_redis_instance.main.port
}

output "redis_auth_string" {
  description = "AUTH string for Redis (if auth enabled)"
  value       = google_redis_instance.main.auth_string
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Load Balancer & Networking
# -----------------------------------------------------------------------------

output "lb_global_ip" {
  description = "Global static IP of the HTTPS load balancer"
  value       = google_compute_global_address.lb.address
}

output "ssl_certificate_id" {
  description = "ID of the managed SSL certificate"
  value       = google_compute_managed_ssl_certificate.main.id
}

output "cloud_armor_policy_id" {
  description = "ID of the Cloud Armor WAF security policy"
  value       = google_compute_security_policy.waf.id
}

# -----------------------------------------------------------------------------
# DNS
# -----------------------------------------------------------------------------

output "dns_zone_name" {
  description = "Name of the Cloud DNS managed zone"
  value       = google_dns_managed_zone.main.name
}

output "dns_name_servers" {
  description = "Nameservers for the DNS zone (configure at registrar)"
  value       = google_dns_managed_zone.main.name_servers
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------

output "vpc_id" {
  description = "ID of the VPC network"
  value       = google_compute_network.main.id
}

output "vpc_name" {
  description = "Name of the VPC network"
  value       = google_compute_network.main.name
}

output "subnet_app_id" {
  description = "ID of the application subnet"
  value       = google_compute_subnetwork.app.id
}

# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------

output "artifacts_bucket_name" {
  description = "Name of the artifacts GCS bucket"
  value       = google_storage_bucket.artifacts.name
}

output "artifacts_bucket_url" {
  description = "URL of the artifacts GCS bucket"
  value       = google_storage_bucket.artifacts.url
}

output "terraform_state_bucket" {
  description = "Name of the Terraform state GCS bucket"
  value       = google_storage_bucket.terraform_state.name
}

output "worker_disk_name" {
  description = "Name of the persistent SSD disk for workers"
  value       = google_compute_disk.worker_ssd.name
}

# -----------------------------------------------------------------------------
# Service Accounts
# -----------------------------------------------------------------------------

output "gke_node_sa_email" {
  description = "Email of the GKE node service account"
  value       = google_service_account.gke_nodes.email
}

output "app_workload_sa_email" {
  description = "Email of the app Workload Identity service account"
  value       = google_service_account.app_workload.email
}

output "worker_workload_sa_email" {
  description = "Email of the worker Workload Identity service account"
  value       = google_service_account.worker_workload.email
}

output "cicd_sa_email" {
  description = "Email of the CI/CD service account"
  value       = google_service_account.cicd.email
}

# -----------------------------------------------------------------------------
# Connection Strings (for application configuration)
# -----------------------------------------------------------------------------

output "database_connection_string" {
  description = "PostgreSQL connection string (password must be fetched from Secret Manager)"
  value       = "postgresql://${google_sql_user.app.name}@${google_sql_database_instance.primary.private_ip_address}:5432/${google_sql_database.main.name}?sslmode=require"
  sensitive   = true
}

output "redis_connection_string" {
  description = "Redis connection string (auth string must be fetched from Redis output)"
  value       = "redis://:AUTH@${google_redis_instance.main.host}:${google_redis_instance.main.port}"
  sensitive   = true
}

# -----------------------------------------------------------------------------
# Kubectl Configuration Command
# -----------------------------------------------------------------------------

output "kubectl_config_command" {
  description = "Command to configure kubectl for the GKE cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.main.name} --region ${var.region} --project ${var.project_id}"
}
