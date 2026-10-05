output "sns_topic_arn" {
  value       = aws_sns_topic.alerts.arn
  description = "ARN of the SNS topic receiving change reports."
}

output "dynamodb_table_name" {
  value       = aws_dynamodb_table.state_table.name
  description = "DynamoDB table storing JSON checkpoints."
}
