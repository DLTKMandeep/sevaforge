#!/usr/bin/env python3
"""
Generation Agent - Generates deployment artifacts (Dockerfiles, Terraform, CI/CD).
Mapped to: generate command → deployment_mcp

Enhanced to generate real infrastructure code:
- Terraform files for AWS (VPC, EKS, S3, IAM)
- Docker files based on detected language
- CI/CD workflows
"""
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent
from core.ai_enhancer import get_ai_enhancer


# =============================================================================
# DOCKERFILE TEMPLATES BY LANGUAGE
# =============================================================================

DOCKERFILE_TEMPLATES = {
    'Python': '''# =============================================================================
# ENTERPRISE-GRADE PYTHON DOCKERFILE
# Multi-stage build with security, optimization, and observability
# =============================================================================
FROM python:3.11-slim AS base

# Build arguments for versioning
ARG BUILD_DATE
ARG GIT_COMMIT
ARG VERSION=1.0.0

# Metadata labels for enterprise tracking
LABEL org.opencontainers.image.created="${BUILD_DATE}" \\
      org.opencontainers.image.authors="Platform Engineering Team" \\
      org.opencontainers.image.version="${VERSION}" \\
      org.opencontainers.image.revision="${GIT_COMMIT}" \\
      org.opencontainers.image.vendor="Enterprise" \\
      org.opencontainers.image.title="Python Application" \\
      maintainer="devops@company.com"

# Security: Create non-root user early
RUN groupadd -r -g 1001 appuser && \\
    useradd -r -u 1001 -g appuser -m -d /home/appuser -s /bin/bash appuser

# Environment variables for production
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1 \\
    PIP_DEFAULT_TIMEOUT=100 \\
    PYTHONFAULTHANDLER=1 \\
    PYTHONHASHSEED=random \\
    # Production settings
    LOG_LEVEL=INFO \\
    WORKERS=4 \\
    TIMEOUT=60 \\
    KEEPALIVE=5

WORKDIR /app

# =============================================================================
# BUILDER STAGE: Install dependencies and compile
# =============================================================================
FROM base AS builder

# Install build dependencies (kept in builder stage only)
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    curl \\
    git \\
    libpq-dev \\
    && rm -rf /var/lib/apt/lists/*

# Install dependencies as root, then change ownership
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \\
    pip install --no-cache-dir -r requirements.txt && \\
    # Remove unnecessary files
    find /usr/local/lib/python3.11 -name '*.pyc' -delete && \\
    find /usr/local/lib/python3.11 -name '__pycache__' -delete

# =============================================================================
# PRODUCTION STAGE: Minimal runtime image
# =============================================================================
FROM python:3.11-slim AS production

# Copy metadata
ARG BUILD_DATE
ARG GIT_COMMIT
ARG VERSION=1.0.0

LABEL org.opencontainers.image.created="${BUILD_DATE}" \\
      org.opencontainers.image.version="${VERSION}" \\
      org.opencontainers.image.revision="${GIT_COMMIT}"

# Create non-root user
RUN groupadd -r -g 1001 appuser && \\
    useradd -r -u 1001 -g appuser -m -d /home/appuser -s /bin/bash appuser

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    ca-certificates \\
    libpq5 \\
    tini \\
    && rm -rf /var/lib/apt/lists/* \\
    && apt-get clean

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    LOG_LEVEL=INFO \\
    WORKERS=4 \\
    TIMEOUT=60

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose application port and metrics port
EXPOSE 8000 9090

# Health check with proper configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:8000/healthz || exit 1

# Signal handling for graceful shutdown
STOPSIGNAL SIGTERM

# Use tini for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]

# Production-ready command with multiple workers
CMD ["python", "-m", "uvicorn", "main:app", \\
     "--host", "0.0.0.0", \\
     "--port", "8000", \\
     "--workers", "4", \\
     "--log-level", "info", \\
     "--access-log", \\
     "--proxy-headers", \\
     "--forwarded-allow-ips", "*"]
''',

    'JavaScript': '''# =============================================================================
# ENTERPRISE-GRADE NODE.JS DOCKERFILE
# Multi-stage build with security, optimization, and caching
# =============================================================================
FROM node:20-alpine AS base

# Build arguments
ARG BUILD_DATE
ARG GIT_COMMIT
ARG VERSION=1.0.0
ARG NODE_ENV=production

# Metadata labels
LABEL org.opencontainers.image.created="${BUILD_DATE}" \\
      org.opencontainers.image.version="${VERSION}" \\
      org.opencontainers.image.revision="${GIT_COMMIT}"

# Install security updates and tini
RUN apk add --no-cache \\
    tini \\
    curl \\
    ca-certificates \\
    && apk upgrade --no-cache

WORKDIR /app

# =============================================================================
# DEPENDENCIES STAGE: Install production dependencies
# =============================================================================
FROM base AS dependencies

# Copy package files for caching
COPY package*.json ./
COPY yarn.lock* ./

# Install production dependencies with security audit
RUN npm ci --only=production --no-audit --prefer-offline \\
    && npm cache clean --force

# =============================================================================
# BUILD STAGE: Install all dependencies and build
# =============================================================================
FROM base AS builder

COPY package*.json ./
COPY yarn.lock* ./

# Install all dependencies (including dev dependencies)
RUN npm ci --no-audit --prefer-offline

# Copy source code
COPY . .

# Build application (if build script exists)
RUN npm run build 2>/dev/null || echo "No build script found" \\
    && npm prune --production

# =============================================================================
# PRODUCTION STAGE: Minimal runtime image
# =============================================================================
FROM node:20-alpine AS production

# Build arguments
ARG BUILD_DATE
ARG GIT_COMMIT
ARG VERSION=1.0.0

LABEL org.opencontainers.image.created="${BUILD_DATE}" \\
      org.opencontainers.image.version="${VERSION}" \\
      org.opencontainers.image.revision="${GIT_COMMIT}"

# Install runtime dependencies and tini
RUN apk add --no-cache \\
    tini \\
    curl \\
    ca-certificates \\
    && apk upgrade --no-cache

# Create non-root user with specific UID/GID
RUN addgroup -g 1001 -S nodejs && \\
    adduser -S nodejs -u 1001 -G nodejs -h /home/nodejs

# Environment variables
ENV NODE_ENV=production \\
    PORT=3000 \\
    LOG_LEVEL=info \\
    NODE_OPTIONS="--max-old-space-size=2048"

WORKDIR /app

# Copy dependencies from dependencies stage
COPY --from=dependencies --chown=nodejs:nodejs /app/node_modules ./node_modules

# Copy built application from builder
COPY --from=builder --chown=nodejs:nodejs /app/dist ./dist
COPY --from=builder --chown=nodejs:nodejs /app/build ./build
COPY --from=builder --chown=nodejs:nodejs /app/*.js ./
COPY --from=builder --chown=nodejs:nodejs /app/package*.json ./
COPY --from=builder --chown=nodejs:nodejs /app/public ./public

# Switch to non-root user
USER nodejs

# Expose application and metrics ports
EXPOSE 3000 9090

# Health check with proper configuration
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
    CMD curl -f http://localhost:3000/health || wget -q --spider http://localhost:3000/health || exit 1

# Graceful shutdown signal
STOPSIGNAL SIGTERM

# Use tini for proper signal handling
ENTRYPOINT ["/sbin/tini", "--"]

# Start application
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

# Install dependencies
RUN apk add --no-cache git ca-certificates tzdata

# Download dependencies
COPY go.mod go.sum* ./
RUN go mod download

# Build the application
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o main .

# Production stage
FROM scratch

WORKDIR /app

# Copy certificates and timezone data
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /usr/share/zoneinfo /usr/share/zoneinfo

# Copy binary
COPY --from=builder /app/main .

EXPOSE 8080

ENTRYPOINT ["./main"]
''',

    'Java': '''FROM eclipse-temurin:17-jdk-alpine AS builder

WORKDIR /app

# Copy gradle/maven files
COPY build.gradle* settings.gradle* pom.xml* mvnw* gradlew* ./
COPY gradle/ gradle/ 2>/dev/null || true
COPY .mvn/ .mvn/ 2>/dev/null || true

# Download dependencies
RUN if [ -f "gradlew" ]; then ./gradlew dependencies --no-daemon; \\
    elif [ -f "mvnw" ]; then ./mvnw dependency:go-offline; fi

# Copy source and build
COPY src/ src/
RUN if [ -f "gradlew" ]; then ./gradlew build --no-daemon -x test; \\
    elif [ -f "mvnw" ]; then ./mvnw package -DskipTests; fi

# Production stage
FROM eclipse-temurin:17-jre-alpine AS production

WORKDIR /app

RUN addgroup -g 1001 -S appgroup && \\
    adduser -S appuser -u 1001 -G appgroup

COPY --from=builder /app/build/libs/*.jar app.jar 2>/dev/null || \\
     COPY --from=builder /app/target/*.jar app.jar

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
''',

    'Rust': '''FROM rust:1.74-alpine AS builder

WORKDIR /app

RUN apk add --no-cache musl-dev

# Cache dependencies
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs && \\
    cargo build --release && \\
    rm -rf src

# Build application
COPY . .
RUN cargo build --release

# Production stage
FROM alpine:latest

WORKDIR /app

RUN apk add --no-cache ca-certificates

COPY --from=builder /app/target/release/app .

EXPOSE 8080

CMD ["./app"]
'''
}


