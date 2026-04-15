"""
ClusterBuilderPersona — adds the compute platform to the infra module.

Depends on InfraArchitectPersona (which creates the VPC). Writes a
cluster.tf alongside the network.tf into the same infra directory.
"""
from typing import Any, Dict, List

from .base_persona import BasePersona


class ClusterBuilderPersona(BasePersona):
    """Generates the compute platform terraform (GKE/EKS/AKS/OKE/etc.)."""

    persona_name = "cluster-builder"
    owned_paths = ["forgeflow/infrastructure/"]

    def __init__(self):
        super().__init__(
            name="cluster_builder_persona",
            description="Generates compute platform terraform (kubernetes/vm/serverless)",
        )

    def produce_artifacts(self, overwrite=True):
        cloud = self.intent["cloud"]["provider"]
        model = self.intent["compute"]["model"]
        flavour = self.intent["compute"]["flavour"]
        app = self.intent["app"]["name"]
        base_dir = f"forgeflow/infrastructure/{cloud}"

        if model == "kubernetes":
            if flavour == "gke-autopilot":
                actions = [self._gke_autopilot(base_dir, app, overwrite)]
            elif flavour == "eks":
                actions = [self._eks(base_dir, app, overwrite)]
            elif flavour == "aks":
                actions = [self._aks(base_dir, app, overwrite)]
            else:
                actions = [self.write_file(
                    f"{base_dir}/cluster.tf",
                    f'# TODO: cluster terraform for flavour {flavour} not yet templated\n',
                    overwrite,
                )]
        elif model == "serverless":
            actions = [self._serverless(base_dir, cloud, flavour, app, overwrite)]
        elif model == "vm":
            actions = [self._vm_group(base_dir, cloud, app, overwrite)]
        else:
            return [], [f"Unknown compute model: {model}"], None

        return actions, [f"Generated {model}/{flavour} cluster spec"], {"flavour": flavour}

    # ------------------------------------------------------------------ GKE

    def _gke_autopilot(self, base_dir: str, app: str, overwrite: bool) -> Dict[str, Any]:
        content = f'''# GKE Autopilot cluster — free control plane, pay only for running pods
resource "google_container_cluster" "main" {{
  name             = "${{local.app}}-cluster"
  location         = var.region
  enable_autopilot = true

  network    = google_compute_network.main.name
  subnetwork = google_compute_subnetwork.main.name

  ip_allocation_policy {{
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }}

  release_channel {{
    channel = "REGULAR"
  }}

  deletion_protection = false
}}

output "cluster_name" {{
  value = google_container_cluster.main.name
}}

output "cluster_endpoint" {{
  value     = google_container_cluster.main.endpoint
  sensitive = true
}}

output "cluster_ca_certificate" {{
  value     = google_container_cluster.main.master_auth[0].cluster_ca_certificate
  sensitive = true
}}

output "region" {{
  value = var.region
}}

output "project_id" {{
  value = var.project_id
}}
'''
        return self.write_file(f"{base_dir}/cluster.tf", content, overwrite)

    # ------------------------------------------------------------------ EKS

    def _eks(self, base_dir: str, app: str, overwrite: bool) -> Dict[str, Any]:
        content = f'''# EKS cluster — control plane + managed node group
module "eks" {{
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${{local.app}}-cluster"
  cluster_version = "1.29"

  cluster_endpoint_public_access = true

  vpc_id     = aws_vpc.main.id
  subnet_ids = aws_subnet.public[*].id

  eks_managed_node_groups = {{
    default = {{
      min_size     = 1
      max_size     = 3
      desired_size = 2
      instance_types = ["t3.medium"]
    }}
  }}
}}

output "cluster_name" {{
  value = module.eks.cluster_name
}}

output "cluster_endpoint" {{
  value     = module.eks.cluster_endpoint
  sensitive = true
}}

output "region" {{
  value = var.region
}}
'''
        return self.write_file(f"{base_dir}/cluster.tf", content, overwrite)

    # ------------------------------------------------------------------ AKS

    def _aks(self, base_dir: str, app: str, overwrite: bool) -> Dict[str, Any]:
        content = f'# AKS cluster — TODO: expand when Azure is targeted\n'
        return self.write_file(f"{base_dir}/cluster.tf", content, overwrite)

    # --------------------------------------------------------------- Serverless

    def _serverless(self, base_dir: str, cloud: str, flavour: str, app: str, overwrite: bool) -> Dict[str, Any]:
        if cloud == "gcp" and flavour == "cloud-run":
            content = f'''# Cloud Run service — scales to zero, billed per request
resource "google_cloud_run_v2_service" "main" {{
  name     = "${{local.app}}-service"
  location = var.region

  template {{
    containers {{
      image = var.image_uri
      ports {{ container_port = {self.intent["app"]["port"]} }}
    }}
    scaling {{
      min_instance_count = 0
      max_instance_count = {self.intent["compute"]["autoscale"]["max"]}
    }}
  }}

  traffic {{
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }}
}}

variable "image_uri" {{
  description = "Container image URI"
  type        = string
  default     = "gcr.io/cloudrun/hello"
}}

output "service_url" {{
  value = google_cloud_run_v2_service.main.uri
}}
'''
            return self.write_file(f"{base_dir}/cluster.tf", content, overwrite)
        return self.write_file(
            f"{base_dir}/cluster.tf",
            f"# Serverless {cloud}/{flavour} — TODO\n",
            overwrite,
        )

    # ------------------------------------------------------------------ VM

    def _vm_group(self, base_dir: str, cloud: str, app: str, overwrite: bool) -> Dict[str, Any]:
        content = f"# VM group for {cloud} — TODO: templated when VM mode is selected\n"
        return self.write_file(f"{base_dir}/cluster.tf", content, overwrite)
