###############################################################################
# SevaForge - Cloud DNS
###############################################################################

# -----------------------------------------------------------------------------
# Managed DNS Zone
# -----------------------------------------------------------------------------

resource "google_dns_managed_zone" "main" {
  name        = var.dns_managed_zone_name
  project     = var.project_id
  dns_name    = "${var.domain_name}."
  description = "DNS zone for SevaForge ${var.environment}"
  visibility  = "public"

  dnssec_config {
    state = "on"
  }

  labels = local.common_labels
}

# -----------------------------------------------------------------------------
# DNS Records
# -----------------------------------------------------------------------------

# Root domain -> Load Balancer
resource "google_dns_record_set" "root" {
  name         = "${var.domain_name}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.main.name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.lb.address]
}

# www -> Load Balancer
resource "google_dns_record_set" "www" {
  name         = "www.${var.domain_name}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.main.name
  type         = "CNAME"
  ttl          = 300
  rrdatas      = ["${var.domain_name}."]
}

# api -> Load Balancer
resource "google_dns_record_set" "api" {
  name         = "api.${var.domain_name}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.main.name
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.lb.address]
}

# CAA record - restrict certificate issuance
resource "google_dns_record_set" "caa" {
  name         = "${var.domain_name}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.main.name
  type         = "CAA"
  ttl          = 3600
  rrdatas = [
    "0 issue \"pki.goog\"",
    "0 issue \"letsencrypt.org\"",
    "0 iodef \"mailto:security@${var.domain_name}\"",
  ]
}

# SPF record for email authentication
resource "google_dns_record_set" "spf" {
  name         = "${var.domain_name}."
  project      = var.project_id
  managed_zone = google_dns_managed_zone.main.name
  type         = "TXT"
  ttl          = 3600
  rrdatas = [
    "\"v=spf1 include:_spf.google.com ~all\"",
  ]
}
