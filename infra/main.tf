terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — stored in S3, locked via DynamoDB.
  # The bucket and table are provisioned by infra/bootstrap/ (run that first).
  # After bootstrap apply, fill in the bucket name from its output and run:
  #   terraform init   (Terraform will offer to copy local state into S3)
  backend "s3" {
    bucket         = "pharmacy-tf-state-070872471837"
    key            = "pharmacy/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "pharmacy-tf-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Resolve current AWS account ID and region (used to build ARNs)
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
