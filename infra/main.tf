terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # After running `terraform apply` the first time, create an S3 bucket for
  # state and uncomment this block to migrate state into it.
  # backend "s3" {
  #   bucket  = "pharmacy-tf-state-<your-account-id>"
  #   key     = "pharmacy/terraform.tfstate"
  #   region  = "us-east-1"
  #   encrypt = true
  # }
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
