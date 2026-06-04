###############################################################################
# SevaForge - Input Variables
###############################################################################

# -----------------------------------------------------------------------------
# Project & Environment
# -----------------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID for SevaForge deployment"
  type        = string
  default     = "sevaforge-prod"
}

variable "project_name" {
  description = "Short project name used in resource naming"
  type        = string
  default     = "sevaforge"
}

variable "region" {
  description = "GCP region for all regional resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (prod, staging, dev)"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "Environment must be one of: prod, staging, dev."
  }
}

# -----------------------------------------------------------------------------
# VPC & Networking
# -----------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "Primary CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_app_cidr" {
  description = "CIDR for the application subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "subnet_services_cidr" {
  description = "CIDR for the services subnet (Cloud SQL, Redis)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "subnet_pods_cidr" {
  description = "CIDR for the GKE pods secondary range"
  type        = string
  default     = "10.0.16.0/20"
}

variable "subnet_services_secondary_cidr" {
  description = "CIDR for the GKE services secondary range"
  type        = string
  default     = "10.0.32.0/20"
}

variable "master_ipv4_cidr" {
  description = "CIDR for GKE master nodes (must be /28)"
  type        = string
  default     = "10.0.64.0/28"
}

# -----------------------------------------------------------------------------
# Domain & SSL
# -----------------------------------------------------------------------------

variable "domain_name" {
  description = "Primary domain name for SevaForge"
  type        = string
  default     = "sevaforge.io"
}

variable "dns_managed_zone_name" {
  description = "Name for the Cloud DNS managed zone"
  type        = string
  default     = "sevaforge-io"
}

# -----------------------------------------------------------------------------
# GKE Configuration
# -----------------------------------------------------------------------------

variable "gke_release_channel" {
  description = "GKE release channel (REGULAR, RAPID, STABLE)"
  type        = string
  default     = "REGULAR"
}

variable "gke_master_authorized_networks" {
  description = "List of CIDR blocks authorized to access the GKE master"
  type = list(object({
    cidr_block   = string
    display_name = string
  }))
  default = []
}

variable "app_pool_machine_type" {
  description = "Machine type for the application node pool"
  type        = string
  default     = "e2-standard-4"
}

variable "app_pool_min_nodes" {
  description = "Minimum number of nodes in the app pool"
  type        = number
  default     = 2
}

variable "app_pool_max_nodes" {
  description = "Maximum number of nodes in the app pool"
  type        = number
  default     = 6
}

variable "worker_pool_machine_type" {
  description = "Machine type for the worker node pool"
  type        = string
  default     = "e2-highmem-4"
}

variable "worker_pool_min_nodes" {
  description = "Minimum number of nodes in the worker pool"
  type        = number
  default     = 1
}

variable "worker_pool_max_nodes" {
  description = "Maximum number of nodes in the worker pool"
  type        = number
  default     = 8
}

# -----------------------------------------------------------------------------
# Cloud SQL Configuration
# -----------------------------------------------------------------------------

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-4-16384"
}

variable "db_disk_size_gb" {
  description = "Cloud SQL disk size in GB"
  type        = number
  default     = 100
}

variable "db_name" {
  description = "Name of the default application database"
  type        = string
  default     = "sevaforge"
}

variable "db_user" {
  description = "Name of the default database user"
  type        = string
  default     = "sevaforge_app"
}

variable "db_postgres_version" {
  description = "PostgreSQL version for Cloud SQL"
  type        = string
  default     = "POSTGRES_15"
}

variable "db_availability_type" {
  description = "Cloud SQL availability type (REGIONAL for HA, ZONAL for single zone)"
  type        = string
  default     = "REGIONAL"
}

variable "db_backup_enabled" {
  description = "Enable automated backups for Cloud SQL"
  type        = bool
  default     = true
}

variable "db_backup_start_time" {
  description = "Start time for Cloud SQL backup window (HH:MM format, UTC)"
  type        = string
  default     = "03:00"
}

variable "db_maintenance_day" {
  description = "Day of week for Cloud SQL maintenance (1=Monday, 7=Sunday)"
  type        = number
  default     = 7
}

variable "db_maintenance_hour" {
  description = "Hour for Cloud SQL maintenance (0-23, UTC)"
  type        = number
  default     = 4
}

# -----------------------------------------------------------------------------
# Redis Configuration
# -----------------------------------------------------------------------------

variable "redis_memory_size_gb" {
  description = "Memory size for Memorystore Redis in GB"
  type        = number
  default     = 6
}

variable "redis_version" {
  description = "Redis version for Memorystore"
  type        = string
  default     = "REDIS_7_0"
}

# -----------------------------------------------------------------------------
# Storage
# -----------------------------------------------------------------------------

variable "worker_disk_size_gb" {
  description = "Size of persistent SSD disk for workers in GB"
  type        = number
  default     = 100
}

variable "artifacts_bucket_retention_days" {
  description = "Number of days to retain objects in the artifacts bucket"
  type        = number
  default     = 90
}

# -----------------------------------------------------------------------------
# Security
# -----------------------------------------------------------------------------

variable "rate_limit_threshold" {
  description = "Number of requests per interval before rate limiting kicks in"
  type        = number
  default     = 1000
}

variable "rate_limit_interval_sec" {
  description = "Interval in seconds for rate limiting"
  type        = number
  default     = 60
}

variable "secret_ids" {
  description = "List of secret IDs to create in Secret Manager"
  type        = list(string)
  default = [
    "sevaforge-db-password",
    "sevaforge-api-key",
    "sevaforge-jwt-secret",
    "sevaforge-webhook-secret",
    "sevaforge-encryption-key",
  ]
}