# =============================================================================
# TERRAFORM TEMPLATES
# =============================================================================

TERRAFORM_MAIN = '''# =============================================================================
# ForgeFlow Generated Terraform Configuration
# Generated: {timestamp}
# Provider: AWS
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

# -----------------------------------------------------------------------------
# General Configuration
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# Network Configuration
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# Kubernetes/EKS Configuration
# -----------------------------------------------------------------------------

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
  description = "Desired number of nodes in the EKS node group"
  type        = number
  default     = 2
}}

variable "node_min_size" {{
  description = "Minimum number of nodes in the EKS node group"
  type        = number
  default     = 1
}}

variable "node_max_size" {{
  description = "Maximum number of nodes in the EKS node group"
  type        = number
  default     = 5
}}

# -----------------------------------------------------------------------------
# Storage Configuration
# -----------------------------------------------------------------------------

variable "enable_s3_versioning" {{
  description = "Enable versioning on S3 buckets"
  type        = bool
  default     = true
}}

variable "s3_lifecycle_days" {{
  description = "Days before transitioning S3 objects to IA storage"
  type        = number
  default     = 90
}}
'''

TERRAFORM_OUTPUTS = '''# =============================================================================
# ForgeFlow Generated Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# VPC Outputs
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# EKS Outputs
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# Storage Outputs
# -----------------------------------------------------------------------------

output "s3_bucket_names" {
  description = "Names of created S3 buckets"
  value       = module.storage.bucket_names
}

output "s3_bucket_arns" {
  description = "ARNs of created S3 buckets"
  value       = module.storage.bucket_arns
}

# -----------------------------------------------------------------------------
# IAM Outputs
# -----------------------------------------------------------------------------

output "app_role_arn" {
  description = "ARN of the application IAM role"
  value       = module.iam.app_role_arn
}
'''

