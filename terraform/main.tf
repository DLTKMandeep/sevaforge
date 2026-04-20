# Minimal ForgeFlow deployment config (fallback — run `forgeflow iac` for full setup)
terraform {{
  required_providers {{
    aws = {{
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }}
  }}
}}

provider "aws" {{
  region = var.region
}}

resource "aws_ecr_repository" "app" {{
  name                 = var.app_name
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {{
    scan_on_push = true
  }}
  tags = {{
    ManagedBy = "ForgeFlow"
    Environment = var.environment
  }}
}}

resource "aws_ecs_cluster" "main" {{
  name = "${{var.app_name}}-${{var.environment}}"
  setting {{
    name  = "containerInsights"
    value = "enabled"
  }}
}}
