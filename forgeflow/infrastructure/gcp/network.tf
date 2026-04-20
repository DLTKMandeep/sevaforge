locals {
  app = "sevaforge-unified"
}

resource "google_compute_network" "main" {
  name                    = "${local.app}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "${local.app}-subnet"
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.main.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/14"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.24.0.0/20"
  }
}

resource "google_compute_firewall" "allow_internal" {
  name      = "${local.app}-allow-internal"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000
  source_ranges = ["10.10.0.0/20", "10.20.0.0/14", "10.24.0.0/20"]

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }
}

resource "google_compute_firewall" "allow_health_checks" {
  name      = "${local.app}-allow-health-checks"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]

  allow {
    protocol = "tcp"
  }
}

output "network_id" {
  value = google_compute_network.main.id
}

output "network_name" {
  value = google_compute_network.main.name
}

output "subnet_name" {
  value = google_compute_subnetwork.main.name
}