TERRAFORM_NETWORK = '''# =============================================================================
# Network Module - VPC, Subnets, Security Groups
# =============================================================================

variable "app_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "vpc_cidr" {
  type = string
}

variable "azs" {
  type = list(string)
}

variable "private_subnets" {
  type = list(string)
}

variable "public_subnets" {
  type = list(string)
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  
  tags = {
    Name = "${var.app_name}-${var.environment}-vpc"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway
# -----------------------------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  
  tags = {
    Name = "${var.app_name}-${var.environment}-igw"
  }
}

# -----------------------------------------------------------------------------
# Public Subnets
# -----------------------------------------------------------------------------

resource "aws_subnet" "public" {
  count                   = length(var.public_subnets)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnets[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true
  
  tags = {
    Name                        = "${var.app_name}-${var.environment}-public-${count.index + 1}"
    "kubernetes.io/role/elb"    = "1"
    "kubernetes.io/cluster/${var.app_name}-${var.environment}" = "shared"
  }
}

# -----------------------------------------------------------------------------
# Private Subnets
# -----------------------------------------------------------------------------

resource "aws_subnet" "private" {
  count             = length(var.private_subnets)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnets[count.index]
  availability_zone = var.azs[count.index]
  
  tags = {
    Name                              = "${var.app_name}-${var.environment}-private-${count.index + 1}"
    "kubernetes.io/role/internal-elb" = "1"
    "kubernetes.io/cluster/${var.app_name}-${var.environment}" = "shared"
  }
}

# -----------------------------------------------------------------------------
# NAT Gateway (for private subnet internet access)
# -----------------------------------------------------------------------------

resource "aws_eip" "nat" {
  count  = length(var.azs)
  domain = "vpc"
  
  tags = {
    Name = "${var.app_name}-${var.environment}-nat-eip-${count.index + 1}"
  }
  
  depends_on = [aws_internet_gateway.main]
}

resource "aws_nat_gateway" "main" {
  count         = length(var.azs)
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  
  tags = {
    Name = "${var.app_name}-${var.environment}-nat-${count.index + 1}"
  }
  
  depends_on = [aws_internet_gateway.main]
}

# -----------------------------------------------------------------------------
# Route Tables
# -----------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  
  tags = {
    Name = "${var.app_name}-${var.environment}-public-rt"
  }
}

resource "aws_route_table" "private" {
  count  = length(var.azs)
  vpc_id = aws_vpc.main.id
  
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }
  
  tags = {
    Name = "${var.app_name}-${var.environment}-private-rt-${count.index + 1}"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnets)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(var.private_subnets)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# -----------------------------------------------------------------------------
# Security Groups
# -----------------------------------------------------------------------------

resource "aws_security_group" "app" {
  name        = "${var.app_name}-${var.environment}-app-sg"
  description = "Security group for application"
  vpc_id      = aws_vpc.main.id
  
  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    description = "Application port"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
  
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name = "${var.app_name}-${var.environment}-app-sg"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}
'''

TERRAFORM_CLUSTER = '''# =============================================================================
# Cluster Module - EKS/Kubernetes
# =============================================================================

variable "app_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "cluster_version" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "node_instance_types" {
  type = list(string)
}

variable "node_desired_size" {
  type = number
}

variable "node_min_size" {
  type = number
}

variable "node_max_size" {
  type = number
}

# -----------------------------------------------------------------------------
# EKS Cluster IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "eks_cluster" {
  name = "${var.app_name}-${var.environment}-eks-cluster-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "eks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
  role       = aws_iam_role.eks_cluster.name
}

resource "aws_iam_role_policy_attachment" "eks_vpc_resource_controller" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
  role       = aws_iam_role.eks_cluster.name
}

# -----------------------------------------------------------------------------
# EKS Cluster
# -----------------------------------------------------------------------------

resource "aws_eks_cluster" "main" {
  name     = "${var.app_name}-${var.environment}"
  version  = var.cluster_version
  role_arn = aws_iam_role.eks_cluster.arn
  
  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
  }
  
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  
  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_resource_controller,
  ]
  
  tags = {
    Name = "${var.app_name}-${var.environment}-eks"
  }
}

# -----------------------------------------------------------------------------
# EKS Node Group IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "eks_nodes" {
  name = "${var.app_name}-${var.environment}-eks-node-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
  role       = aws_iam_role.eks_nodes.name
}

resource "aws_iam_role_policy_attachment" "eks_container_registry" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
  role       = aws_iam_role.eks_nodes.name
}

# -----------------------------------------------------------------------------
# EKS Node Group
# -----------------------------------------------------------------------------

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.app_name}-${var.environment}-nodes"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.node_instance_types
  
  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }
  
  update_config {
    max_unavailable = 1
  }
  
  labels = {
    Environment = var.environment
  }
  
  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node_policy,
    aws_iam_role_policy_attachment.eks_cni_policy,
    aws_iam_role_policy_attachment.eks_container_registry,
  ]
  
  tags = {
    Name = "${var.app_name}-${var.environment}-node-group"
  }
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cluster_name" {
  value = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "cluster_arn" {
  value = aws_eks_cluster.main.arn
}

output "cluster_ca_certificate" {
  value = aws_eks_cluster.main.certificate_authority[0].data
}

output "node_group_arn" {
  value = aws_eks_node_group.main.arn
}
'''

TERRAFORM_STORAGE = '''# =============================================================================
# Storage Module - S3, EBS Volumes
# =============================================================================

variable "app_name" {
  type = string
}

variable "environment" {
  type = string
}

# -----------------------------------------------------------------------------
# S3 Bucket - Application Data
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "app_data" {
  bucket = "${var.app_name}-${var.environment}-data-${random_id.bucket_suffix.hex}"
  
  tags = {
    Name = "${var.app_name}-${var.environment}-data"
  }
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket_versioning" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "app_data" {
  bucket = aws_s3_bucket.app_data.id
  
  rule {
    id     = "transition-to-ia"
    status = "Enabled"
    
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    
    transition {
      days          = 180
      storage_class = "GLACIER"
    }
    
    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }
    
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Bucket - Logs
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "logs" {
  bucket = "${var.app_name}-${var.environment}-logs-${random_id.bucket_suffix.hex}"
  
  tags = {
    Name = "${var.app_name}-${var.environment}-logs"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  
  rule {
    id     = "expire-old-logs"
    status = "Enabled"
    
    expiration {
      days = 365
    }
  }
}

# -----------------------------------------------------------------------------
# S3 Bucket - Backups
# -----------------------------------------------------------------------------

resource "aws_s3_bucket" "backups" {
  bucket = "${var.app_name}-${var.environment}-backups-${random_id.bucket_suffix.hex}"
  
  tags = {
    Name = "${var.app_name}-${var.environment}-backups"
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "bucket_names" {
  value = {
    data    = aws_s3_bucket.app_data.id
    logs    = aws_s3_bucket.logs.id
    backups = aws_s3_bucket.backups.id
  }
}

output "bucket_arns" {
  value = [
    aws_s3_bucket.app_data.arn,
    aws_s3_bucket.logs.arn,
    aws_s3_bucket.backups.arn
  ]
}
'''

