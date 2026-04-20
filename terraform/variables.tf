variable "app_name" {
  description = "Application name"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment (dev, staging, production)"
  type        = string
  default     = "staging"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
