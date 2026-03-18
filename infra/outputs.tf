# ── Outputs ───────────────────────────────────────────────────────────────────
# Copy these values into your GitHub repository secrets after `terraform apply`.

output "ecr_repository_url" {
  description = "ECR URL — used in deploy.yml (ECR_REPOSITORY variable)"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name — set as ECS_CLUSTER in deploy.yml"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name — set as ECS_SERVICE in deploy.yml"
  value       = aws_ecs_service.backend.name
}

output "alb_dns_name" {
  description = "ALB DNS — set as VITE_API_BASE GitHub secret (prefix with http://)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "cloudfront_url" {
  description = "Frontend URL — share this link on your resume/portfolio"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "s3_bucket_name" {
  description = "S3 bucket name — set as S3_BUCKET GitHub secret"
  value       = aws_s3_bucket.frontend.bucket
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID — set as CLOUDFRONT_DIST_ID GitHub secret"
  value       = aws_cloudfront_distribution.frontend.id
}

output "secrets_manager_secret_name" {
  description = "Secrets Manager secret name passed to ECS as AWS_SECRET_NAME"
  value       = aws_secretsmanager_secret.app.name
}

output "rds_endpoint" {
  description = "RDS host (already included in DATABASE_URL in Secrets Manager)"
  value       = aws_db_instance.main.address
}

output "alerts_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarms — subscribe additional endpoints here"
  value       = aws_sns_topic.alerts.arn
}