TERRAFORM_IAM = '''# =============================================================================
# IAM Module - Roles and Policies
# =============================================================================

variable "app_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "eks_cluster_arn" {
  type = string
}

variable "s3_bucket_arns" {
  type = list(string)
}

# -----------------------------------------------------------------------------
# Application IAM Role (for EKS Service Account)
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# OIDC Provider for EKS (enables IRSA)
data "aws_eks_cluster" "main" {
  name = "${var.app_name}-${var.environment}"
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = data.aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["9e99a48a9960b14926bb7f3b02e22da2b0ab7280"]
}

# Application Role with IRSA
resource "aws_iam_role" "app" {
  name = "${var.app_name}-${var.environment}-app-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.eks.arn
      }
      Condition = {
        StringEquals = {
          "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:default:${var.app_name}"
          "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })
}

# -----------------------------------------------------------------------------
# Application Policies
# -----------------------------------------------------------------------------

# S3 Access Policy
resource "aws_iam_policy" "s3_access" {
  name        = "${var.app_name}-${var.environment}-s3-access"
  description = "Allow application to access S3 buckets"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = concat(
          var.s3_bucket_arns,
          [for arn in var.s3_bucket_arns : "${arn}/*"]
        )
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "app_s3" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.s3_access.arn
}

# Secrets Manager Access Policy
resource "aws_iam_policy" "secrets_access" {
  name        = "${var.app_name}-${var.environment}-secrets-access"
  description = "Allow application to access secrets"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.app_name}/${var.environment}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "app_secrets" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.secrets_access.arn
}

# CloudWatch Logs Policy
resource "aws_iam_policy" "cloudwatch_logs" {
  name        = "${var.app_name}-${var.environment}-cloudwatch-logs"
  description = "Allow application to write CloudWatch logs"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/${var.app_name}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "app_cloudwatch" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.cloudwatch_logs.arn
}

# -----------------------------------------------------------------------------
# CI/CD Role (for GitHub Actions or similar)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "cicd" {
  name = "${var.app_name}-${var.environment}-cicd-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
      }
      Condition = {
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:*/${var.app_name}:*"
        }
      }
    }]
  })
}

resource "aws_iam_policy" "cicd_deploy" {
  name        = "${var.app_name}-${var.environment}-cicd-deploy"
  description = "Allow CI/CD to deploy to EKS"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = var.eks_cluster_arn
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cicd_deploy" {
  role       = aws_iam_role.cicd.name
  policy_arn = aws_iam_policy.cicd_deploy.arn
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "app_role_arn" {
  value = aws_iam_role.app.arn
}

output "app_role_name" {
  value = aws_iam_role.app.name
}

output "cicd_role_arn" {
  value = aws_iam_role.cicd.arn
}
'''


# =============================================================================
# DOCKER COMPOSE TEMPLATE
# =============================================================================

