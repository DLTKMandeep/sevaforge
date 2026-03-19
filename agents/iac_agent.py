#!/usr/bin/env python3
"""
IAC Agent - Infrastructure as Code Generation
Generates Terraform, Pulumi, Docker configurations

Part of the specialized agent architecture:
- forgeflow iac <path> → iac_mcp → IACAgent
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
# TERRAFORM TEMPLATES
# =============================================================================

TERRAFORM_MAIN = '''# =============================================================================
# ForgeFlow Generated Terraform Configuration
# Generated: {timestamp}
# Provider: {cloud}
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
  
  # Uncomment for remote state (recommended for production)
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

# Configure Kubernetes provider after EKS cluster is created
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

# =============================================================================
# Local Values
# =============================================================================

locals {{
  name_prefix = "${{var.app_name}}-${{var.environment}}"
  
  common_tags = {{
    Application = var.app_name
    Environment = var.environment
  }}
}}

# =============================================================================
# Module References
# =============================================================================

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
  
  app_name           = var.app_name
  environment        = var.environment
  cluster_version    = var.kubernetes_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  
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
  
  app_name         = var.app_name
  environment      = var.environment
  eks_cluster_arn  = module.eks.cluster_arn
  s3_bucket_arns   = module.storage.bucket_arns
  
  depends_on = [module.eks, module.storage]
}}
'''

TERRAFORM_VARIABLES = '''# =============================================================================
# ForgeFlow Generated Variables
# =============================================================================

variable "app_name" {{
  description = "Application name used for resource naming"
  type        = string
  default     = "{app_name}"
}}

variable "environment" {{
  description = "Deployment environment (dev, staging, production)"
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

TERRAFORM_OUTPUTS = '''# =============================================================================
# ForgeFlow Generated Outputs
# =============================================================================

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
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

output "eks_cluster_arn" {
  description = "ARN of the EKS cluster"
  value       = module.eks.cluster_arn
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

# Terraform module templates
TERRAFORM_NETWORK = '''# Network Module - VPC, Subnets, Security Groups
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

output "vpc_id" { value = aws_vpc.main.id }
output "private_subnet_ids" { value = [] }
output "public_subnet_ids" { value = [] }
output "app_security_group_id" { value = "" }
'''

TERRAFORM_CLUSTER = '''# Cluster Module - EKS/Kubernetes
variable "app_name" { type = string }
variable "environment" { type = string }
variable "cluster_version" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "node_instance_types" { type = list(string) }
variable "node_desired_size" { type = number }
variable "node_min_size" { type = number }
variable "node_max_size" { type = number }

output "cluster_name" { value = "" }
output "cluster_endpoint" { value = "" }
output "cluster_arn" { value = "" }
output "cluster_ca_certificate" { value = "" }
output "node_group_arn" { value = "" }
'''

TERRAFORM_STORAGE = '''# Storage Module - S3, EBS
variable "app_name" { type = string }
variable "environment" { type = string }

output "bucket_names" { value = {} }
output "bucket_arns" { value = [] }
'''

TERRAFORM_IAM = '''# IAM Module - Roles and Policies
variable "app_name" { type = string }
variable "environment" { type = string }
variable "eks_cluster_arn" { type = string }
variable "s3_bucket_arns" { type = list(string) }

output "app_role_arn" { value = "" }
output "app_role_name" { value = "" }
output "cicd_role_arn" { value = "" }
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


class IACAgent(BaseAgent):
    """
    Infrastructure as Code Agent - Generates Terraform, Docker, and Pulumi configurations.
    
    Responsibilities:
    - Terraform files (main.tf, variables.tf, outputs.tf)
    - Terraform modules (network, cluster, storage, iam)
    - Dockerfile based on detected language
    - docker-compose.yml for local development
    - Pulumi support (optional)
    - Cloud-specific configs (AWS, GCP, Azure)
    """
    
    def __init__(self):
        super().__init__(
            name="IACAgent",
            description="Generates Infrastructure as Code (Terraform, Docker, Pulumi)"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate infrastructure code based on repository analysis."""
        # Handle params defensively
        if params is None:
            params = {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {"repo_path": params}
        
        repo_path = Path(params.get("repo_path", ".")).resolve()
        cloud = params.get("cloud", "aws").lower()
        include_pulumi = params.get("include_pulumi", False)
        
        self.log(f"Generating IAC for: {repo_path}")
        
        actions = []
        findings = []
        
        # Detect app name and language
        app_name = self._detect_app_name(repo_path)
        primary_lang = self._detect_primary_language(repo_path)
        
        self.log(f"Detected app: {app_name}, language: {primary_lang}")
        
        # Create infrastructure directory
        infra_path = repo_path / "infrastructure"
        infra_path.mkdir(exist_ok=True)
        
        # Generate Terraform
        terraform_actions = self._generate_terraform(infra_path, app_name, cloud)
        actions.extend(terraform_actions)
        
        # Generate Docker files
        docker_actions = self._generate_docker_files(repo_path, primary_lang, app_name)
        actions.extend(docker_actions)
        
        # Generate Pulumi (optional)
        if include_pulumi:
            pulumi_actions = self._generate_pulumi(infra_path, app_name)
            actions.extend(pulumi_actions)
        
        return self.create_result(
            status="success",
            summary=f"Generated IAC artifacts for {app_name}",
            data={
                "app_name": app_name,
                "primary_language": primary_lang,
                "cloud_provider": cloud,
                "infrastructure_path": str(infra_path),
                "files_generated": len(actions),
            },
            findings=findings,
            actions=actions
        )
    
    def _detect_app_name(self, repo_path: Path) -> str:
        """Detect application name from package files or directory."""
        # Check package.json
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                if isinstance(data, dict) and data.get("name"):
                    return data["name"].replace("@", "").replace("/", "-")
            except:
                pass
        
        # Check pyproject.toml
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                for line in content.split("\n"):
                    if line.startswith("name"):
                        name = line.split("=")[1].strip().strip('"\'')
                        if name:
                            return name
            except:
                pass
        
        # Fallback to directory name
        return repo_path.name.lower().replace(" ", "-").replace("_", "-")
    
    def _detect_primary_language(self, repo_path: Path) -> str:
        """Detect primary programming language."""
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".rb": "Ruby",
        }
        
        counts = {}
        for ext, lang in ext_map.items():
            count = len(list(repo_path.rglob(f"*{ext}")))
            if count > 0:
                counts[lang] = count
        
        if counts:
            return max(counts, key=counts.get)
        return "Python"  # Default
    
    def _generate_terraform(self, infra_path: Path, app_name: str, cloud: str) -> List[Dict]:
        """Generate Terraform configuration files."""
        actions = []
        terraform_path = infra_path / "terraform"
        terraform_path.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # main.tf
        main_content = TERRAFORM_MAIN.format(
            timestamp=timestamp,
            app_name=app_name,
            cloud=cloud
        )
        (terraform_path / "main.tf").write_text(main_content)
        actions.append({"action": "created", "file": "infrastructure/terraform/main.tf"})
        
        # variables.tf
        vars_content = TERRAFORM_VARIABLES.format(app_name=app_name)
        (terraform_path / "variables.tf").write_text(vars_content)
        actions.append({"action": "created", "file": "infrastructure/terraform/variables.tf"})
        
        # outputs.tf
        (terraform_path / "outputs.tf").write_text(TERRAFORM_OUTPUTS)
        actions.append({"action": "created", "file": "infrastructure/terraform/outputs.tf"})
        
        # Create modules directory
        modules_path = terraform_path / "modules"
        modules_path.mkdir(exist_ok=True)
        
        # Network module
        network_path = modules_path / "network"
        network_path.mkdir(exist_ok=True)
        (network_path / "main.tf").write_text(TERRAFORM_NETWORK)
        actions.append({"action": "created", "file": "infrastructure/terraform/modules/network/main.tf"})
        
        # Cluster module
        cluster_path = modules_path / "cluster"
        cluster_path.mkdir(exist_ok=True)
        (cluster_path / "main.tf").write_text(TERRAFORM_CLUSTER)
        actions.append({"action": "created", "file": "infrastructure/terraform/modules/cluster/main.tf"})
        
        # Storage module
        storage_path = modules_path / "storage"
        storage_path.mkdir(exist_ok=True)
        (storage_path / "main.tf").write_text(TERRAFORM_STORAGE)
        actions.append({"action": "created", "file": "infrastructure/terraform/modules/storage/main.tf"})
        
        # IAM module
        iam_path = modules_path / "iam"
        iam_path.mkdir(exist_ok=True)
        (iam_path / "main.tf").write_text(TERRAFORM_IAM)
        actions.append({"action": "created", "file": "infrastructure/terraform/modules/iam/main.tf"})
        
        return actions
    
    def _generate_docker_files(self, repo_path: Path, primary_lang: str, app_name: str) -> List[Dict]:
        """Generate Docker-related files."""
        actions = []
        
        # Dockerfile
        dockerfile = DOCKERFILE_TEMPLATES.get(primary_lang, DOCKERFILE_TEMPLATES["Python"])
        (repo_path / "Dockerfile").write_text(dockerfile)
        actions.append({"action": "created", "file": "Dockerfile"})
        
        # .dockerignore
        (repo_path / ".dockerignore").write_text(DOCKERIGNORE_TEMPLATE)
        actions.append({"action": "created", "file": ".dockerignore"})
        
        # docker-compose.yml
        app_port = "3000" if primary_lang in ["JavaScript", "TypeScript"] else "8000"
        compose_content = DOCKER_COMPOSE_TEMPLATE.format(
            app_name=app_name,
            app_port=app_port
        )
        (repo_path / "docker-compose.yml").write_text(compose_content)
        actions.append({"action": "created", "file": "docker-compose.yml"})
        
        return actions
    
    def _generate_pulumi(self, infra_path: Path, app_name: str) -> List[Dict]:
        """Generate Pulumi configuration files."""
        actions = []
        pulumi_path = infra_path / "pulumi"
        pulumi_path.mkdir(exist_ok=True)
        
        # index.ts
        (pulumi_path / "index.ts").write_text(PULUMI_INDEX_TS.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/pulumi/index.ts"})
        
        # Pulumi.yaml
        (pulumi_path / "Pulumi.yaml").write_text(PULUMI_YAML.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/pulumi/Pulumi.yaml"})
        
        return actions
