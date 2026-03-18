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