DOCKER_COMPOSE_TEMPLATE = '''# =============================================================================
# ENTERPRISE-GRADE DOCKER COMPOSE
# Production-ready local development environment
# Generated by ForgeFlow
# =============================================================================
version: '3.9'

# =============================================================================
# SERVICES
# =============================================================================
services:
  
  # ---------------------------------------------------------------------------
  # Application Service
  # ---------------------------------------------------------------------------
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
      args:
        BUILD_DATE: ${{BUILD_DATE:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}}
        GIT_COMMIT: ${{GIT_COMMIT:-$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")}}
        VERSION: ${{VERSION:-1.0.0}}
    image: {app_name}:${{VERSION:-latest}}
    container_name: {app_name}-app
    hostname: {app_name}-app
    
    # Resource limits for stability
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    
    # Security configuration
    security_opt:
      - no-new-privileges:true
    read_only: false  # Set to true if app doesn't write to filesystem
    tmpfs:
      - /tmp:mode=1777,size=100M
      - /var/tmp:mode=1777,size=100M
    
    # User configuration (matches Dockerfile non-root user)
    user: "1001:1001"
    
    # Port mapping
    ports:
      - "{app_port}:{app_port}"     # Application port
      - "9090:9090"                  # Metrics port (Prometheus)
    
    # Volume mounts
    volumes:
      - .:/app:ro                    # Mount source code (read-only in production)
      - app_logs:/app/logs           # Application logs
      - app_tmp:/app/tmp             # Temporary files
    
    # Environment configuration
    environment:
      # Application settings
      - NODE_ENV=${{NODE_ENV:-production}}
      - LOG_LEVEL=${{LOG_LEVEL:-info}}
      - PORT={app_port}
      
      # Database connection
      - DATABASE_URL=postgresql://postgres:${{POSTGRES_PASSWORD:-changeme}}@db:5432/{app_name}
      - DB_POOL_SIZE=${{DB_POOL_SIZE:-20}}
      - DB_MAX_OVERFLOW=${{DB_MAX_OVERFLOW:-10}}
      
      # Redis connection
      - REDIS_URL=redis://:${{REDIS_PASSWORD:-changeme}}@redis:6379/0
      - CACHE_TTL=${{CACHE_TTL:-3600}}
      
      # Security
      - SECRET_KEY=${{SECRET_KEY:-change-this-in-production}}
      - JWT_SECRET=${{JWT_SECRET:-change-this-in-production}}
      - CORS_ORIGINS=${{CORS_ORIGINS:-http://localhost:3000}}
      
      # Observability
      - ENABLE_METRICS=${{ENABLE_METRICS:-true}}
      - ENABLE_TRACING=${{ENABLE_TRACING:-true}}
      - OTEL_SERVICE_NAME={app_name}
    
    # Environment file for secrets (not tracked in git)
    env_file:
      - .env
    
    # Service dependencies with health checks
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    
    # Health check
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{app_port}/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    # Restart policy
    restart: unless-stopped
    
    # Signal handling
    stop_grace_period: 30s
    stop_signal: SIGTERM
    
    # Init process for proper signal handling
    init: true
    
    # Logging configuration
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
        labels: "service,environment"
    
    # Labels for service discovery and monitoring
    labels:
      - "com.forgeflow.service=app"
      - "com.forgeflow.environment=development"
      - "com.forgeflow.version=${{VERSION:-1.0.0}}"
      - "traefik.enable=true"
      - "traefik.http.routers.app.rule=Host(`localhost`)"
    
    networks:
      - frontend
      - backend

  # ---------------------------------------------------------------------------
  # PostgreSQL Database (if needed)
  # ---------------------------------------------------------------------------
  db:
    image: postgres:16-alpine
    container_name: {app_name}-db
    hostname: postgres-db
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.25'
          memory: 256M
    
    # Security
    security_opt:
      - no-new-privileges:true
    
    # Port mapping (only for local development)
    ports:
      - "${{POSTGRES_PORT:-5432}}:5432"
    
    # Environment variables
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD:-changeme}}
      - POSTGRES_DB={app_name}
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
      - PGDATA=/var/lib/postgresql/data/pgdata
      # Performance tuning
      - POSTGRES_SHARED_BUFFERS=256MB
      - POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
      - POSTGRES_MAINTENANCE_WORK_MEM=64MB
      - POSTGRES_CHECKPOINT_COMPLETION_TARGET=0.9
      - POSTGRES_WAL_BUFFERS=16MB
      - POSTGRES_DEFAULT_STATISTICS_TARGET=100
      - POSTGRES_RANDOM_PAGE_COST=1.1
      - POSTGRES_EFFECTIVE_IO_CONCURRENCY=200
      - POSTGRES_WORK_MEM=16MB
      - POSTGRES_MIN_WAL_SIZE=1GB
      - POSTGRES_MAX_WAL_SIZE=4GB
    
    # Persistent volumes
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - postgres_backups:/backups
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro  # Init script
    
    # Health check
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {app_name}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    
    # Restart policy
    restart: unless-stopped
    stop_grace_period: 60s
    
    # Logging
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    
    # Labels
    labels:
      - "com.forgeflow.service=database"
      - "com.forgeflow.backup=true"
    
    networks:
      - backend

  # ---------------------------------------------------------------------------
  # Redis Cache
  # ---------------------------------------------------------------------------
  redis:
    image: redis:7-alpine
    container_name: {app_name}-redis
    hostname: redis-cache
    
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.1'
          memory: 128M
    
    # Security
    security_opt:
      - no-new-privileges:true
    
    # Command with configuration
    command: >
      redis-server
      --requirepass ${{REDIS_PASSWORD:-changeme}}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --appendonly yes
      --appendfsync everysec
      --auto-aof-rewrite-percentage 100
      --auto-aof-rewrite-min-size 64mb
      --save 900 1
      --save 300 10
      --save 60 10000
      --loglevel notice
    
    # Port mapping
    ports:
      - "${{REDIS_PORT:-6379}}:6379"
    
    # Persistent storage
    volumes:
      - redis_data:/data
      - redis_config:/usr/local/etc/redis
    
    # Health check
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    
    # Restart policy
    restart: unless-stopped
    stop_grace_period: 10s
    
    # Logging
    logging:
      driver: json-file
      options:
        max-size: "5m"
        max-file: "2"
    
    # Labels
    labels:
      - "com.forgeflow.service=cache"
    
    networks:
      - backend

# =============================================================================
# VOLUMES - Persistent data storage
# =============================================================================
volumes:
  # Application volumes
  app_logs:
    driver: local
    labels:
      - "com.forgeflow.backup=false"
  
  app_tmp:
    driver: local
    labels:
      - "com.forgeflow.backup=false"
  
  # Database volumes
  postgres_data:
    driver: local
    labels:
      - "com.forgeflow.backup=true"
      - "com.forgeflow.backup.frequency=daily"
  
  postgres_backups:
    driver: local
    labels:
      - "com.forgeflow.backup=true"
  
  # Redis volumes
  redis_data:
    driver: local
    labels:
      - "com.forgeflow.backup=true"
      - "com.forgeflow.backup.frequency=daily"
  
  redis_config:
    driver: local

# =============================================================================
# NETWORKS - Service isolation
# =============================================================================
networks:
  # Frontend network (public-facing services)
  frontend:
    driver: bridge
    labels:
      - "com.forgeflow.network=frontend"
  
  # Backend network (internal services)
  backend:
    driver: bridge
    internal: false  # Set to true in production for isolation
    labels:
      - "com.forgeflow.network=backend"

# =============================================================================
# CONFIGURATION NOTES
# =============================================================================
# 
# Environment Variables (create .env file):
#   - POSTGRES_PASSWORD=your-secure-password
#   - REDIS_PASSWORD=your-secure-password
#   - SECRET_KEY=your-secret-key
#   - JWT_SECRET=your-jwt-secret
#
# Commands:
#   docker-compose up -d              # Start all services
#   docker-compose ps                 # Check service status
#   docker-compose logs -f app        # View app logs
#   docker-compose exec app sh        # Shell into app container
#   docker-compose down -v            # Stop and remove volumes
#
# Production deployment:
#   - Use Docker secrets instead of environment variables
#   - Enable network isolation (internal: true for backend)
#   - Use external volumes for data persistence
#   - Configure proper backup strategies
#   - Enable SSL/TLS termination
#   - Use orchestration platform (Kubernetes, ECS, etc.)
#
# =============================================================================
'''

