# =============================================================================
# Sevaforge — OCI Always Free Terraform
# Provisions: VCN · Internet Gateway · Subnets · OKE (BASIC_CLUSTER)
#             ARM Node Pool (2× A1.Flex) · OCIR
# All resources fit within OCI Always Free tier limits.
# =============================================================================

terraform {
  required_version = ">= 1.3"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# =============================================================================
# Locals
# =============================================================================

locals {
  app      = "sevaforge"
  vcn_cidr = "10.0.0.0/16"

  common_tags = {
    project   = local.app
    managedBy = "terraform"
  }
}

# =============================================================================
# VCN
# =============================================================================

resource "oci_core_vcn" "sevaforge" {
  compartment_id = var.compartment_id
  display_name   = "${local.app}-vcn"
  cidr_blocks    = [local.vcn_cidr]
  dns_label      = local.app

  freeform_tags = local.common_tags
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-igw"
  enabled        = true

  freeform_tags = local.common_tags
}

# Route table: public traffic → Internet Gateway
resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-public-rt"

  route_rules {
    network_entity_id = oci_core_internet_gateway.igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }

  freeform_tags = local.common_tags
}

# Security list — allow inbound HTTP/HTTPS + SSH, all outbound
resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-public-sl"

  # Allow all outbound
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }

  # HTTP
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 80; max = 80 }
  }

  # HTTPS
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 443; max = 443 }
  }

  # App port (Sevaforge API)
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 8000; max = 8000 }
  }

  # Kubernetes API
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 6443; max = 6443 }
  }

  # Inter-node communication (within VCN)
  ingress_security_rules {
    protocol = "all"
    source   = local.vcn_cidr
  }

  freeform_tags = local.common_tags
}

# Public subnet — Load Balancer + worker nodes (Always Free stays simple)
resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.sevaforge.id
  display_name      = "${local.app}-public-subnet"
  cidr_block        = "10.0.1.0/24"
  dns_label         = "public"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]

  freeform_tags = local.common_tags
}

# Private subnet — OKE worker nodes (NAT not needed for Always Free; use public subnet)
resource "oci_core_subnet" "workers" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.sevaforge.id
  display_name      = "${local.app}-workers-subnet"
  cidr_block        = "10.0.2.0/24"
  dns_label         = "workers"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]

  freeform_tags = local.common_tags
}

# =============================================================================
# OKE Cluster — BASIC_CLUSTER (free control plane)
# =============================================================================

resource "oci_containerengine_cluster" "sevaforge" {
  compartment_id     = var.compartment_id
  vcn_id             = oci_core_vcn.sevaforge.id
  name               = "${local.app}-cluster"
  kubernetes_version = var.kubernetes_version
  type               = "BASIC_CLUSTER" # Always Free — no management fee

  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = oci_core_subnet.public.id
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.public.id]

    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }

  freeform_tags = local.common_tags
}

# =============================================================================
# Data source — auto-discover latest Oracle Linux 8 aarch64 image
# No need to pass image OCID manually — Terraform resolves it at plan time
# =============================================================================

data "oci_core_images" "ol8_aarch64" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"

  filter {
    name   = "display_name"
    values = [".*aarch64.*"]
    regex  = true
  }
}

# =============================================================================
# ARM Node Pool — 2× VM.Standard.A1.Flex (2 oCPU + 12 GB each)
# Total: 4 oCPU + 24 GB — exactly at Always Free A1 limit
# =============================================================================

resource "oci_containerengine_node_pool" "arm" {
  cluster_id         = oci_containerengine_cluster.sevaforge.id
  compartment_id     = var.compartment_id
  name               = "${local.app}-arm-pool"
  kubernetes_version = var.kubernetes_version

  node_config_details {
    size = 2 # 2 nodes

    placement_configs {
      availability_domain = var.availability_domain
      subnet_id           = oci_core_subnet.workers.id
    }

    freeform_tags = local.common_tags
  }

  node_shape = "VM.Standard.A1.Flex"

  node_shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  # Oracle Linux 8 aarch64 — resolved automatically by data source above
  node_source_details {
    source_type             = "IMAGE"
    image_id                = data.oci_core_images.ol8_aarch64.images[0].id
    boot_volume_size_in_gbs = 50
  }

  # Pass kubeconfig bootstrap token
  initial_node_labels {
    key   = "role"
    value = "worker"
  }

  freeform_tags = local.common_tags
}
