variable "app_name" {
  description = "Application name"
  type        = string
  default     = "forgeflow-app"
}

variable "region" {
  description = "AWS Region"
  type        = string
  default     = "us-east-1"
}

variable "desired_count" {
  description = "Number of instances"
  type        = number
  default     = 2
}

variable "subnets" {
  description = "Subnet IDs"
  type        = list(string)
  default     = []
}
