"""
InfraArchitectPersona — owns cloud network topology (VPC, subnets, firewall).

Separate from ClusterBuilderPersona: this persona produces the *foundation*
that any compute platform sits on. ClusterBuilder adds the GKE/EKS resources
to the same Terraform module.

Artifacts:
  forgeflow/infrastructure/{cloud}/network.tf
  forgeflow/infrastructure/{cloud}/variables.tf
  forgeflow/infrastructure/{cloud}/providers.tf
  forgeflow/infrastructure/{cloud}/backend.tf
"""
from typing import Any, Dict, List

from .base_persona import BasePersona


class InfraArchitectPersona(BasePersona):
    """Produces cloud-agnostic infrastructure foundations (network, backend, providers)."""

    persona_name = "infra-architect"
    owned_paths = ["forgeflow/infrastructure/"]

    def __init__(self):
        super().__init__(
            name="infra_architect_persona",
            description="Designs the cloud network + Terraform scaffolding",
        )

    def produce_artifacts(self, overwrite=True):
        cloud = self.intent["cloud"]["provider"]
        app = self.intent["app"]["name"]

        base_dir = f"forgeflow/infrastructure/{cloud}"

        if cloud == "gcp":
            actions = self._gcp_artifacts(base_dir, app, overwrite)
        elif cloud == "aws":
            actions = self._aws_artifacts(base_dir, app, overwrite)
        elif cloud == "azure":
            actions = self._azure_artifacts(base_dir, app, overwrite)
        elif cloud == "oci":
            actions = self._oci_artifacts(base_dir, app, overwrite)
        else:
            return [], [f"No infra template for cloud '{cloud}'"], None

        findings = [
            f"Generated {cloud.upper()} network topology for app '{app}'",
            f"State backend: remote (cloud-native object storage)",
        ]
        return actions, findings, {"cloud": cloud, "module_dir": base_dir}

    # =======================================================================
    # GCP
    # =======================================================================

    def _gcp_artifacts(self, base_dir: str, app: str, overwrite: bool) -> List[Dict[str, Any]]:
        providers_tf = f'''terraform {{
  required_version = ">= 1.3"
  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = ">= 5.0"
    }}
  }}
}}

provider "google" {{
  project = var.project_id
  region  = var.region
}}
'''

        backend_tf = f'''terraform {{
  backend "gcs" {{
    bucket = "{app}-tfstate"
    prefix = "gcp"
  }}
}}
'''

        variables_tf = '''variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}
'''

        network_tf = f'''locals {{
  app = "{app}"
}}

resource "google_compute_network" "main" {{
  name                    = "${{local.app}}-vpc"
  auto_create_subnetworks = false
}}

resource "google_compute_subnetwork" "main" {{
  name          = "${{local.app}}-subnet"
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.main.id

  secondary_ip_range {{
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/14"
  }}

  secondary_ip_range {{
    range_name    = "services"
    ip_cidr_range = "10.24.0.0/20"
  }}
}}

resource "google_compute_firewall" "allow_internal" {{
  name      = "${{local.app}}-allow-internal"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000
  source_ranges = ["10.10.0.0/20", "10.20.0.0/14", "10.24.0.0/20"]

  allow {{
    protocol = "tcp"
  }}
  allow {{
    protocol = "udp"
  }}
  allow {{
    protocol = "icmp"
  }}
}}

resource "google_compute_firewall" "allow_health_checks" {{
  name      = "${{local.app}}-allow-health-checks"
  network   = google_compute_network.main.name
  direction = "INGRESS"
  priority  = 1000
  source_ranges = ["35.191.0.0/16", "130.211.0.0/22"]

  allow {{
    protocol = "tcp"
  }}
}}

output "network_id" {{
  value = google_compute_network.main.id
}}

output "network_name" {{
  value = google_compute_network.main.name
}}

output "subnet_name" {{
  value = google_compute_subnetwork.main.name
}}
'''

        return [
            self.write_file(f"{base_dir}/providers.tf", providers_tf, overwrite),
            self.write_file(f"{base_dir}/backend.tf", backend_tf, overwrite),
            self.write_file(f"{base_dir}/variables.tf", variables_tf, overwrite),
            self.write_file(f"{base_dir}/network.tf", network_tf, overwrite),
        ]

    # =======================================================================
    # AWS
    # =======================================================================

    def _aws_artifacts(self, base_dir: str, app: str, overwrite: bool) -> List[Dict[str, Any]]:
        providers_tf = '''terraform {
  required_version = ">= 1.3"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
'''
        backend_tf = f'''terraform {{
  backend "s3" {{
    bucket = "{app}-tfstate"
    key    = "aws/terraform.tfstate"
    region = "us-east-1"
  }}
}}
'''
        variables_tf = '''variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
'''
        network_tf = f'''locals {{
  app = "{app}"
}}

resource "aws_vpc" "main" {{
  cidr_block           = "10.10.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {{ Name = "${{local.app}}-vpc" }}
}}

resource "aws_subnet" "public" {{
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.10.${{count.index}}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = {{ Name = "${{local.app}}-public-${{count.index}}" }}
}}

data "aws_availability_zones" "available" {{
  state = "available"
}}

resource "aws_internet_gateway" "main" {{
  vpc_id = aws_vpc.main.id
  tags = {{ Name = "${{local.app}}-igw" }}
}}

resource "aws_route_table" "public" {{
  vpc_id = aws_vpc.main.id

  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }}
  tags = {{ Name = "${{local.app}}-public-rt" }}
}}

resource "aws_route_table_association" "public" {{
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}}

output "vpc_id" {{
  value = aws_vpc.main.id
}}

output "subnet_ids" {{
  value = aws_subnet.public[*].id
}}
'''

        return [
            self.write_file(f"{base_dir}/providers.tf", providers_tf, overwrite),
            self.write_file(f"{base_dir}/backend.tf", backend_tf, overwrite),
            self.write_file(f"{base_dir}/variables.tf", variables_tf, overwrite),
            self.write_file(f"{base_dir}/network.tf", network_tf, overwrite),
        ]

    # =======================================================================
    # Azure / OCI — minimal stubs so the persona never silently skips
    # =======================================================================

    def _azure_artifacts(self, base_dir: str, app: str, overwrite: bool) -> List[Dict[str, Any]]:
        stub = f'# Azure infra for {app} — TODO: expand when Azure is targeted\n'
        return [self.write_file(f"{base_dir}/README.md",
                                f"Azure network module for {app} — not yet implemented.\n",
                                overwrite)]

    def _oci_artifacts(self, base_dir: str, app: str, overwrite: bool) -> List[Dict[str, Any]]:
        # OCI module already exists in the repo; leave as-is and emit a marker
        return [self.write_file(
            f"{base_dir}/PERSONA_NOTE.md",
            f"InfraArchitectPersona: existing OCI module preserved. "
            f"To regenerate from persona templates, delete this file and re-run deploy-design.\n",
            overwrite=False,  # do NOT overwrite existing OCI module
        )]
