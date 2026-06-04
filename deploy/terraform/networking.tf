###############################################################################
# SevaForge - Global HTTPS Load Balancer, Cloud CDN, Cloud Armor, SSL
###############################################################################

# -----------------------------------------------------------------------------
# Global Static IP
# -----------------------------------------------------------------------------

resource "google_compute_global_address" "lb" {
  name        = "${var.project_name}-${var.environment}-lb-ip"
  project     = var.project_id
  description = "Global static IP for SevaForge HTTPS load balancer"
}

# -----------------------------------------------------------------------------
# Managed SSL Certificate
# -----------------------------------------------------------------------------

resource "google_compute_managed_ssl_certificate" "main" {
  name    = "${var.project_name}-${var.environment}-ssl-cert"
  project = var.project_id

  managed {
    domains = [
      var.domain_name,
      "www.${var.domain_name}",
      "api.${var.domain_name}",
    ]
  }
}

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------

resource "google_compute_health_check" "http" {
  name                = "${var.project_name}-${var.environment}-http-health-check"
  project             = var.project_id
  description         = "Health check for SevaForge backend service"
  check_interval_sec  = 10
  timeout_sec         = 5
  healthy_threshold   = 2
  unhealthy_threshold = 3

  http_health_check {
    port         = 80
    request_path = "/healthz"
  }

  log_config {
    enable = true
  }
}

# -----------------------------------------------------------------------------
# Backend Service with Cloud CDN
# -----------------------------------------------------------------------------

resource "google_compute_backend_service" "main" {
  name                  = "${var.project_name}-${var.environment}-backend"
  project               = var.project_id
  protocol              = "HTTP"
  port_name             = "http"
  timeout_sec           = 30
  description           = "Primary backend service for SevaForge application"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  health_checks         = [google_compute_health_check.http.id]
  security_policy       = google_compute_security_policy.waf.id

  enable_cdn = true

  cdn_policy {
    cache_mode                   = "CACHE_ALL_STATIC"
    default_ttl                  = 3600
    max_ttl                      = 86400
    client_ttl                   = 3600
    negative_caching             = true
    signed_url_cache_max_age_sec = 0
    serve_while_stale            = 86400

    cache_key_policy {
      include_host         = true
      include_protocol     = true
      include_query_string = false
    }

    negative_caching_policy {
      code = 404
      ttl  = 60
    }

    negative_caching_policy {
      code = 502
      ttl  = 10
    }
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }

  # Backend will be configured to point to GKE NEGs via Kubernetes Ingress
  # This is a placeholder; the actual backend group is managed by GKE ingress controller
}

# -----------------------------------------------------------------------------
# URL Map
# -----------------------------------------------------------------------------

resource "google_compute_url_map" "main" {
  name            = "${var.project_name}-${var.environment}-url-map"
  project         = var.project_id
  default_service = google_compute_backend_service.main.id
  description     = "URL map for SevaForge HTTPS load balancer"
}

# HTTPS redirect URL map
resource "google_compute_url_map" "http_redirect" {
  name    = "${var.project_name}-${var.environment}-http-redirect"
  project = var.project_id

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# -----------------------------------------------------------------------------
# HTTPS Target Proxy
# -----------------------------------------------------------------------------

resource "google_compute_target_https_proxy" "main" {
  name             = "${var.project_name}-${var.environment}-https-proxy"
  project          = var.project_id
  url_map          = google_compute_url_map.main.id
  ssl_certificates = [google_compute_managed_ssl_certificate.main.id]

  ssl_policy = google_compute_ssl_policy.main.id
}

# HTTP Target Proxy (for redirect)
resource "google_compute_target_http_proxy" "redirect" {
  name    = "${var.project_name}-${var.environment}-http-redirect-proxy"
  project = var.project_id
  url_map = google_compute_url_map.http_redirect.id
}

# -----------------------------------------------------------------------------
# SSL Policy
# -----------------------------------------------------------------------------

resource "google_compute_ssl_policy" "main" {
  name            = "${var.project_name}-${var.environment}-ssl-policy"
  project         = var.project_id
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

# -----------------------------------------------------------------------------
# Forwarding Rules
# -----------------------------------------------------------------------------

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${var.project_name}-${var.environment}-https-rule"
  project               = var.project_id
  ip_address            = google_compute_global_address.lb.address
  ip_protocol           = "TCP"
  port_range            = "443"
  target                = google_compute_target_https_proxy.main.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  description           = "HTTPS forwarding rule for SevaForge"

  labels = local.common_labels
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  name                  = "${var.project_name}-${var.environment}-http-redirect-rule"
  project               = var.project_id
  ip_address            = google_compute_global_address.lb.address
  ip_protocol           = "TCP"
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  description           = "HTTP to HTTPS redirect for SevaForge"

  labels = local.common_labels
}

# -----------------------------------------------------------------------------
# Cloud Armor WAF Policy
# -----------------------------------------------------------------------------

resource "google_compute_security_policy" "waf" {
  name        = "${var.project_name}-${var.environment}-waf-policy"
  project     = var.project_id
  description = "Cloud Armor WAF policy for SevaForge with OWASP rules and rate limiting"

  # Default rule: allow
  rule {
    action   = "allow"
    priority = 2147483647
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow rule"
  }

  # Rate limiting
  rule {
    action   = "throttle"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = var.rate_limit_threshold
        interval_sec = var.rate_limit_interval_sec
      }
    }
    description = "Rate limiting: ${var.rate_limit_threshold} requests per ${var.rate_limit_interval_sec}s"
  }

  # OWASP ModSecurity CRS - SQL Injection
  rule {
    action   = "deny(403)"
    priority = 2000
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "OWASP CRS: Block SQL injection attacks"
  }

  # OWASP ModSecurity CRS - Cross-Site Scripting
  rule {
    action   = "deny(403)"
    priority = 2001
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "OWASP CRS: Block XSS attacks"
  }

  # OWASP ModSecurity CRS - Local File Inclusion
  rule {
    action   = "deny(403)"
    priority = 2002
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "OWASP CRS: Block local file inclusion attacks"
  }

  # OWASP ModSecurity CRS - Remote File Inclusion
  rule {
    action   = "deny(403)"
    priority = 2003
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rfi-v33-stable')"
      }
    }
    description = "OWASP CRS: Block remote file inclusion attacks"
  }

  # OWASP ModSecurity CRS - Remote Code Execution
  rule {
    action   = "deny(403)"
    priority = 2004
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('rce-v33-stable')"
      }
    }
    description = "OWASP CRS: Block remote code execution attacks"
  }

  # OWASP ModSecurity CRS - Scanner Detection
  rule {
    action   = "deny(403)"
    priority = 2005
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('scannerdetection-v33-stable')"
      }
    }
    description = "OWASP CRS: Block scanner/crawler probes"
  }

  # OWASP ModSecurity CRS - Protocol Attack
  rule {
    action   = "deny(403)"
    priority = 2006
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('protocolattack-v33-stable')"
      }
    }
    description = "OWASP CRS: Block protocol-based attacks"
  }

  # Block known bad IPs (placeholder for managed threat intelligence)
  rule {
    action   = "deny(403)"
    priority = 500
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('cve-canary')"
      }
    }
    description = "Block CVE-based exploit attempts"
  }

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }
}
