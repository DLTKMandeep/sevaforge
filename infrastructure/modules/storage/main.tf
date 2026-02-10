# =============================================================================
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
