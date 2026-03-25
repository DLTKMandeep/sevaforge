#!/usr/bin/env python3
"""
IAC Agent - Infrastructure as Code Generation
Generates Terraform, Pulumi, Docker configurations

Part of the specialized agent architecture:
- forgeflow iac <path> → iac_mcp → IACAgent

Supported clouds: aws | gcp | azure | oci
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent


# =============================================================================
# DOCKERFILE TEMPLATES BY LANGUAGE
# =============================================================================

DOCKERFILE_TEMPLATES = {
    'Python': '''FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \\
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',

    'JavaScript': '''FROM node:20-alpine AS base

WORKDIR /app

# Install dependencies only (for caching)
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# Build stage (if needed)
FROM base AS builder
RUN npm ci
COPY . .
RUN npm run build 2>/dev/null || true

# Production stage
FROM node:20-alpine AS production
WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001 -G nodejs

COPY --from=base /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist 2>/dev/null || true
COPY --from=builder /app/*.js ./
COPY --from=builder /app/package*.json ./

USER nodejs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

CMD ["node", "index.js"]
''',

    'TypeScript': '''FROM node:20-alpine AS base

WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM base AS builder
COPY . .
COPY tsconfig.json ./
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app

RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001 -G nodejs

COPY --from=base /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/package*.json ./

USER nodejs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/health || exit 1

CMD ["node", "dist/index.js"]
''',

    'Go': '''FROM golang:1.21-alpine AS builder

WORKDIR /app

RUN apk add --no-cache git ca-certificates tzdata

COPY go.mod go.sum* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /app/main .

FROM alpine:3.18 AS production
WORKDIR /app

RUN addgroup -g 1001 -S appgroup && \\
    adduser -S appuser -u 1001 -G appgroup

COPY --from=builder /app/main .
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

CMD ["./main"]
''',

    'Rust': '''FROM rust:1.73-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*

COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release && rm -rf src target/release/deps

COPY . .
RUN cargo build --release

FROM debian:bookworm-slim AS production
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    ca-certificates && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /app/target/release/app .

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["./app"]
''',
}


# =============================================================================
# ──────────────────────────── AWS TEMPLATES ───────────────────────────────────
# =============================================================================

TERRAFORM_MAIN_AWS = '''# =============================================================================
# ForgeFlow Generated Terraform — AWS
# Generated: {timestamp}
# =============================================================================

terraform {{
  required_version = ">= 1.0"

  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
    kubernetes = {{
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }}
    helm = {{
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }}
  }}

  # backend "s3" {{
  #   bucket         = "{app_name}-terraform-state"
  #   key            = "infrastructure/terraform.tfstate"
  #   region         = var.aws_region
  #   encrypt        = true
  #   dynamodb_table = "{app_name}-terraform-locks"
  # }}
}}

provider "aws" {{
  region = var.aws_region

  default_tags {{
    tags = {{
      Project     = var.app_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Generator   = "ForgeFlow"
    }}
  }}
}}

provider "kubernetes" {{
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)

  exec {{
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }}
}}

provider "helm" {{
  kubernetes {{
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)

    exec {{
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }}
  }}
}}

locals {{
  name_prefix = "${{var.app_name}}-${{var.environment}}"
}}

module "vpc" {{
  source = "./modules/network"

  app_name        = var.app_name
  environment     = var.environment
  vpc_cidr        = var.vpc_cidr
  azs             = var.availability_zones
  private_subnets = var.private_subnet_cidrs
  public_subnets  = var.public_subnet_cidrs
}}

module "eks" {{
  source = "./modules/cluster"

  app_name            = var.app_name
  environment         = var.environment
  cluster_version     = var.kubernetes_version
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  node_instance_types = var.node_instance_types
  node_desired_size   = var.node_desired_size
  node_min_size       = var.node_min_size
  node_max_size       = var.node_max_size

  depends_on = [module.vpc]
}}

module "storage" {{
  source = "./modules/storage"

  app_name    = var.app_name
  environment = var.environment

  depends_on = [module.vpc]
}}

module "iam" {{
  source = "./modules/iam"

  app_name        = var.app_name
  environment     = var.environment
  eks_cluster_arn = module.eks.cluster_arn
  s3_bucket_arns  = module.storage.bucket_arns

  depends_on = [module.eks, module.storage]
}}
'''

TERRAFORM_VARIABLES_AWS = '''# =============================================================================
# ForgeFlow Generated Variables — AWS
# =============================================================================

variable "app_name" {{
  description = "Application name used for resource naming"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {{
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }}
}}

variable "aws_region" {{
  description = "AWS region for resources"
  type        = string
  default     = "us-west-2"
}}

variable "vpc_cidr" {{
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}}

variable "availability_zones" {{
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b", "us-west-2c"]
}}

variable "private_subnet_cidrs" {{
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}}

variable "public_subnet_cidrs" {{
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}}

variable "kubernetes_version" {{
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.28"
}}

variable "node_instance_types" {{
  description = "EC2 instance types for EKS node groups"
  type        = list(string)
  default     = ["t3.medium"]
}}

variable "node_desired_size" {{
  description = "Desired number of nodes"
  type        = number
  default     = 2
}}

variable "node_min_size" {{
  description = "Minimum number of nodes"
  type        = number
  default     = 1
}}

variable "node_max_size" {{
  description = "Maximum number of nodes"
  type        = number
  default     = 5
}}

variable "enable_s3_versioning" {{
  description = "Enable versioning on S3 buckets"
  type        = bool
  default     = true
}}
'''

TERRAFORM_OUTPUTS_AWS = '''# =============================================================================
# ForgeFlow Generated Outputs — AWS
# =============================================================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "Endpoint for EKS cluster"
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}

output "s3_bucket_names" {
  description = "Names of created S3 buckets"
  value       = module.storage.bucket_names
}

output "app_role_arn" {
  description = "ARN of the application IAM role"
  value       = module.iam.app_role_arn
}
'''

TERRAFORM_NETWORK_AWS = '''# Network Module — AWS VPC
variable "app_name" { type = string }
variable "environment" { type = string }
variable "vpc_cidr" { type = string }
variable "azs" { type = list(string) }
variable "private_subnets" { type = list(string) }
variable "public_subnets" { type = list(string) }

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${var.app_name}-${var.environment}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.app_name}-${var.environment}-igw" }
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnets)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnets[count.index]
  availability_zone = var.azs[count.index]
  tags = {
    Name = "${var.app_name}-${var.environment}-private-${count.index + 1}"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnets)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnets[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true
  tags = {
    Name = "${var.app_name}-${var.environment}-public-${count.index + 1}"
    "kubernetes.io/role/elb" = "1"
  }
}

resource "aws_security_group" "app" {
  name        = "${var.app_name}-${var.environment}-sg"
  description = "Security group for ${var.app_name}"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

output "vpc_id"              { value = aws_vpc.main.id }
output "private_subnet_ids"  { value = aws_subnet.private[*].id }
output "public_subnet_ids"   { value = aws_subnet.public[*].id }
output "app_security_group_id" { value = aws_security_group.app.id }
'''

TERRAFORM_CLUSTER_AWS = '''# Cluster Module — AWS EKS
variable "app_name" { type = string }
variable "environment" { type = string }
variable "cluster_version" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "node_instance_types" { type = list(string) }
variable "node_desired_size" { type = number }
variable "node_min_size" { type = number }
variable "node_max_size" { type = number }

resource "aws_eks_cluster" "main" {
  name     = "${var.app_name}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.cluster_version

  vpc_config {
    subnet_ids = var.private_subnet_ids
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.app_name}-${var.environment}-ng"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.node_instance_types

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  update_config { max_unavailable = 1 }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.ecr_readonly,
  ]
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.app_name}-${var.environment}-eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow",
      Principal = { Service = "eks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role" "eks_node" {
  name               = "${var.app_name}-${var.environment}-eks-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow",
      Principal = { Service = "ec2.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_node.name
}

resource "aws_iam_role_policy_attachment" "ecr_readonly" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_node.name
}

output "cluster_name"           { value = aws_eks_cluster.main.name }
output "cluster_endpoint"       { value = aws_eks_cluster.main.endpoint }
output "cluster_arn"            { value = aws_eks_cluster.main.arn }
output "cluster_ca_certificate" { value = aws_eks_cluster.main.certificate_authority[0].data }
output "node_group_arn"         { value = aws_eks_node_group.main.arn }
'''

TERRAFORM_STORAGE_AWS = '''# Storage Module — AWS S3
variable "app_name" { type = string }
variable "environment" { type = string }

locals {
  buckets = {
    app    = "${var.app_name}-${var.environment}-app"
    assets = "${var.app_name}-${var.environment}-assets"
    logs   = "${var.app_name}-${var.environment}-logs"
  }
}

resource "aws_s3_bucket" "buckets" {
  for_each = local.buckets
  bucket   = each.value
  tags     = { Name = each.value, Purpose = each.key }
}

resource "aws_s3_bucket_versioning" "buckets" {
  for_each = aws_s3_bucket.buckets
  bucket   = each.value.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "buckets" {
  for_each = aws_s3_bucket.buckets
  bucket   = each.value.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "buckets" {
  for_each                = aws_s3_bucket.buckets
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_names" { value = { for k, v in aws_s3_bucket.buckets : k => v.bucket } }
output "bucket_arns"  { value = [for v in aws_s3_bucket.buckets : v.arn] }
'''

TERRAFORM_IAM_AWS = '''# IAM Module — AWS Roles & Policies
variable "app_name" { type = string }
variable "environment" { type = string }
variable "eks_cluster_arn" { type = string }
variable "s3_bucket_arns" { type = list(string) }

resource "aws_iam_role" "app" {
  name               = "${var.app_name}-${var.environment}-app-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Service = "pods.eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "app_s3" {
  name = "${var.app_name}-${var.environment}-s3-policy"
  role = aws_iam_role.app.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = concat(var.s3_bucket_arns, [for arn in var.s3_bucket_arns : "${arn}/*"])
    }]
  })
}

resource "aws_iam_role" "cicd" {
  name               = "${var.app_name}-${var.environment}-cicd-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "codebuild.amazonaws.com" }
    }]
  })
}

output "app_role_arn"  { value = aws_iam_role.app.arn }
output "app_role_name" { value = aws_iam_role.app.name }
output "cicd_role_arn" { value = aws_iam_role.cicd.arn }
'''


# =============================================================================
# ──────────────────────────── GCP TEMPLATES ───────────────────────────────────
# =============================================================================

TERRAFORM_MAIN_GCP = '''# =============================================================================
# ForgeFlow Generated Terraform — GCP
# Generated: {timestamp}
# =============================================================================

terraform {{
  required_version = ">= 1.0"

  required_providers {{
    google = {{
      source  = "hashicorp/google"
      version = "~> 5.0"
    }}
    kubernetes = {{
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }}
  }}

  # backend "gcs" {{
  #   bucket = "{app_name}-terraform-state"
  #   prefix = "terraform/state"
  # }}
}}

provider "google" {{
  project = var.gcp_project
  region  = var.gcp_region
}}

provider "kubernetes" {{
  host                   = "https://${{module.gke.cluster_endpoint}}"
  token                  = module.gke.access_token
  cluster_ca_certificate = base64decode(module.gke.cluster_ca_certificate)
}}

locals {{
  name_prefix = "${{var.app_name}}-${{var.environment}}"
}}

module "network" {{
  source = "./modules/network"

  app_name    = var.app_name
  environment = var.environment
  gcp_project = var.gcp_project
  gcp_region  = var.gcp_region
  vpc_cidr    = var.vpc_cidr
}}

module "gke" {{
  source = "./modules/cluster"

  app_name           = var.app_name
  environment        = var.environment
  gcp_project        = var.gcp_project
  gcp_region         = var.gcp_region
  gcp_zone           = var.gcp_zone
  kubernetes_version = var.kubernetes_version
  network_id         = module.network.network_id
  subnet_id          = module.network.subnet_id
  node_machine_type  = var.node_machine_type
  node_count         = var.node_count
  node_min_count     = var.node_min_count
  node_max_count     = var.node_max_count

  depends_on = [module.network]
}}

module "storage" {{
  source = "./modules/storage"

  app_name    = var.app_name
  environment = var.environment
  gcp_project = var.gcp_project
  gcp_region  = var.gcp_region
}}

module "iam" {{
  source = "./modules/iam"

  app_name    = var.app_name
  environment = var.environment
  gcp_project = var.gcp_project

  depends_on = [module.gke]
}}
'''

TERRAFORM_VARIABLES_GCP = '''# =============================================================================
# ForgeFlow Generated Variables — GCP
# =============================================================================

variable "app_name" {{
  description = "Application name used for resource naming"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {{
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }}
}}

variable "gcp_project" {{
  description = "GCP project ID"
  type        = string
  # Set via: terraform.tfvars or TF_VAR_gcp_project
}}

variable "gcp_region" {{
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}}

variable "gcp_zone" {{
  description = "GCP zone for zonal resources"
  type        = string
  default     = "us-central1-a"
}}

variable "vpc_cidr" {{
  description = "CIDR block for VPC subnet"
  type        = string
  default     = "10.0.0.0/16"
}}

variable "kubernetes_version" {{
  description = "Kubernetes version for GKE cluster"
  type        = string
  default     = "1.28"
}}

variable "node_machine_type" {{
  description = "GCE machine type for GKE nodes"
  type        = string
  default     = "e2-standard-2"
}}

variable "node_count" {{
  description = "Number of nodes per zone"
  type        = number
  default     = 2
}}

variable "node_min_count" {{
  description = "Minimum nodes for autoscaling"
  type        = number
  default     = 1
}}

variable "node_max_count" {{
  description = "Maximum nodes for autoscaling"
  type        = number
  default     = 5
}}
'''

TERRAFORM_OUTPUTS_GCP = '''# =============================================================================
# ForgeFlow Generated Outputs — GCP
# =============================================================================

output "network_id" {
  description = "VPC network ID"
  value       = module.network.network_id
}

output "gke_cluster_name" {
  description = "Name of the GKE cluster"
  value       = module.gke.cluster_name
}

output "gke_cluster_endpoint" {
  description = "Endpoint for GKE cluster"
  value       = module.gke.cluster_endpoint
  sensitive   = true
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "gcloud container clusters get-credentials ${module.gke.cluster_name} --region ${var.gcp_region} --project ${var.gcp_project}"
}

output "gcs_bucket_names" {
  description = "Names of created GCS buckets"
  value       = module.storage.bucket_names
}

output "app_service_account_email" {
  description = "Email of the application service account"
  value       = module.iam.app_service_account_email
}
'''

TERRAFORM_NETWORK_GCP = '''# Network Module — GCP VPC
variable "app_name" { type = string }
variable "environment" { type = string }
variable "gcp_project" { type = string }
variable "gcp_region" { type = string }
variable "vpc_cidr" { type = string }

resource "google_compute_network" "main" {
  project                 = var.gcp_project
  name                    = "${var.app_name}-${var.environment}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  project       = var.gcp_project
  name          = "${var.app_name}-${var.environment}-subnet"
  ip_cidr_range = var.vpc_cidr
  region        = var.gcp_region
  network       = google_compute_network.main.id

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/20"
  }

  private_ip_google_access = true
}

resource "google_compute_firewall" "allow_internal" {
  project = var.gcp_project
  name    = "${var.app_name}-${var.environment}-allow-internal"
  network = google_compute_network.main.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow { protocol = "udp"; ports = ["0-65535"] }
  allow { protocol = "icmp" }

  source_ranges = [var.vpc_cidr]
}

output "network_id"   { value = google_compute_network.main.id }
output "network_name" { value = google_compute_network.main.name }
output "subnet_id"    { value = google_compute_subnetwork.main.id }
output "subnet_name"  { value = google_compute_subnetwork.main.name }
'''

TERRAFORM_CLUSTER_GCP = '''# Cluster Module — GCP GKE
variable "app_name" { type = string }
variable "environment" { type = string }
variable "gcp_project" { type = string }
variable "gcp_region" { type = string }
variable "gcp_zone" { type = string }
variable "kubernetes_version" { type = string }
variable "network_id" { type = string }
variable "subnet_id" { type = string }
variable "node_machine_type" { type = string }
variable "node_count" { type = number }
variable "node_min_count" { type = number }
variable "node_max_count" { type = number }

resource "google_container_cluster" "main" {
  project  = var.gcp_project
  name     = "${var.app_name}-${var.environment}"
  location = var.gcp_region

  # Use a separately managed node pool
  remove_default_node_pool = true
  initial_node_count       = 1

  network    = var.network_id
  subnetwork = var.subnet_id

  min_master_version = var.kubernetes_version

  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.gcp_project}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }
}

resource "google_container_node_pool" "main" {
  project    = var.gcp_project
  name       = "${var.app_name}-${var.environment}-pool"
  location   = var.gcp_region
  cluster    = google_container_cluster.main.name
  node_count = var.node_count

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  node_config {
    machine_type = var.node_machine_type
    disk_size_gb = 50
    disk_type    = "pd-ssd"

    workload_metadata_config { mode = "GKE_METADATA" }

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

data "google_client_config" "default" {}

output "cluster_name"           { value = google_container_cluster.main.name }
output "cluster_endpoint"       { value = google_container_cluster.main.endpoint }
output "cluster_ca_certificate" { value = google_container_cluster.main.master_auth[0].cluster_ca_certificate }
output "access_token"           { value = data.google_client_config.default.access_token; sensitive = true }
'''

TERRAFORM_STORAGE_GCP = '''# Storage Module — GCP GCS
variable "app_name" { type = string }
variable "environment" { type = string }
variable "gcp_project" { type = string }
variable "gcp_region" { type = string }

locals {
  buckets = {
    app    = "${var.app_name}-${var.environment}-app"
    assets = "${var.app_name}-${var.environment}-assets"
    logs   = "${var.app_name}-${var.environment}-logs"
  }
}

resource "google_storage_bucket" "buckets" {
  for_each = local.buckets

  project                     = var.gcp_project
  name                        = each.value
  location                    = var.gcp_region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning { enabled = true }

  lifecycle_rule {
    action     { type = "Delete" }
    condition  { age = 365 }
  }
}

output "bucket_names" { value = { for k, v in google_storage_bucket.buckets : k => v.name } }
output "bucket_urls"  { value = [for v in google_storage_bucket.buckets : v.url] }
'''

TERRAFORM_IAM_GCP = '''# IAM Module — GCP Service Accounts
variable "app_name" { type = string }
variable "environment" { type = string }
variable "gcp_project" { type = string }

resource "google_service_account" "app" {
  project      = var.gcp_project
  account_id   = "${var.app_name}-${var.environment}-sa"
  display_name = "${var.app_name} ${var.environment} Service Account"
  description  = "Service account for ${var.app_name} in ${var.environment}"
}

resource "google_project_iam_member" "app_storage" {
  project = var.gcp_project
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_logging" {
  project = var.gcp_project
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_project_iam_member" "app_monitoring" {
  project = var.gcp_project
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.app.email}"
}

resource "google_service_account" "cicd" {
  project      = var.gcp_project
  account_id   = "${var.app_name}-${var.environment}-cicd-sa"
  display_name = "${var.app_name} CI/CD Service Account"
}

resource "google_project_iam_member" "cicd_artifacts" {
  project = var.gcp_project
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cicd.email}"
}

output "app_service_account_email"  { value = google_service_account.app.email }
output "cicd_service_account_email" { value = google_service_account.cicd.email }
'''


# =============================================================================
# ──────────────────────────── AZURE TEMPLATES ─────────────────────────────────
# =============================================================================

TERRAFORM_MAIN_AZURE = '''# =============================================================================
# ForgeFlow Generated Terraform — Azure
# Generated: {timestamp}
# =============================================================================

terraform {{
  required_version = ">= 1.0"

  required_providers {{
    azurerm = {{
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }}
    kubernetes = {{
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }}
  }}

  # backend "azurerm" {{
  #   resource_group_name  = "{app_name}-tfstate-rg"
  #   storage_account_name = "{app_name}tfstate"
  #   container_name       = "tfstate"
  #   key                  = "terraform.tfstate"
  # }}
}}

provider "azurerm" {{
  features {{
    resource_group {{ prevent_deletion_if_contains_resources = false }}
    key_vault     {{ purge_soft_delete_on_destroy = true }}
  }}
}}

provider "kubernetes" {{
  host                   = module.aks.kube_config.host
  client_certificate     = base64decode(module.aks.kube_config.client_certificate)
  client_key             = base64decode(module.aks.kube_config.client_key)
  cluster_ca_certificate = base64decode(module.aks.kube_config.cluster_ca_certificate)
}}

locals {{
  name_prefix = "${{var.app_name}}-${{var.environment}}"
}}

module "network" {{
  source = "./modules/network"

  app_name        = var.app_name
  environment     = var.environment
  azure_location  = var.azure_location
  address_space   = var.address_space
  subnet_prefixes = var.subnet_prefixes
}}

module "aks" {{
  source = "./modules/cluster"

  app_name           = var.app_name
  environment        = var.environment
  azure_location     = var.azure_location
  resource_group_id  = module.network.resource_group_id
  subnet_id          = module.network.subnet_id
  kubernetes_version = var.kubernetes_version
  vm_size            = var.node_vm_size
  node_count         = var.node_count
  min_count          = var.node_min_count
  max_count          = var.node_max_count

  depends_on = [module.network]
}}

module "storage" {{
  source = "./modules/storage"

  app_name           = var.app_name
  environment        = var.environment
  azure_location     = var.azure_location
  resource_group_name = module.network.resource_group_name
}}

module "iam" {{
  source = "./modules/iam"

  app_name            = var.app_name
  environment         = var.environment
  aks_principal_id    = module.aks.kubelet_identity_object_id
  storage_account_id  = module.storage.storage_account_id

  depends_on = [module.aks, module.storage]
}}
'''

TERRAFORM_VARIABLES_AZURE = '''# =============================================================================
# ForgeFlow Generated Variables — Azure
# =============================================================================

variable "app_name" {{
  description = "Application name used for resource naming"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {{
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }}
}}

variable "azure_location" {{
  description = "Azure region for resources"
  type        = string
  default     = "eastus"
}}

variable "address_space" {{
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}}

variable "subnet_prefixes" {{
  description = "Subnet address prefixes"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}}

variable "kubernetes_version" {{
  description = "Kubernetes version for AKS cluster"
  type        = string
  default     = "1.28"
}}

variable "node_vm_size" {{
  description = "VM size for AKS nodes"
  type        = string
  default     = "Standard_D2_v3"
}}

variable "node_count" {{
  description = "Initial number of nodes"
  type        = number
  default     = 2
}}

variable "node_min_count" {{
  description = "Minimum number of nodes for autoscaling"
  type        = number
  default     = 1
}}

variable "node_max_count" {{
  description = "Maximum number of nodes for autoscaling"
  type        = number
  default     = 5
}}
'''

TERRAFORM_OUTPUTS_AZURE = '''# =============================================================================
# ForgeFlow Generated Outputs — Azure
# =============================================================================

output "resource_group_name" {
  description = "Name of the resource group"
  value       = module.network.resource_group_name
}

output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = module.network.vnet_id
}

output "aks_cluster_name" {
  description = "Name of the AKS cluster"
  value       = module.aks.cluster_name
}

output "aks_cluster_id" {
  description = "ID of the AKS cluster"
  value       = module.aks.cluster_id
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "az aks get-credentials --resource-group ${module.network.resource_group_name} --name ${module.aks.cluster_name}"
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = module.storage.storage_account_name
}

output "app_identity_client_id" {
  description = "Client ID of the app managed identity"
  value       = module.iam.app_identity_client_id
}
'''

TERRAFORM_NETWORK_AZURE = '''# Network Module — Azure VNet
variable "app_name" { type = string }
variable "environment" { type = string }
variable "azure_location" { type = string }
variable "address_space" { type = list(string) }
variable "subnet_prefixes" { type = list(string) }

resource "azurerm_resource_group" "main" {
  name     = "${var.app_name}-${var.environment}-rg"
  location = var.azure_location
  tags     = { Application = var.app_name, Environment = var.environment, ManagedBy = "Terraform" }
}

resource "azurerm_virtual_network" "main" {
  name                = "${var.app_name}-${var.environment}-vnet"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = var.address_space
}

resource "azurerm_subnet" "main" {
  count                = length(var.subnet_prefixes)
  name                 = "${var.app_name}-${var.environment}-subnet-${count.index + 1}"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.subnet_prefixes[count.index]]
}

resource "azurerm_network_security_group" "main" {
  name                = "${var.app_name}-${var.environment}-nsg"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

output "resource_group_id"   { value = azurerm_resource_group.main.id }
output "resource_group_name" { value = azurerm_resource_group.main.name }
output "vnet_id"             { value = azurerm_virtual_network.main.id }
output "subnet_id"           { value = azurerm_subnet.main[0].id }
output "subnet_ids"          { value = azurerm_subnet.main[*].id }
'''

TERRAFORM_CLUSTER_AZURE = '''# Cluster Module — Azure AKS
variable "app_name" { type = string }
variable "environment" { type = string }
variable "azure_location" { type = string }
variable "resource_group_id" { type = string }
variable "subnet_id" { type = string }
variable "kubernetes_version" { type = string }
variable "vm_size" { type = string }
variable "node_count" { type = number }
variable "min_count" { type = number }
variable "max_count" { type = number }

data "azurerm_resource_group" "main" {
  id = var.resource_group_id
}

resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.app_name}-${var.environment}-aks"
  location            = var.azure_location
  resource_group_name = data.azurerm_resource_group.main.name
  dns_prefix          = "${var.app_name}-${var.environment}"
  kubernetes_version  = var.kubernetes_version

  default_node_pool {
    name                = "default"
    node_count          = var.node_count
    vm_size             = var.vm_size
    vnet_subnet_id      = var.subnet_id
    enable_auto_scaling = true
    min_count           = var.min_count
    max_count           = var.max_count
    os_disk_size_gb     = 50
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }

  tags = { Application = var.app_name, Environment = var.environment }
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-${var.environment}-logs"
  location            = var.azure_location
  resource_group_name = data.azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

output "cluster_name"                 { value = azurerm_kubernetes_cluster.main.name }
output "cluster_id"                   { value = azurerm_kubernetes_cluster.main.id }
output "kube_config"                  { value = azurerm_kubernetes_cluster.main.kube_config[0]; sensitive = true }
output "kubelet_identity_object_id"   { value = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id }
output "kubelet_identity_client_id"   { value = azurerm_kubernetes_cluster.main.kubelet_identity[0].client_id }
'''

TERRAFORM_STORAGE_AZURE = '''# Storage Module — Azure Blob Storage
variable "app_name" { type = string }
variable "environment" { type = string }
variable "azure_location" { type = string }
variable "resource_group_name" { type = string }

# Storage account name must be globally unique, 3-24 chars, lowercase alphanumeric
locals {
  # Trim to 20 chars to allow env suffix
  sa_name = lower(replace(substr("${var.app_name}${var.environment}sa", 0, 24), "-", ""))
}

resource "azurerm_storage_account" "main" {
  name                     = local.sa_name
  resource_group_name      = var.resource_group_name
  location                 = var.azure_location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled       = true
    change_feed_enabled      = true
    delete_retention_policy  { days = 30 }
    container_delete_retention_policy { days = 30 }
  }

  tags = { Application = var.app_name, Environment = var.environment }
}

resource "azurerm_storage_container" "containers" {
  for_each = toset(["app", "assets", "logs"])

  name                  = each.value
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

output "storage_account_name" { value = azurerm_storage_account.main.name }
output "storage_account_id"   { value = azurerm_storage_account.main.id }
output "primary_blob_endpoint" { value = azurerm_storage_account.main.primary_blob_endpoint }
'''

TERRAFORM_IAM_AZURE = '''# IAM Module — Azure Managed Identity & RBAC
variable "app_name" { type = string }
variable "environment" { type = string }
variable "aks_principal_id" { type = string }
variable "storage_account_id" { type = string }

data "azurerm_subscription" "current" {}
data "azurerm_resource_group" "main" {
  name = "${var.app_name}-${var.environment}-rg"
}

resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.app_name}-${var.environment}-identity"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
}

# Allow app identity to read/write blobs
resource "azurerm_role_assignment" "app_storage" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# Allow AKS kubelet to pull from ACR (if registry is in same subscription)
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "AcrPull"
  principal_id         = var.aks_principal_id
}

output "app_identity_id"        { value = azurerm_user_assigned_identity.app.id }
output "app_identity_client_id" { value = azurerm_user_assigned_identity.app.client_id }
output "app_identity_principal_id" { value = azurerm_user_assigned_identity.app.principal_id }
'''


# =============================================================================
# ──────────────────────────── OCI TEMPLATES ───────────────────────────────────
# =============================================================================

TERRAFORM_MAIN_OCI = '''# =============================================================================
# ForgeFlow Generated Terraform — OCI (Oracle Cloud Infrastructure)
# Generated: {timestamp}
# =============================================================================

terraform {{
  required_version = ">= 1.0"

  required_providers {{
    oci = {{
      source  = "oracle/oci"
      version = "~> 5.0"
    }}
    kubernetes = {{
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }}
  }}

  # OCI Object Storage backend (optional)
  # backend "http" {{
  #   address        = "https://objectstorage.<region>.oraclecloud.com/p/<PAR>/n/<namespace>/b/{app_name}-tfstate/o/terraform.tfstate"
  #   update_method  = "PUT"
  # }}
}}

provider "oci" {{
  tenancy_ocid = var.oci_tenancy_ocid
  region       = var.oci_region
  # auth = "InstancePrincipal" for OCI compute instances
  # Otherwise: API key auth via ~/.oci/config or env vars
}}

locals {{
  name_prefix = "${{var.app_name}}-${{var.environment}}"
}}

module "network" {{
  source = "./modules/network"

  app_name         = var.app_name
  environment      = var.environment
  compartment_id   = var.oci_compartment_id
  oci_region       = var.oci_region
  vcn_cidr         = var.vcn_cidr
}}

module "oke" {{
  source = "./modules/cluster"

  app_name           = var.app_name
  environment        = var.environment
  compartment_id     = var.oci_compartment_id
  oci_region         = var.oci_region
  vcn_id             = module.network.vcn_id
  subnet_id          = module.network.private_subnet_id
  lb_subnet_id       = module.network.public_subnet_id
  kubernetes_version = var.kubernetes_version
  node_shape         = var.node_shape
  node_ocpus         = var.node_ocpus
  node_memory_gb     = var.node_memory_gb
  node_count         = var.node_count

  depends_on = [module.network]
}}

module "storage" {{
  source = "./modules/storage"

  app_name       = var.app_name
  environment    = var.environment
  compartment_id = var.oci_compartment_id
  oci_region     = var.oci_region
  namespace      = data.oci_objectstorage_namespace.this.namespace
}}

module "iam" {{
  source = "./modules/iam"

  app_name       = var.app_name
  environment    = var.environment
  compartment_id = var.oci_compartment_id
  tenancy_ocid   = var.oci_tenancy_ocid

  depends_on = [module.oke]
}}

data "oci_objectstorage_namespace" "this" {{
  compartment_id = var.oci_compartment_id
}}
'''

TERRAFORM_VARIABLES_OCI = '''# =============================================================================
# ForgeFlow Generated Variables — OCI
# =============================================================================

variable "app_name" {{
  description = "Application name used for resource naming"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment"
  type        = string
  default     = "dev"

  validation {{
    condition     = contains(["dev", "staging", "production"], var.environment)
    error_message = "Environment must be dev, staging, or production."
  }}
}}

variable "oci_tenancy_ocid" {{
  description = "OCID of the OCI tenancy"
  type        = string
  # Set via: TF_VAR_oci_tenancy_ocid or terraform.tfvars
}}

variable "oci_compartment_id" {{
  description = "OCID of the compartment for resources"
  type        = string
  # Set via: TF_VAR_oci_compartment_id or terraform.tfvars
}}

variable "oci_region" {{
  description = "OCI region identifier"
  type        = string
  default     = "us-ashburn-1"
}}

variable "vcn_cidr" {{
  description = "CIDR block for the VCN"
  type        = string
  default     = "10.0.0.0/16"
}}

variable "kubernetes_version" {{
  description = "Kubernetes version for OKE cluster"
  type        = string
  default     = "v1.28.2"
}}

variable "node_shape" {{
  description = "Shape for OKE node pool compute instances"
  type        = string
  default     = "VM.Standard.E4.Flex"
}}

variable "node_ocpus" {{
  description = "Number of OCPUs per node (Flex shapes)"
  type        = number
  default     = 2
}}

variable "node_memory_gb" {{
  description = "Memory in GB per node (Flex shapes)"
  type        = number
  default     = 16
}}

variable "node_count" {{
  description = "Number of nodes in the node pool"
  type        = number
  default     = 2
}}
'''

TERRAFORM_OUTPUTS_OCI = '''# =============================================================================
# ForgeFlow Generated Outputs — OCI
# =============================================================================

output "vcn_id" {
  description = "OCID of the VCN"
  value       = module.network.vcn_id
}

output "oke_cluster_id" {
  description = "OCID of the OKE cluster"
  value       = module.oke.cluster_id
}

output "oke_cluster_name" {
  description = "Name of the OKE cluster"
  value       = module.oke.cluster_name
}

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "oci ce cluster create-kubeconfig --cluster-id ${module.oke.cluster_id} --region ${var.oci_region}"
}

output "object_storage_namespace" {
  description = "OCI Object Storage namespace"
  value       = module.storage.namespace
}

output "bucket_names" {
  description = "Names of created Object Storage buckets"
  value       = module.storage.bucket_names
}
'''

TERRAFORM_NETWORK_OCI = '''# Network Module — OCI VCN
variable "app_name" { type = string }
variable "environment" { type = string }
variable "compartment_id" { type = string }
variable "oci_region" { type = string }
variable "vcn_cidr" { type = string }

resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_id
  cidr_block     = var.vcn_cidr
  display_name   = "${var.app_name}-${var.environment}-vcn"
  dns_label      = replace("${var.app_name}${var.environment}", "-", "")
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.app_name}-${var.environment}-igw"
  enabled        = true
}

resource "oci_core_nat_gateway" "main" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.app_name}-${var.environment}-nat"
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.app_name}-${var.environment}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.app_name}-${var.environment}-private-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.main.id
  }
}

resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.main.id
  cidr_block        = cidrsubnet(var.vcn_cidr, 8, 1)
  display_name      = "${var.app_name}-${var.environment}-public-subnet"
  route_table_id    = oci_core_route_table.public.id
  dns_label         = "public"
}

resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 10)
  display_name               = "${var.app_name}-${var.environment}-private-subnet"
  route_table_id             = oci_core_route_table.private.id
  prohibit_public_ip_on_vnic = true
  dns_label                  = "private"
}

output "vcn_id"           { value = oci_core_vcn.main.id }
output "public_subnet_id" { value = oci_core_subnet.public.id }
output "private_subnet_id" { value = oci_core_subnet.private.id }
'''

TERRAFORM_CLUSTER_OCI = '''# Cluster Module — OCI OKE
variable "app_name" { type = string }
variable "environment" { type = string }
variable "compartment_id" { type = string }
variable "oci_region" { type = string }
variable "vcn_id" { type = string }
variable "subnet_id" { type = string }
variable "lb_subnet_id" { type = string }
variable "kubernetes_version" { type = string }
variable "node_shape" { type = string }
variable "node_ocpus" { type = number }
variable "node_memory_gb" { type = number }
variable "node_count" { type = number }

resource "oci_containerengine_cluster" "main" {
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "${var.app_name}-${var.environment}"
  vcn_id             = var.vcn_id

  endpoint_config {
    is_public_ip_enabled = false
    subnet_id            = var.subnet_id
  }

  options {
    service_lb_subnet_ids = [var.lb_subnet_id]

    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
}

resource "oci_containerengine_node_pool" "main" {
  cluster_id         = oci_containerengine_cluster.main.id
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "${var.app_name}-${var.environment}-pool"

  node_config_details {
    size = var.node_count

    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = var.subnet_id
    }
  }

  node_shape = var.node_shape

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }

  node_source_details {
    image_id    = data.oci_core_images.ol8.images[0].id
    source_type = "IMAGE"
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "ol8" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = var.node_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

output "cluster_id"   { value = oci_containerengine_cluster.main.id }
output "cluster_name" { value = oci_containerengine_cluster.main.name }
'''

TERRAFORM_STORAGE_OCI = '''# Storage Module — OCI Object Storage
variable "app_name" { type = string }
variable "environment" { type = string }
variable "compartment_id" { type = string }
variable "oci_region" { type = string }
variable "namespace" { type = string }

locals {
  buckets = ["app", "assets", "logs"]
}

resource "oci_objectstorage_bucket" "buckets" {
  for_each = toset(local.buckets)

  compartment_id = var.compartment_id
  name           = "${var.app_name}-${var.environment}-${each.value}"
  namespace      = var.namespace

  access_type            = "NoPublicAccess"
  object_events_enabled  = true
  storage_tier           = "Standard"
  versioning             = "Enabled"
}

output "namespace"    { value = var.namespace }
output "bucket_names" { value = { for k, v in oci_objectstorage_bucket.buckets : k => v.name } }
'''

TERRAFORM_IAM_OCI = '''# IAM Module — OCI Dynamic Groups & Policies
variable "app_name" { type = string }
variable "environment" { type = string }
variable "compartment_id" { type = string }
variable "tenancy_ocid" { type = string }

resource "oci_identity_dynamic_group" "app" {
  compartment_id = var.tenancy_ocid  # Dynamic groups must be in tenancy root
  name           = "${var.app_name}-${var.environment}-dg"
  description    = "Dynamic group for ${var.app_name} ${var.environment} instances"
  matching_rule  = "ALL {instance.compartment.id = '${var.compartment_id}'}"
}

resource "oci_identity_policy" "app_object_storage" {
  compartment_id = var.compartment_id
  name           = "${var.app_name}-${var.environment}-objectstorage-policy"
  description    = "Allow app instances to access Object Storage"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to manage objects in compartment id ${var.compartment_id} where target.bucket.name = '${var.app_name}-${var.environment}-app'",
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to read objects in compartment id ${var.compartment_id} where target.bucket.name = '${var.app_name}-${var.environment}-assets'",
  ]
}

resource "oci_identity_policy" "app_logging" {
  compartment_id = var.compartment_id
  name           = "${var.app_name}-${var.environment}-logging-policy"
  description    = "Allow app instances to write logs"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.app.name} to use log-content in compartment id ${var.compartment_id}",
  ]
}

output "dynamic_group_id"   { value = oci_identity_dynamic_group.app.id }
output "dynamic_group_name" { value = oci_identity_dynamic_group.app.name }
'''


# =============================================================================
# DOCKER COMPOSE TEMPLATE
# =============================================================================

DOCKER_COMPOSE_TEMPLATE = '''# ForgeFlow Generated Docker Compose
# For local development
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: base
    ports:
      - "{app_port}:{app_port}"
    volumes:
      - .:/app
      - /app/node_modules
    environment:
      - NODE_ENV=development
      - DEBUG=true
      - LOG_LEVEL=debug
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/{app_name}
      - REDIS_URL=redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - app-network

  db:
    image: postgres:15-alpine
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {app_name}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - app-network

volumes:
  postgres_data:
  redis_data:

networks:
  app-network:
    driver: bridge
'''

DOCKERIGNORE_TEMPLATE = '''# ForgeFlow Generated .dockerignore
.git
.gitignore
*.md
docs/
.idea/
.vscode/
*.swp
.DS_Store
__pycache__/
*.py[cod]
venv/
.venv/
.env
.env.local
node_modules/
coverage/
.pytest_cache/
.mypy_cache/
terraform/
*.tfstate*
.terraform/
.github/
.gitlab-ci.yml
.forgeflow/
'''


# =============================================================================
# PULUMI TEMPLATES (Optional)
# =============================================================================

PULUMI_INDEX_TS = '''import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";
import * as eks from "@pulumi/eks";

const config = new pulumi.Config();
const appName = config.require("appName");
const environment = config.get("environment") || "dev";

// Create VPC
const vpc = new aws.ec2.Vpc("main", {{
    cidrBlock: "10.0.0.0/16",
    enableDnsHostnames: true,
    enableDnsSupport: true,
    tags: {{
        Name: `${{appName}}-${{environment}}-vpc`,
        Environment: environment,
        ManagedBy: "Pulumi",
        Generator: "ForgeFlow",
    }},
}});

// Create EKS Cluster
const cluster = new eks.Cluster("cluster", {{
    name: `${{appName}}-${{environment}}`,
    vpcId: vpc.id,
    desiredCapacity: 2,
    minSize: 1,
    maxSize: 5,
    instanceType: "t3.medium",
    tags: {{
        Environment: environment,
    }},
}});

// Export outputs
export const kubeconfig = cluster.kubeconfig;
export const clusterName = cluster.eksCluster.name;
export const vpcId = vpc.id;
'''

PULUMI_YAML = '''name: {app_name}-infrastructure
runtime: nodejs
description: ForgeFlow generated Pulumi infrastructure

config:
  appName:
    default: {app_name}
  environment:
    default: dev
  aws:region:
    default: us-west-2
'''

# =============================================================================
# Template dispatch tables
# =============================================================================

_MAIN_TF = {
    'aws':   TERRAFORM_MAIN_AWS,
    'gcp':   TERRAFORM_MAIN_GCP,
    'azure': TERRAFORM_MAIN_AZURE,
    'oci':   TERRAFORM_MAIN_OCI,
}
_VARS_TF = {
    'aws':   TERRAFORM_VARIABLES_AWS,
    'gcp':   TERRAFORM_VARIABLES_GCP,
    'azure': TERRAFORM_VARIABLES_AZURE,
    'oci':   TERRAFORM_VARIABLES_OCI,
}
_OUTPUTS_TF = {
    'aws':   TERRAFORM_OUTPUTS_AWS,
    'gcp':   TERRAFORM_OUTPUTS_GCP,
    'azure': TERRAFORM_OUTPUTS_AZURE,
    'oci':   TERRAFORM_OUTPUTS_OCI,
}
_NETWORK_TF = {
    'aws':   TERRAFORM_NETWORK_AWS,
    'gcp':   TERRAFORM_NETWORK_GCP,
    'azure': TERRAFORM_NETWORK_AZURE,
    'oci':   TERRAFORM_NETWORK_OCI,
}
_CLUSTER_TF = {
    'aws':   TERRAFORM_CLUSTER_AWS,
    'gcp':   TERRAFORM_CLUSTER_GCP,
    'azure': TERRAFORM_CLUSTER_AZURE,
    'oci':   TERRAFORM_CLUSTER_OCI,
}
_STORAGE_TF = {
    'aws':   TERRAFORM_STORAGE_AWS,
    'gcp':   TERRAFORM_STORAGE_GCP,
    'azure': TERRAFORM_STORAGE_AZURE,
    'oci':   TERRAFORM_STORAGE_OCI,
}
_IAM_TF = {
    'aws':   TERRAFORM_IAM_AWS,
    'gcp':   TERRAFORM_IAM_GCP,
    'azure': TERRAFORM_IAM_AZURE,
    'oci':   TERRAFORM_IAM_OCI,
}

SUPPORTED_CLOUDS = list(_MAIN_TF.keys())


class IACAgent(BaseAgent):
    """
    Infrastructure as Code Agent — generates Terraform, Docker, and Pulumi configs.

    Supported clouds: aws | gcp | azure | oci

    Responsibilities:
    - Terraform files (main.tf, variables.tf, outputs.tf) per cloud
    - Terraform modules (network, cluster, storage, iam) per cloud
    - Dockerfile based on detected language
    - docker-compose.yml for local development
    - Pulumi support (optional, AWS only currently)
    """

    def __init__(self):
        super().__init__(
            name="IACAgent",
            description="Generates Infrastructure as Code (Terraform/Pulumi/Docker) for AWS, GCP, Azure, OCI"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate infrastructure code based on repository analysis."""
        if params is None:
            params = {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {"repo_path": params}

        repo_path     = Path(params.get("repo_path", params.get("path", "."))).resolve()
        overwrite     = params.get("greenfield", False)
        cloud         = params.get("cloud", "aws").lower()
        include_pulumi = params.get("include_pulumi", False)

        # Validate cloud
        if cloud not in SUPPORTED_CLOUDS:
            return self.create_result(
                status="error",
                summary=f"Unsupported cloud '{cloud}'. Supported: {', '.join(SUPPORTED_CLOUDS)}",
                data={"supported_clouds": SUPPORTED_CLOUDS},
                findings=[f"❌ Unknown cloud provider: '{cloud}'"],
                actions=[]
            )

        self.log(f"Generating IAC for: {repo_path} (cloud={cloud})")

        actions  = []
        findings = []

        app_name     = self._detect_app_name(repo_path)
        primary_lang = self._detect_primary_language(repo_path)

        self.log(f"Detected app: {app_name}, language: {primary_lang}")

        infra_path = repo_path / "infrastructure"
        infra_path.mkdir(exist_ok=True)

        # Terraform
        terraform_actions = self._generate_terraform(infra_path, app_name, cloud, overwrite)
        actions.extend(terraform_actions)

        # Docker
        docker_actions = self._generate_docker_files(repo_path, primary_lang, app_name, overwrite)
        actions.extend(docker_actions)

        # Pulumi (optional)
        if include_pulumi:
            pulumi_actions = self._generate_pulumi(infra_path, app_name, overwrite)
            actions.extend(pulumi_actions)

        created  = len([a for a in actions if a.get('action') == 'created'])
        existing = len([a for a in actions if a.get('action') == 'exists'])
        findings.append(f"✅ {created} files created, {existing} already existed")

        return self.create_result(
            status="success",
            summary=f"Generated {cloud.upper()} IAC artifacts for '{app_name}' ({created} files created)",
            data={
                "app_name":           app_name,
                "primary_language":   primary_lang,
                "cloud_provider":     cloud,
                "infrastructure_path": str(infra_path),
                "files_created":      created,
                "files_existing":     existing,
            },
            findings=findings,
            actions=actions
        )

    # -------------------------------------------------------------------------
    # Detection helpers
    # -------------------------------------------------------------------------

    def _detect_app_name(self, repo_path: Path) -> str:
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                if isinstance(data, dict) and data.get("name"):
                    return data["name"].replace("@", "").replace("/", "-")
            except Exception:
                pass

        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                for line in pyproject.read_text().split("\n"):
                    if line.startswith("name"):
                        name = line.split("=")[1].strip().strip('"\'')
                        if name:
                            return name
            except Exception:
                pass

        return repo_path.name.lower().replace(" ", "-").replace("_", "-")

    def _detect_primary_language(self, repo_path: Path) -> str:
        ext_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".go": "Go",     ".rs": "Rust",        ".java": "Java",
            ".rb": "Ruby",
        }
        counts: Dict[str, int] = {}
        for ext, lang in ext_map.items():
            count = len(list(repo_path.rglob(f"*{ext}")))
            if count > 0:
                counts[lang] = count
        return max(counts, key=counts.get) if counts else "Python"

    # -------------------------------------------------------------------------
    # Terraform generation (cloud-dispatched)
    # -------------------------------------------------------------------------

    def _generate_terraform(self, infra_path: Path, app_name: str, cloud: str, overwrite: bool = False) -> List[Dict]:
        actions: List[Dict] = []
        terraform_path = infra_path / "terraform"
        terraform_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        main_content = _MAIN_TF[cloud].format(timestamp=timestamp, app_name=app_name)
        actions.append(self._safe_write(terraform_path / "main.tf", main_content, overwrite))

        vars_content = _VARS_TF[cloud].format(app_name=app_name)
        actions.append(self._safe_write(terraform_path / "variables.tf", vars_content, overwrite))

        actions.append(self._safe_write(terraform_path / "outputs.tf", _OUTPUTS_TF[cloud], overwrite))

        modules_path = terraform_path / "modules"
        modules_path.mkdir(exist_ok=True)

        for module_name, templates in [
            ("network", _NETWORK_TF),
            ("cluster", _CLUSTER_TF),
            ("storage", _STORAGE_TF),
            ("iam",     _IAM_TF),
        ]:
            mod_path = modules_path / module_name
            mod_path.mkdir(exist_ok=True)
            actions.append(self._safe_write(mod_path / "main.tf", templates[cloud], overwrite))

        return actions

    # -------------------------------------------------------------------------
    # Docker generation
    # -------------------------------------------------------------------------

    def _generate_docker_files(self, repo_path: Path, primary_lang: str, app_name: str, overwrite: bool = False) -> List[Dict]:
        actions: List[Dict] = []

        dockerfile = DOCKERFILE_TEMPLATES.get(primary_lang, DOCKERFILE_TEMPLATES["Python"])
        actions.append(self._safe_write(repo_path / "Dockerfile", dockerfile, overwrite))
        actions.append(self._safe_write(repo_path / ".dockerignore", DOCKERIGNORE_TEMPLATE, overwrite))

        app_port = "3000" if primary_lang in ("JavaScript", "TypeScript") else "8000"
        compose_content = DOCKER_COMPOSE_TEMPLATE.format(app_name=app_name, app_port=app_port)
        actions.append(self._safe_write(repo_path / "docker-compose.yml", compose_content, overwrite))

        return actions

    # -------------------------------------------------------------------------
    # Pulumi generation (AWS only for now)
    # -------------------------------------------------------------------------

    def _generate_pulumi(self, infra_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        actions: List[Dict] = []
        pulumi_path = infra_path / "pulumi"
        pulumi_path.mkdir(exist_ok=True)

        actions.append(self._safe_write(pulumi_path / "index.ts", PULUMI_INDEX_TS.format(app_name=app_name), overwrite))
        actions.append(self._safe_write(pulumi_path / "Pulumi.yaml", PULUMI_YAML.format(app_name=app_name), overwrite))

        return actions
