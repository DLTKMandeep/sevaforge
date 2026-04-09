# =============================================================================
# Sevaforge — GCP Free Tier Terraform
# Provisions: VPC · GKE Autopilot Cluster
# GKE Autopilot control plane is free — you pay only for pod resources
# With $300 free credit, worker pods run for months at zero cost
# =============================================================================

terraform {
  required_version = ">= 1.3"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
  backend "local" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  app = "sevaforge"
  common_labels = {
    project    = local.app
    managed-by = "terraform"
  }
}

# =============================================================================
# VPC Network
# =============================================================================

resource "google_compute_network" "sevaforge" {
  name                    = "${local.app}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "sevaforge" {
  name          = "${local.app}-subnet"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.sevaforge.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.4.0.0/14"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.8.0.0/20"
  }
}

# =============================================================================
# Firewall — allow health checks + internal traffic
# =============================================================================

resource "google_compute_firewall" "allow_internal" {
  name    = "${local.app}-allow-internal"
  network = google_compute_network.sevaforge.name

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.0.0.0/8"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${local.app}-allow-health-checks"
  network = google_compute_network.sevaforge.name

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8000", "6443"]
  }

  # Google health check IP ranges
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]
}

# =============================================================================
# GKE Autopilot — free control plane, pay only for pod resources
# =============================================================================

resource "google_container_cluster" "sevaforge" {
  name     = "${local.app}-cluster"
  location = var.region

  # Autopilot mode — Google manages nodes, you pay per pod resource
  enable_autopilot = true

  network    = google_compute_network.sevaforge.name
  subnetwork = google_compute_subnetwork.sevaforge.name

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Release channel for auto-upgrades
  release_channel {
    channel = "REGULAR"
  }

  resource_labels = local.common_labels

  # Deletion protection — set to false for easy teardown
  deletion_protection = false

  lifecycle {
    ignore_changes = [resource_labels]
  }
}
