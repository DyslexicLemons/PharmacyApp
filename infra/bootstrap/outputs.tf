# Copy these values into the backend block in infra/main.tf

output "state_bucket_name" {
  description = "Paste this as `bucket` in the infra/main.tf backend block"
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "Paste this as `dynamodb_table` in the infra/main.tf backend block"
  value       = aws_dynamodb_table.tf_locks.name
}

output "aws_region" {
  description = "Paste this as `region` in the infra/main.tf backend block"
  value       = var.aws_region
}

output "next_steps" {
  description = "What to do after this apply"
  value       = <<-EOT
    Backend resources created. Now:
      1. Open infra/main.tf and uncomment the backend "s3" block.
      2. Set:
           bucket         = "${aws_s3_bucket.tf_state.bucket}"
           key            = "pharmacy/terraform.tfstate"
           region         = "${var.aws_region}"
           dynamodb_table = "${aws_dynamodb_table.tf_locks.name}"
           encrypt        = true
      3. Run: cd ../  &&  terraform init
         Terraform will prompt you to copy local state into S3 — answer yes.
  EOT
}
