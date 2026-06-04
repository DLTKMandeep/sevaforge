###############################################################################
# SevaForge - Cloud SQL PostgreSQL (HA + Read Replica)
###############################################################################

# -----------------------------------------------------------------------------
# Random password for the database user
# -----------------------------------------------------------------------------

resource "random_password" "db_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}|:?,."
}

# -----------------------------------------------------------------------------
# Primary Cloud SQL Instance
# -----------------------------------------------------------------------------

resource "google_sql_database_instance" "primary" {
  name                = "${var.project_name}-${var.environment}-pg-${random_id.suffix.hex}"
  project             = var.project_id
  region              = var.region
  database_version    = var.db_postgres_version
  deletion_protection = true

  settings {
    tier              = var.db_tier
    availability_type = var.db_availability_type
    disk_size         = var.db_disk_size_gb
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    # Private network configuration
    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.main.id
      enable_private_path_for_google_cloud_services = true
    }

    # Backup configuration
    backup_configuration {
      enabled                        = var.db_backup_enabled
      start_time                     = var.db_backup_start_time
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 30
        retention_unit   = "COUNT"
      }
    }

    # Maintenance window
    maintenance_window {
      day          = var.db_maintenance_day
      hour         = var.db_maintenance_hour
      update_track = "stable"
    }

    # Database flags for production hardening
    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    database_flags {
      name  = "log_lock_waits"
      value = "on"
    }

    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    insights_config {
      query_insights_enabled  = true
      query_plans_per_minute  = 5
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    user_labels = local.common_labels
  }

  depends_on = [
    google_service_networking_connection.private_services,
    google_project_service.apis["sqladmin.googleapis.com"],
  ]
}

# -----------------------------------------------------------------------------
# Read Replica
# -----------------------------------------------------------------------------

resource "google_sql_database_instance" "read_replica" {
  name                 = "${var.project_name}-${var.environment}-pg-replica-${random_id.suffix.hex}"
  project              = var.project_id
  region               = var.region
  database_version     = var.db_postgres_version
  master_instance_name = google_sql_database_instance.primary.name
  deletion_protection  = true

  replica_configuration {
    failover_target = false
  }

  settings {
    tier            = var.db_tier
    disk_size       = var.db_disk_size_gb
    disk_type       = "PD_SSD"
    disk_autoresize = true

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.main.id
      enable_private_path_for_google_cloud_services = true
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }

    insights_config {
      query_insights_enabled  = true
      query_plans_per_minute  = 5
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    user_labels = merge(local.common_labels, {
      role = "read-replica"
    })
  }

  depends_on = [google_sql_database_instance.primary]
}

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

resource "google_sql_database" "main" {
  name     = var.db_name
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
}

# -----------------------------------------------------------------------------
# Database User
# -----------------------------------------------------------------------------

resource "google_sql_user" "app" {
  name     = var.db_user
  project  = var.project_id
  instance = google_sql_database_instance.primary.name
  password = random_password.db_password.result

  deletion_policy = "ABANDON"
}

# -----------------------------------------------------------------------------
# Store the generated password in Secret Manager
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.secrets["sevaforge-db-password"].id
  secret_data = random_password.db_password.result

  depends_on = [google_secret_manager_secret.secrets]
}
