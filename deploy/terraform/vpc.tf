###############################################################################
# SevaForge - VPC, Subnets, Firewall, Cloud NAT, Cloud Router
###############################################################################

# -----------------------------------------------------------------------------
# VPC Network
# -----------------------------------------------------------------------------

resource "google_compute_network" "main" {
  name                            = "${var.project_name}-${var.environment}-vpc"
  project                         = var.project_id
  auto_create_subnetworks         = false
  routing_mode                    = "REGIONAL"
  delete_default_routes_on_create = false
  description                     = "Primary VPC for SevaForge ${var.environment} environment"
}

# -----------------------------------------------------------------------------
# Subnets
# -----------------------------------------------------------------------------

resource "google_compute_subnetwork" "app" {
  name                     = "${var.project_name}-${var.environment}-app-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = var.subnet_app_cidr
  private_ip_google_access = true
  description              = "Application subnet for GKE nodes"

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.subnet_pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.subnet_services_secondary_cidr
  }

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_subnetwork" "services" {
  name                     = "${var.project_name}-${var.environment}-services-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.main.id
  ip_cidr_range            = var.subnet_services_cidr
  private_ip_google_access = true
  description              = "Services subnet for Cloud SQL, Redis, and managed services"
}

# -----------------------------------------------------------------------------
# Private Service Access (for Cloud SQL, Redis)
# -----------------------------------------------------------------------------

resource "google_compute_global_address" "private_services" {
  name          = "${var.project_name}-${var.environment}-private-svc-range"
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.main.id
  description   = "Private service connection IP range for managed services"
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]

  depends_on = [google_project_service.apis["servicenetworking.googleapis.com"]]
}

# -----------------------------------------------------------------------------
# Firewall Rules
# -----------------------------------------------------------------------------

resource "google_compute_firewall" "allow_internal" {
  name        = "${var.project_name}-${var.environment}-allow-internal"
  project     = var.project_id
  network     = google_compute_network.main.id
  description = "Allow internal traffic between all subnets"
  priority    = 1000
  direction   = "INGRESS"

  allow {
    protocol = "tcp"
  }

  allow {
    protocol = "udp"
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [
    var.subnet_app_cidr,
    var.subnet_services_cidr,
    var.subnet_pods_cidr,
    var.subnet_services_secondary_cidr,
  ]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "allow_health_checks" {
  name        = "${var.project_name}-${var.environment}-allow-health-checks"
  project     = var.project_id
  network     = google_compute_network.main.id
  description = "Allow GCP health check probes to reach backend instances"
  priority    = 900
  direction   = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["80", "443", "8080", "10256"]
  }

  # Google Cloud health check IP ranges
  source_ranges = [
    "35.191.0.0/16",
    "130.211.0.0/22",
  ]

  target_tags = ["gke-node"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "allow_iap_ssh" {
  name        = "${var.project_name}-${var.environment}-allow-iap-ssh"
  project     = var.project_id
  network     = google_compute_network.main.id
  description = "Allow SSH via Identity-Aware Proxy for secure node access"
  priority    = 1000
  direction   = "INGRESS"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  # IAP forwarding IP range
  source_ranges = ["35.235.240.0/20"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_firewall" "deny_all_ingress" {
  name        = "${var.project_name}-${var.environment}-deny-all-ingress"
  project     = var.project_id
  network     = google_compute_network.main.id
  description = "Default deny all ingress traffic"
  priority    = 65534
  direction   = "INGRESS"

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# -----------------------------------------------------------------------------
# Cloud Router
# -----------------------------------------------------------------------------

resource "google_compute_router" "main" {
  name        = "${var.project_name}-${var.environment}-router"
  project     = var.project_id
  region      = var.region
  network     = google_compute_network.main.id
  description = "Cloud Router for NAT gateway and dynamic routing"

  bgp {
    asn = 64514
  }
}

# -----------------------------------------------------------------------------
# Cloud NAT (egress for private GKE nodes)
# -----------------------------------------------------------------------------

resource "google_compute_router_nat" "main" {
  name                               = "${var.project_name}-${var.environment}-nat"
  project                            = var.project_id
  region                             = var.region
  router                             = google_compute_router.main.name
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }

  min_ports_per_vm                    = 2048
  max_ports_per_vm                    = 65536
  enable_dynamic_port_allocation      = true
  enable_endpoint_independent_mapping = false

  depends_on = [google_compute_router.main]
}
