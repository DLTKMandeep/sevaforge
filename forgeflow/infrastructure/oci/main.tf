# =============================================================================
# Sevaforge — OCI Always Free Terraform
# Provisions: VCN · Internet Gateway · Subnets · Security List
#             2× VM.Standard.A1.Flex (ARM) running Docker Compose
#
# NO OKE — VM-based deployment avoids cluster quota issues entirely.
# Total: 4 oCPU + 24 GB RAM — exactly at Always Free A1 limit.
# =============================================================================

terraform {
  required_version = ">= 1.3"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 5.47.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
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

  # cloud-init: install Docker, pull image, start Sevaforge on boot
  cloud_init = <<-CLOUDINIT
    #cloud-config
    package_update: true
    packages:
      - docker
      - docker-compose-plugin
    runcmd:
      - systemctl enable docker
      - systemctl start docker
      - mkdir -p /opt/sevaforge
      - |
        cat > /opt/sevaforge/docker-compose.yml <<'EOF'
        version: "3.9"
        services:
          sevaforge:
            image: ${var.ocir_image}
            restart: always
            ports:
              - "8000:8000"
            environment:
              - ENV=production
        EOF
      - docker compose -f /opt/sevaforge/docker-compose.yml up -d
  CLOUDINIT
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
    tcp_options { min = 22; max = 22 }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 80; max = 80 }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 443; max = 443 }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 8000; max = 8000 }
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

# =============================================================================
# SSH key pair (generated once, stored as GitHub secret by workflow)
# =============================================================================

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# =============================================================================
# ARM VMs — 2× VM.Standard.A1.Flex (2 oCPU + 12 GB each)
# Spread across ADs for availability
# =============================================================================

resource "oci_core_instance" "sevaforge" {
  count = 2

  compartment_id      = var.compartment_id
  display_name        = "${local.app}-vm-${count.index + 1}"
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[count.index % length(data.oci_identity_availability_domains.ads.availability_domains)].name
  shape               = "VM.Standard.A1.Flex"
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = 2
    memory_in_gbs = 12
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ol8_aarch64.images[0].id
    boot_volume_size_in_gbs = 50
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    display_name     = "${local.app}-vnic-${count.index + 1}"
  }

  metadata = {
    ssh_authorized_keys = tls_private_key.ssh.public_key_openssh
    user_data           = base64encode(local.cloud_init)
  }

  lifecycle {
    prevent_destroy       = true
    ignore_changes        = [source_details, metadata]
  }
}

# =============================================================================
# Free Load Balancer — routes HTTP/8000 across both VMs
# =============================================================================

resource "oci_load_balancer_load_balancer" "sevaforge" {
  compartment_id = var.compartment_id
  display_name   = "${local.app}-lb"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.public.id]
  is_private     = false
  freeform_tags  = local.common_tags

  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 10
  }

  lifecycle { prevent_destroy = true }
}

resource "oci_load_balancer_backend_set" "sevaforge" {
  name             = "sevaforge-backend"
  load_balancer_id = oci_load_balancer_load_balancer.sevaforge.id
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol          = "HTTP"
    port              = 8000
    url_path          = "/health"
    return_code       = 200
    interval_ms       = 10000
    timeout_in_millis = 3000
    retries           = 3
  }
}

resource "oci_load_balancer_backend" "sevaforge" {
  count            = 2
  load_balancer_id = oci_load_balancer_load_balancer.sevaforge.id
  backendset_name  = oci_load_balancer_backend_set.sevaforge.name
  ip_address       = oci_core_instance.sevaforge[count.index].private_ip
  port             = 8000
  backup           = false
  drain            = false
  offline          = false
  weight           = 1
}

resource "oci_load_balancer_listener" "http" {
  load_balancer_id         = oci_load_balancer_load_balancer.sevaforge.id
  name                     = "http"
  default_backend_set_name = oci_load_balancer_backend_set.sevaforge.name
  port                     = 80
  protocol                 = "HTTP"
}