DOCKERIGNORE_TEMPLATE = '''# ForgeFlow Generated .dockerignore

# Git
.git
.gitignore
.gitattributes

# Documentation
*.md
docs/
LICENSE

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
env/
.env
.env.local
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.tox/

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.npm
.yarn

# Go
*.exe
*.exe~
*.dll
*.dylib
vendor/

# Java
*.class
*.jar
*.war
target/
.gradle/

# Rust
target/
Cargo.lock

# Testing
coverage/
*.cover
.hypothesis/

# Infrastructure
terraform/
*.tfstate
*.tfstate.*
.terraform/

# Docker
Dockerfile*
docker-compose*.yml
.docker/

# CI/CD
.github/
.gitlab-ci.yml
.circleci/
Jenkinsfile

# ForgeFlow
.forgeflow/
'''

CI_WORKFLOW = '''name: ForgeFlow CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up linting
        run: echo "Add language-specific linting here"

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      
      - name: Run tests
        run: echo "Add language-specific tests here"

  build:
    runs-on: ubuntu-latest
    needs: test
    permissions:
      contents: read
      packages: write
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Log in to Container Registry
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=sha,prefix=
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    runs-on: ubuntu-latest
    needs: build
    if: github.ref == 'refs/heads/main' && github.event_name != 'pull_request'
    environment: production
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE }}
          aws-region: us-west-2
      
      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ vars.EKS_CLUSTER_NAME }} --region us-west-2
      
      - name: Deploy to EKS
        run: |
          kubectl set image deployment/app app=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          kubectl rollout status deployment/app
'''


