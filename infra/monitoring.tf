# ── Billing Budget ────────────────────────────────────────────────────────────
# Requires Cost Explorer to be enabled in the AWS console (one-time toggle).
resource "aws_budgets_budget" "monthly" {
  name         = "${var.project_name}-monthly-budget"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.alerts.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.alerts.arn]
  }
}

# ── CloudWatch Billing Alarm ───────────────────────────────────────────────────
# Billing metrics are only published in us-east-1 regardless of your deploy region.
resource "aws_cloudwatch_metric_alarm" "billing" {
  alarm_name          = "${var.project_name}-billing-threshold"
  alarm_description   = "Estimated monthly charges exceeded $${var.budget_limit_usd}."
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  dimensions          = { Currency = "USD" }
  statistic           = "Maximum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = var.budget_limit_usd
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# ── SNS Topic ─────────────────────────────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "alert_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ── Unhandled 500 Errors ───────────────────────────────────────────────────────
# Matches the exact string emitted by the global_exception_handler in main.py:
#   logger.exception("Unhandled exception on %s %s", ...)
resource "aws_cloudwatch_log_metric_filter" "unhandled_exceptions" {
  name           = "${var.project_name}-unhandled-exceptions"
  log_group_name = aws_cloudwatch_log_group.backend.name
  pattern        = "\"Unhandled exception\""

  metric_transformation {
    name      = "UnhandledExceptions"
    namespace = "PharmacyApp"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "unhandled_exceptions" {
  alarm_name          = "${var.project_name}-unhandled-exceptions"
  alarm_description   = "One or more unhandled 500 errors in the last 5 minutes."
  namespace           = "PharmacyApp"
  metric_name         = "UnhandledExceptions"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
