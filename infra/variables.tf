variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name used as a prefix for all AWS resource names"
  type        = string
  default     = "pharmacy"
}

variable "environment" {
  description = "Deployment environment label (prod / staging)"
  type        = string
  default     = "prod"
}

# ── Database ─────────────────────────────────────────────────────────────────

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "pharmacy_admin"
}

variable "db_password" {
  description = "RDS master password (store in terraform.tfvars, never commit)"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Name of the PostgreSQL database to create"
  type        = string
  default     = "pharmacy_db"
}

variable "db_instance_class" {
  description = "RDS instance type"
  type        = string
  default     = "db.t3.micro"
}

# ── Backend secrets ───────────────────────────────────────────────────────────

variable "jwt_secret_key" {
  description = "HS256 signing key for JWTs (min 32 chars, random hex recommended)"
  type        = string
  sensitive   = true
}

# ── ECS ───────────────────────────────────────────────────────────────────────

variable "backend_cpu" {
  description = "Fargate task CPU units (256 / 512 / 1024 …)"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Number of running ECS tasks"
  type        = number
  default     = 1
}

# ── Monitoring ────────────────────────────────────────────────────────────────

variable "alert_email" {
  description = "Email address that receives CloudWatch alarm notifications"
  type        = string
}
