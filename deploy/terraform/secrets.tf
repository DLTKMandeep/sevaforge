###############################################################################
# SevaForge - Secret Manager
###############################################################################

# -----------------------------------------------------------------------------
# Secret Manager Secrets
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "secrets" {
  for_each = toset(var.secret_ids)

  secret_id = each.value
  project   = var.project_id

  replication {
    auto {}
  }

  labels = merge(local.common_labels, {
    secret_name = each.value
  })

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

# -----------------------------------------------------------------------------
# IAM bindings for secret access
# App and worker service accounts can read secrets
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret_iam_member" "app_access" {
  for_each = toset(var.secret_ids)

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app_workload.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_access" {
  for_each = toset(var.secret_ids)

  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker_workload.email}"
}