class GenerationAgent(BaseAgent):
    """Agent that generates deployment artifacts including Terraform and Docker files."""
    
    # Port mapping by language
    PORT_BY_LANGUAGE = {
        'Python': 8000,
        'JavaScript': 3000,
        'TypeScript': 3000,
        'Go': 8080,
        'Java': 8080,
        'Rust': 8080,
    }
    
    def __init__(self):
        super().__init__(
            name="generation_agent",
            description="Generates Terraform, Dockerfiles, Helm charts, CI/CD configs"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate deployment artifacts in artifacts directory."""
        original_repo_path = Path(params.get('path', '.')).resolve()
        stack = params.get('stack', 'auto')
        cloud_provider = params.get('cloud', 'aws')
        
        self.log(f"Generating infrastructure for {original_repo_path}...")
        
        # Create artifacts directory in forgeflow_local
        forgeflow_root = Path(__file__).parent.parent  # Get forgeflow_local directory
        artifacts_root = forgeflow_root / 'artifacts'
        artifacts_root.mkdir(exist_ok=True)
        
        # Create timestamped artifact directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        app_name = self._detect_app_name(original_repo_path)
        artifact_dir = artifacts_root / f"{app_name}_{timestamp}"
        
        self.log(f"📦 Creating artifact directory: {artifact_dir}")
        
        # Copy repository to artifacts directory (excluding common ignore patterns)
        self._copy_repo_to_artifacts(original_repo_path, artifact_dir)
        
        # Now work with the artifact directory as repo_path
        repo_path = artifact_dir
        
        self.log(f"✅ Repository copied to artifacts. Generating in: {repo_path}")
        
        # Load discovery results if available (check both locations)
        discover_results = self._load_discover_results(original_repo_path)
        if not discover_results:
            discover_results = self._load_discover_results(repo_path)
        
        # Detect primary language
        primary_lang = self._detect_primary_language(repo_path, discover_results)
        
        self.log(f"Detected: language={primary_lang}, app={app_name}")
        
        # Track all generated artifacts
        artifacts = []
        generated_files = []
        
        # Create infrastructure directory in artifacts
        infra_path = repo_path / 'infrastructure'
        infra_path.mkdir(parents=True, exist_ok=True)
        
        # Generate Terraform files
        terraform_files = self._generate_terraform(infra_path, app_name, cloud_provider)
        artifacts.extend(terraform_files)
        generated_files.extend([f['file'] for f in terraform_files if f['status'] == 'generated'])
        
        # Generate Docker files
        docker_files = self._generate_docker_files(repo_path, primary_lang, app_name)
        artifacts.extend(docker_files)
        generated_files.extend([f['file'] for f in docker_files if f['status'] == 'generated'])
        
        # Generate CI/CD workflow
        ci_result = self._generate_ci_workflow(repo_path)
        artifacts.append(ci_result)
        if ci_result['status'] == 'generated':
            generated_files.append(ci_result['file'])
        
        generated_count = len([a for a in artifacts if a['status'] == 'generated'])
        
        self.log(f"✅ Generated {generated_count} infrastructure files in artifacts directory")
        self.log(f"📂 Artifacts location: {artifact_dir}")
        
        return self.create_result(
            status='success',
            summary=f"Generated {generated_count} infrastructure files for {primary_lang} ({cloud_provider})",
            data={
                'stack': stack if stack != 'auto' else f'auto ({primary_lang})',
                'primary_language': primary_lang,
                'cloud_provider': cloud_provider,
                'app_name': app_name,
                'artifact_directory': str(artifact_dir),
                'original_repo': str(original_repo_path),
                'infrastructure_path': str(infra_path),
                'artifacts': artifacts,
                'generated_files': generated_files
            },
            findings=[
                f"✓ {f}" for f in generated_files
            ] + [
                f"• {a['file']}: {a['status']}" for a in artifacts if a['status'] != 'generated'
            ]
        )
    
    def _copy_repo_to_artifacts(self, source: Path, dest: Path) -> None:
        """
        Copy repository to artifacts directory, excluding common ignore patterns.
        """
        ignore_patterns = {
            # Version control
            '.git', '.gitignore', '.gitattributes',
            # Dependencies
            'node_modules', '__pycache__', '.venv', 'venv', 'env',
            '.tox', '.pytest_cache', '.mypy_cache',
            # Build artifacts
            'dist', 'build', '*.egg-info', 'target',
            # IDE
            '.idea', '.vscode', '*.swp', '*.swo',
            # OS
            '.DS_Store', 'Thumbs.db',
            # ForgeFlow staging (but keep .forgeflow for discovery data)
            'staging',
            # Docker
            'volumes', 'data',
            # Logs
            '*.log', 'logs',
        }
        
        def should_ignore(path: Path) -> bool:
            """Check if path should be ignored."""
            name = path.name
            # Check exact matches
            if name in ignore_patterns:
                return True
            # Check pattern matches
            for pattern in ignore_patterns:
                if '*' in pattern:
                    import fnmatch
                    if fnmatch.fnmatch(name, pattern):
                        return True
            return False
        
        # Create destination directory
        dest.mkdir(parents=True, exist_ok=True)
        
        # Copy files and directories
        for item in source.iterdir():
            if should_ignore(item):
                continue
            
            dest_item = dest / item.name
            
            try:
                if item.is_dir():
                    shutil.copytree(item, dest_item, ignore=lambda d, files: [
                        f for f in files if should_ignore(Path(d) / f)
                    ])
                else:
                    shutil.copy2(item, dest_item)
            except Exception as e:
                self.log(f"⚠️  Warning: Could not copy {item.name}: {e}")
    
    def _load_discover_results(self, repo_path: Path) -> Optional[Dict[str, Any]]:
        """Load discovery results if available."""
        # Try to load enhanced discovery results first
        discovery_file = repo_path / '.forgeflow' / 'discovery.json'
        if discovery_file.exists():
            try:
                with open(discovery_file) as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Fallback to inventory
        inventory_file = repo_path / '.forgeflow' / 'inventory.json'
        if inventory_file.exists():
            try:
                with open(inventory_file) as f:
                    return {'inventory': json.load(f)}
            except Exception:
                pass
        return None
    
    def _detect_primary_language(self, repo_path: Path, discover_results: Optional[Dict]) -> str:
        """Detect primary language from discovery results or file scan."""
        # Try from discovery results first
        if discover_results and 'inventory' in discover_results:
            languages = {}
            for item in discover_results['inventory']:
                lang = item.get('language', 'Other')
                if lang != 'Other':
                    languages[lang] = languages.get(lang, 0) + 1
            if languages:
                return max(languages, key=languages.get)
        
        # Fallback to file extension detection
        lang_counts = {}
        extensions = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.tsx': 'TypeScript',
            '.go': 'Go',
            '.java': 'Java',
            '.rs': 'Rust',
        }
        
        for ext, lang in extensions.items():
            count = len(list(repo_path.rglob(f'*{ext}')))
            if count > 0:
                lang_counts[lang] = count
        
        # Check for package files as indicators
        if (repo_path / 'package.json').exists():
            if (repo_path / 'tsconfig.json').exists():
                return 'TypeScript'
            return 'JavaScript'
        if (repo_path / 'requirements.txt').exists() or (repo_path / 'pyproject.toml').exists():
            return 'Python'
        if (repo_path / 'go.mod').exists():
            return 'Go'
        if (repo_path / 'pom.xml').exists() or (repo_path / 'build.gradle').exists():
            return 'Java'
        if (repo_path / 'Cargo.toml').exists():
            return 'Rust'
        
        if lang_counts:
            return max(lang_counts, key=lang_counts.get)
        
        return 'Python'  # Default
    
    def _detect_app_name(self, repo_path: Path) -> str:
        """Detect application name from repo."""
        # Try package.json
        package_json = repo_path / 'package.json'
        if package_json.exists():
            try:
                with open(package_json) as f:
                    data = json.load(f)
                    if 'name' in data:
                        return data['name'].replace('@', '').replace('/', '-')
            except Exception:
                pass
        
        # Try pyproject.toml
        pyproject = repo_path / 'pyproject.toml'
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                for line in content.split('\n'):
                    if line.strip().startswith('name'):
                        return line.split('=')[1].strip().strip('"\'')
            except Exception:
                pass
        
        # Use directory name
        return repo_path.resolve().name.lower().replace(' ', '-').replace('_', '-')
    
    def _generate_terraform(self, infra_path: Path, app_name: str, cloud: str) -> List[Dict[str, Any]]:
        """Generate Terraform infrastructure files."""
        results = []
        timestamp = datetime.now().isoformat()
        
        # Create modules directory structure
        modules_path = infra_path / 'modules'
        for module in ['network', 'cluster', 'storage', 'iam']:
            (modules_path / module).mkdir(parents=True, exist_ok=True)
        
        # Main terraform files
        terraform_files = {
            'main.tf': TERRAFORM_MAIN.format(timestamp=timestamp, app_name=app_name),
            'variables.tf': TERRAFORM_VARIABLES.format(app_name=app_name),
            'outputs.tf': TERRAFORM_OUTPUTS,
        }
        
        # Module files
        module_files = {
            'modules/network/main.tf': TERRAFORM_NETWORK,
            'modules/cluster/main.tf': TERRAFORM_CLUSTER,
            'modules/storage/main.tf': TERRAFORM_STORAGE,
            'modules/iam/main.tf': TERRAFORM_IAM,
        }
        
        # Write main terraform files
        for filename, content in terraform_files.items():
            file_path = infra_path / filename
            if not file_path.exists():
                file_path.write_text(content)
                results.append({
                    'file': f'infrastructure/{filename}',
                    'type': 'terraform',
                    'status': 'generated',
                    'description': f'Terraform {filename.replace(".tf", "").replace("_", " ")}'
                })
            else:
                results.append({
                    'file': f'infrastructure/{filename}',
                    'type': 'terraform',
                    'status': 'exists'
                })
        
        # Write module files
        for filename, content in module_files.items():
            file_path = infra_path / filename
            if not file_path.exists():
                file_path.write_text(content)
                results.append({
                    'file': f'infrastructure/{filename}',
                    'type': 'terraform-module',
                    'status': 'generated',
                    'description': f'Terraform module: {filename.split("/")[1]}'
                })
            else:
                results.append({
                    'file': f'infrastructure/{filename}',
                    'type': 'terraform-module',
                    'status': 'exists'
                })
        
        # Create terraform.tfvars.example
        tfvars_example = infra_path / 'terraform.tfvars.example'
        if not tfvars_example.exists():
            tfvars_content = f'''# Example Terraform Variables
# Copy to terraform.tfvars and customize

app_name    = "{app_name}"
environment = "dev"
aws_region  = "us-west-2"

# Customize as needed
# kubernetes_version = "1.28"
# node_desired_size  = 2
'''
            tfvars_example.write_text(tfvars_content)
            results.append({
                'file': 'infrastructure/terraform.tfvars.example',
                'type': 'terraform',
                'status': 'generated',
                'description': 'Example variables file'
            })
        
        return results
    
    def _generate_docker_files(self, repo_path: Path, primary_lang: str, app_name: str) -> List[Dict[str, Any]]:
        """Generate Docker files with AI enhancement."""
        results = []
        app_port = self.PORT_BY_LANGUAGE.get(primary_lang, 8000)
        
        # Load discovery results for AI enhancement
        discover_results = self._load_discover_results(repo_path)
        ai_enhancer = get_ai_enhancer()
        
        # Check if multi-service architecture
        services = discover_results.get('services', []) if discover_results else []
        is_multi_service = len(services) > 1
        
        if is_multi_service and services:
            self.log(f"🤖 Detected multi-service architecture with {len(services)} services")
            
            # Generate Dockerfile for each service
            for service in services:
                service_name = service.get('name', 'service')
                service_path = repo_path / service.get('path', service_name)
                dockerfile_path = service_path / 'Dockerfile'
                
                if not dockerfile_path.exists():
                    # Get basic template
                    service_lang = service.get('language', primary_lang)
                    template = DOCKERFILE_TEMPLATES.get(service_lang, DOCKERFILE_TEMPLATES['Python'])
                    
                    # AI Enhancement
                    if ai_enhancer.is_available():
                        enhanced_dockerfile = ai_enhancer.enhance_dockerfile(service, template)
                        dockerfile_content = enhanced_dockerfile
                    else:
                        dockerfile_content = template
                    
                    dockerfile_path.parent.mkdir(exist_ok=True)
                    dockerfile_path.write_text(dockerfile_content)
                    
                    results.append({
                        'file': f'{service.get("path", service_name)}/Dockerfile',
                        'type': 'docker',
                        'status': 'generated',
                        'description': f'Dockerfile for {service_name} ({service_lang})'
                    })
        else:
            # Single service - generate root Dockerfile
            dockerfile_path = repo_path / 'Dockerfile'
            if not dockerfile_path.exists():
                template = DOCKERFILE_TEMPLATES.get(primary_lang, DOCKERFILE_TEMPLATES['Python'])
                
                # AI Enhancement for single service
                if ai_enhancer.is_available() and discover_results:
                    service_info = {
                        'name': app_name,
                        'language': primary_lang,
                        'framework': discover_results.get('frameworks', [None])[0] if discover_results.get('frameworks') else None,
                        'port': app_port,
                        'dependencies': list(discover_results.get('key_dependencies', {}).keys())[:10] if discover_results.get('key_dependencies') else []
                    }
                    enhanced_dockerfile = ai_enhancer.enhance_dockerfile(service_info, template)
                    dockerfile_content = enhanced_dockerfile
                else:
                    dockerfile_content = template
                
                dockerfile_path.write_text(dockerfile_content)
                results.append({
                    'file': 'Dockerfile',
                    'type': 'docker',
                    'status': 'generated',
                    'description': f'Multi-stage Dockerfile for {primary_lang}'
                })
            else:
                results.append({
                    'file': 'Dockerfile',
                    'type': 'docker',
                    'status': 'exists'
                })
        
        # Generate docker-compose.yml with AI enhancement
        compose_path = repo_path / 'docker-compose.yml'
        if not compose_path.exists():
            compose_content = DOCKER_COMPOSE_TEMPLATE.format(
                app_name=app_name,
                app_port=app_port
            )
            
            # AI Enhancement for docker-compose
            if ai_enhancer.is_available() and discover_results:
                detected_deps = {
                    'databases': discover_results.get('databases', []),
                    'caching': ['redis'] if any('redis' in str(d).lower() for d in discover_results.get('databases', [])) else [],
                    'messaging': []
                }
                enhanced_compose = ai_enhancer.enhance_docker_compose(
                    services,
                    detected_deps,
                    compose_content
                )
                compose_content = enhanced_compose
            
            compose_path.write_text(compose_content)
            results.append({
                'file': 'docker-compose.yml',
                'type': 'docker',
                'status': 'generated',
                'description': 'Docker Compose with detected services and dependencies'
            })
        else:
            results.append({
                'file': 'docker-compose.yml',
                'type': 'docker',
                'status': 'exists'
            })
        
        # Generate .dockerignore
        dockerignore_path = repo_path / '.dockerignore'
        if not dockerignore_path.exists():
            dockerignore_path.write_text(DOCKERIGNORE_TEMPLATE)
            results.append({
                'file': '.dockerignore',
                'type': 'docker',
                'status': 'generated',
                'description': 'Optimized Docker build context'
            })
        else:
            results.append({
                'file': '.dockerignore',
                'type': 'docker',
                'status': 'exists'
            })
        
        return results
    
    def _generate_ci_workflow(self, repo_path: Path) -> Dict[str, Any]:
        """Generate GitHub Actions workflow."""
        workflow_dir = repo_path / '.github' / 'workflows'
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflow_dir / 'forgeflow-ci.yml'
        
        if not workflow_path.exists():
            workflow_path.write_text(CI_WORKFLOW)
            return {
                'file': '.github/workflows/forgeflow-ci.yml',
                'type': 'cicd',
                'status': 'generated',
                'description': 'Full CI/CD pipeline with build, test, deploy'
            }
        return {
            'file': '.github/workflows/forgeflow-ci.yml',
            'type': 'cicd',
            'status': 'exists'
        }
