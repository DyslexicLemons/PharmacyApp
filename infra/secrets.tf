# ── AWS Secrets Manager ───────────────────────────────────────────────────────
# The backend reads this secret at startup via backend/app/secrets.py.
# The secret name is passed to the container as AWS_SECRET_NAME.

resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project_name}/prod"
  description             = "Runtime secrets for the Pharmacy backend"
  recovery_window_in_days = 0 # immediate deletion allowed (portfolio project)
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id

  secret_string = jsonencode({
    DATABASE_URL    = "postgresql://${var.db_username}:${var.db_password}@${aws_db_instance.main.address}:5432/${var.db_name}"
    JWT_SECRET_KEY  = var.jwt_secret_key
    ALLOWED_ORIGINS = "https://${aws_cloudfront_distribution.frontend.domain_name}"
  })
}
