# =============================================================================
# Sevaforge — OCI Always Free Terraform
# Provisions: VCN · Internet Gateway · Subnets · OKE BASIC_CLUSTER
#             ARM Node Pool (2× VM.Standard.A1.Flex)
# =============================================================================

terraform {
  required_version = ">= 1.3"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.47.0"
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

locals {
  app      = "sevaforge"
  vcn_cidr = "10.0.0.0/16"
  common_tags = {
    project   = local.app
    managedBy = "terraform"
  }
}

# =============================================================================
# Data sources
# =============================================================================

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

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
# VCN
# =============================================================================

resource "oci_core_vcn" "sevaforge" {
  compartment_id = var.compartment_id
  display_name   = "${local.app}-vcn"
  cidr_blocks    = [local.vcn_cidr]
  dns_label      = local.app
  freeform_tags  = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-igw"
  enabled        = true
  freeform_tags  = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-public-rt"
  freeform_tags  = local.common_tags
  route_rules {
    network_entity_id = oci_core_internet_gateway.igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
  lifecycle { prevent_destroy = true }
}

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.sevaforge.id
  display_name   = "${local.app}-public-sl"
  freeform_tags  = local.common_tags

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 80
      max = 80
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 443
      max = 443
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8000
      max = 8000
    }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 6443
      max = 6443
    }
  }
  ingress_security_rules {
    protocol = "all"
    source   = local.vcn_cidr
  }
  lifecycle { prevent_destroy = true }
}

resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.sevaforge.id
  display_name      = "${local.app}-public-subnet"
  cidr_block        = "10.0.1.0/24"
  dns_label         = "public"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]
  freeform_tags     = local.common_tags
  lifecycle { prevent_destroy = true }
}

resource "oci_core_subnet" "workers" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.sevaforge.id
  display_name      = "${local.app}-workers-subnet"
  cidr_block        = "10.0.2.0/24"
  dns_label         = "workers"
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]
  freeform_tags     = local.common_tags
  lifecycle { prevent_destroy = true }
}

# =============================================================================
# OKE Cluster — BASIC_CLUSTER (free control plane)
# =============================================================================

resource "oci_containerengine_cluster" "sevaforge" {
  compartment_id     = var.compartment_id
  vcn_id             = oci_core_vcn.sevaforge.id
  name               = "${local.app}-cluster"
  kubernetes_version = var.kubernetes_version
  type               = "BASIC_CLUSTER"

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
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [kubernetes_version]
  }
}

# =============================================================================
# ARM Node Pool — spread across all ADs for capacity
# Set enable_arm_pool = false when IAD is out of A1 capacity
# =============================================================================

resource "oci_containerengine_node_pool" "arm" {
  count = var.enable_arm_pool ? 1 : 0

  cluster_id         = oci_containerengine_cluster.sevaforge.id
  compartment_id     = var.compartment_id
  name               = "${local.app}-arm-pool"
  kubernetes_version = var.kubernetes_version

  node_config_details {
    size = var.node_pool_size

    dynamic "placement_configs" {
      for_each = data.oci_identity_availability_domains.ads.availability_domains
      content {
        availability_domain = placement_configs.value.name
        subnet_id           = oci_core_subnet.workers.id
      }
    }
    freeform_tags = local.common_tags
  }

  node_shape = "VM.Standard.A1.Flex"
  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gbs
  }

  node_source_details {
    source_type             = "IMAGE"
    image_id                = data.oci_core_images.ol8_aarch64.images[0].id
    boot_volume_size_in_gbs = 50
  }

  initial_node_labels {
    key   = "role"
    value = "worker"
  }
  freeform_tags = local.common_tags

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [node_source_details, kubernetes_version]
  }
}

# =============================================================================
# AMD Fallback Node Pool — use when ARM capacity is exhausted
# Set enable_amd_fallback = true to activate
# =============================================================================

data "oci_core_images" "ol8_x86" {
  count                    = var.enable_amd_fallback ? 1 : 0
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = "VM.Standard.E4.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

resource "oci_containerengine_node_pool" "amd_fallback" {
  count = var.enable_amd_fallback ? 1 : 0

  cluster_id         = oci_containerengine_cluster.sevaforge.id
  compartment_id     = var.compartment_id
  name               = "${local.app}-amd-fallback-pool"
  kubernetes_version = var.kubernetes_version

  node_config_details {
    size = var.node_pool_size

    dynamic "placement_configs" {
      for_each = data.oci_identity_availability_domains.ads.availability_domains
      content {
        availability_domain = placement_configs.value.name
        subnet_id           = oci_core_subnet.workers.id
      }
    }
    freeform_tags = local.common_tags
  }

  node_shape = "VM.Standard.E4.Flex"
  node_shape_config {
    ocpus         = 1
    memory_in_gbs = 8
  }

  node_source_details {
    source_type             = "IMAGE"
    image_id                = data.oci_core_images.ol8_x86[0].images[0].id
    boot_volume_size_in_gbs = 50
  }

  initial_node_labels {
    key   = "role"
    value = "worker"
  }
  freeform_tags = local.common_tags

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [node_source_details, kubernetes_version]
  }
}
