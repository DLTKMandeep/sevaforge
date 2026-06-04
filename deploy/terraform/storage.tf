###############################################################################
# SevaForge - GCS Buckets & Persistent Disks
###############################################################################

# -----------------------------------------------------------------------------
# Artifacts Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "artifacts" {
  name          = "${var.project_name}-${var.environment}-artifacts-${random_id.suffix.hex}"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.artifacts_bucket_retention_days
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age        = 30
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3
    }
    action {
      type = "Delete"
    }
  }

  encryption {
    default_kms_key_name = null # Uses Google-managed encryption by default
  }

  labels = local.common_labels
}

# -----------------------------------------------------------------------------
# Terraform State Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "terraform_state" {
  name          = "${var.project_name}-${var.environment}-terraform-state"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }

  labels = merge(local.common_labels, {
    purpose = "terraform-state"
  })
}

# -----------------------------------------------------------------------------
# Persistent SSD Disk for Workers
# -----------------------------------------------------------------------------

resource "google_compute_disk" "worker_ssd" {
  name        = "${var.project_name}-${var.environment}-worker-ssd"
  project     = var.project_id
  zone        = data.google_compute_zones.available.names[0]
  type        = "pd-ssd"
  size        = var.worker_disk_size_gb
  description = "Persistent SSD for SevaForge worker processes"

  labels = merge(local.common_labels, {
    purpose = "worker-storage"
  })

  physical_block_size_bytes = 4096
}
