###############################################################################
# SevaForge - IAM & Workload Identity
###############################################################################

# -----------------------------------------------------------------------------
# GKE Node Service Account
# -----------------------------------------------------------------------------

resource "google_service_account" "gke_nodes" {
  account_id   = "${var.project_name}-${var.environment}-gke-nodes"
  project      = var.project_id
  display_name = "SevaForge GKE Node Service Account"
  description  = "Service account for GKE node pools with minimal permissions"
}

resource "google_project_iam_member" "gke_nodes_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_resource_metadata_writer" {
  project = var.project_id
  role    = "roles/stackdriver.resourceMetadata.writer"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

resource "google_project_iam_member" "gke_nodes_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# -----------------------------------------------------------------------------
# Application Workload Identity Service Account
# -----------------------------------------------------------------------------

resource "google_service_account" "app_workload" {
  account_id   = "${var.project_name}-${var.environment}-app"
  project      = var.project_id
  display_name = "SevaForge App Workload Identity"
  description  = "Service account bound via Workload Identity to app pods"
}

# Allow GKE SA to impersonate this GSA
resource "google_service_account_iam_member" "app_workload_identity" {
  service_account_id = google_service_account.app_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[sevaforge/sevaforge-app]"
}

# App SA permissions
resource "google_project_iam_member" "app_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.app_workload.email}"
}

resource "google_project_iam_member" "app_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.app_workload.email}"
}

resource "google_storage_bucket_iam_member" "app_artifacts_admin" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.app_workload.email}"
}

resource "google_project_iam_member" "app_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.app_workload.email}"
}

# -----------------------------------------------------------------------------
# Worker Workload Identity Service Account
# -----------------------------------------------------------------------------

resource "google_service_account" "worker_workload" {
  account_id   = "${var.project_name}-${var.environment}-worker"
  project      = var.project_id
  display_name = "SevaForge Worker Workload Identity"
  description  = "Service account bound via Workload Identity to worker pods"
}

resource "google_service_account_iam_member" "worker_workload_identity" {
  service_account_id = google_service_account.worker_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[sevaforge/sevaforge-worker]"
}

# Worker SA permissions
resource "google_project_iam_member" "worker_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.worker_workload.email}"
}

resource "google_project_iam_member" "worker_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker_workload.email}"
}

resource "google_storage_bucket_iam_member" "worker_artifacts_admin" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.worker_workload.email}"
}

resource "google_project_iam_member" "worker_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.worker_workload.email}"
}

resource "google_project_iam_member" "worker_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.worker_workload.email}"
}

# -----------------------------------------------------------------------------
# CI/CD Service Account (for deployment pipelines)
# -----------------------------------------------------------------------------

resource "google_service_account" "cicd" {
  account_id   = "${var.project_name}-${var.environment}-cicd"
  project      = var.project_id
  display_name = "SevaForge CI/CD Pipeline"
  description  = "Service account for CI/CD deployment pipelines"
}

resource "google_project_iam_member" "cicd_container_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

resource "google_project_iam_member" "cicd_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}
