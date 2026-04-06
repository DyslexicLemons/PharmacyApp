# Bootstrap — provisions the S3 bucket and DynamoDB table that the main
# infra/ config uses as its Terraform remote backend.
#
# Run this ONCE before you run `terraform init` in infra/:
#   cd infra/bootstrap && terraform init && terraform apply
#
# This config intentionally uses LOCAL state (no backend block) because
# the remote backend doesn't exist yet. The state file it produces is tiny
# and rarely changes — commit it or store it safely.
#
# After apply, copy the printed outputs into infra/main.tf backend block.

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Intentionally no backend block — local state is correct here.
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "pharmacy"
      ManagedBy = "Terraform-Bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}

variable "aws_region" {
  description = "AWS region (must match the main infra/ config)"
  type        = string
  default     = "us-east-1"
}

# ── S3 bucket for Terraform state ─────────────────────────────────────────────

resource "aws_s3_bucket" "tf_state" {
  # Include account ID to guarantee global uniqueness
  bucket = "pharmacy-tf-state-${data.aws_caller_identity.current.account_id}"

  # Prevent accidental deletion — comment out only if you truly need to destroy
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled" # Lets you roll back to a previous state file if corrupted
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── DynamoDB table for state locking ─────────────────────────────────────────
# Prevents two concurrent `terraform apply` runs from corrupting the state file.

resource "aws_dynamodb_table" "tf_locks" {
  name         = "pharmacy-tf-locks"
  billing_mode = "PAY_PER_REQUEST" # No provisioned capacity needed for lock table
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }
}
