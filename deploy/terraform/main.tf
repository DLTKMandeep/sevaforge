###############################################################################
# SevaForge - Main Terraform Configuration
# Provider configuration, backend, and data sources
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "gcs" {
    bucket = "sevaforge-prod-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

###############################################################################
# Data Sources
###############################################################################

data "google_project" "current" {
  project_id = var.project_id
}

data "google_compute_zones" "available" {
  project = var.project_id
  region  = var.region
}

data "google_container_engine_versions" "gke" {
  location = var.region
  project  = var.project_id
}

data "google_client_config" "default" {}

###############################################################################
# Random suffix for globally unique resource names
###############################################################################

resource "random_id" "suffix" {
  byte_length = 4
}

###############################################################################
# Enable required APIs
###############################################################################

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "dns.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "certificatemanager.googleapis.com",
  ])

  project                    = var.project_id
  service                    = each.value
  disable_dependent_services = false
  disable_on_destroy         = false
}

###############################################################################
# Local values
###############################################################################

locals {
  common_labels = {
    project     = "sevaforge"
    environment = var.environment
    managed_by  = "terraform"
    team        = "platform"
  }

  cluster_name = "${var.project_name}-${var.environment}-gke"
}
