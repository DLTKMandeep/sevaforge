###############################################################################
# SevaForge - GKE Cluster & Node Pools
###############################################################################

# -----------------------------------------------------------------------------
# GKE Cluster
# -----------------------------------------------------------------------------

resource "google_container_cluster" "main" {
  provider = google-beta

  name        = local.cluster_name
  project     = var.project_id
  location    = var.region
  description = "SevaForge ${var.environment} GKE Standard cluster"

  # Use separately managed node pools
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = google_compute_network.main.id
  subnetwork = google_compute_subnetwork.app.id

  # Private cluster configuration
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_ipv4_cidr

    master_global_access_config {
      enabled = true
    }
  }

  # IP allocation for pods and services
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Master authorized networks
  dynamic "master_authorized_networks_config" {
    for_each = length(var.gke_master_authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.gke_master_authorized_networks
        content {
          cidr_block   = cidr_blocks.value.cidr_block
          display_name = cidr_blocks.value.display_name
        }
      }
    }
  }

  # Release channel
  release_channel {
    channel = var.gke_release_channel
  }

  # Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Network policy (Dataplane V2 includes built-in network policy)
  datapath_provider = "ADVANCED_DATAPATH"

  # Binary Authorization
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  # Cluster addons
  addons_config {
    http_load_balancing {
      disabled = false
    }

    horizontal_pod_autoscaling {
      disabled = false
    }

    network_policy_config {
      disabled = true # Dataplane V2 handles this
    }

    gce_persistent_disk_csi_driver_config {
      enabled = true
    }

    dns_cache_config {
      enabled = true
    }
  }

  # Maintenance window: Sunday 04:00-08:00 UTC
  maintenance_policy {
    recurring_window {
      start_time = "2024-01-07T04:00:00Z"
      end_time   = "2024-01-07T08:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }
  }

  # Logging and monitoring
  logging_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
      "WORKLOADS",
    ]
  }

  monitoring_config {
    enable_components = [
      "SYSTEM_COMPONENTS",
    ]

    managed_prometheus {
      enabled = true
    }
  }

  # Security configurations
  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  # Protect against accidental deletion
  deletion_protection = true

  resource_labels = local.common_labels

  depends_on = [
    google_project_service.apis["container.googleapis.com"],
    google_compute_router_nat.main,
  ]
}

# -----------------------------------------------------------------------------
# App Node Pool
# -----------------------------------------------------------------------------

resource "google_container_node_pool" "app" {
  name     = "app-pool"
  project  = var.project_id
  location = var.region
  cluster  = google_container_cluster.main.name

  initial_node_count = var.app_pool_min_nodes

  autoscaling {
    min_node_count = var.app_pool_min_nodes
    max_node_count = var.app_pool_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = var.app_pool_machine_type
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    image_type   = "COS_CONTAINERD"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    service_account = google_service_account.gke_nodes.email

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }

    labels = merge(local.common_labels, {
      node_pool = "app"
    })

    tags = ["gke-node", "app-node"]
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}

# -----------------------------------------------------------------------------
# Worker Node Pool
# -----------------------------------------------------------------------------

resource "google_container_node_pool" "worker" {
  name     = "worker-pool"
  project  = var.project_id
  location = var.region
  cluster  = google_container_cluster.main.name

  initial_node_count = var.worker_pool_min_nodes

  autoscaling {
    min_node_count = var.worker_pool_min_nodes
    max_node_count = var.worker_pool_max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
    strategy        = "SURGE"
  }

  node_config {
    machine_type = var.worker_pool_machine_type
    disk_size_gb = 100
    disk_type    = "pd-ssd"
    image_type   = "COS_CONTAINERD"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    service_account = google_service_account.gke_nodes.email

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }

    metadata = {
      disable-legacy-endpoints = "true"
    }

    labels = merge(local.common_labels, {
      node_pool = "worker"
    })

    tags = ["gke-node", "worker-node"]

    taint {
      key    = "workload"
      value  = "worker"
      effect = "NO_SCHEDULE"
    }
  }

  lifecycle {
    ignore_changes = [initial_node_count]
  }
}
