terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  backend "s3" {
    # Bucket name can be supplied dynamically via -backend-config="bucket=$STATE_BUCKET_NAME"
    # or via the STATE_BUCKET_NAME environment variable in CI/CD.
    key    = "pipeline/terraform.tfstate"
    region = "eu-central-1"
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. State Persistence (DynamoDB - 1 RCU / 1 WCU Provisioned Always Free)
resource "aws_dynamodb_table" "state_table" {
  name           = "${var.project_name}-state"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "id"

  attribute {
    name = "id"
    type = "S"
  }
}

# 2. SNS Alerting
resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# 3. CloudWatch Log Group (14-day retention prevents free tier storage exhaustion)
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.project_name}-reporter"
  retention_in_days = 14
}

# 4. Lambda Crash Alarm (Fires if the scraper throws uncaught errors)
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.project_name}-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Triggered when the scraper Lambda crashes or fails execution."
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = aws_lambda_function.reporter.function_name
  }
}

# 5. Dependency Layer Build
resource "terraform_data" "build_layer" {
  triggers_replace = [
    filesha256("${path.module}/../src/requirements.txt")
  ]

  provisioner "local-exec" {
    command = <<-EOT
      python3 -m pip install \
        --platform manylinux2014_x86_64 \
        --target "${path.module}/build_layer/python" \
        --implementation cp \
        --python-version 3.12 \
        --only-binary=:all: \
        --upgrade \
        -r "${path.module}/../src/requirements.txt"
    EOT
  }
}

data "archive_file" "layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/build_layer"
  output_path = "${path.module}/layer.zip"

  depends_on = [terraform_data.build_layer]
}

resource "aws_lambda_layer_version" "python_deps" {
  layer_name          = "${var.project_name}-dependencies"
  filename            = data.archive_file.layer_zip.output_path
  source_code_hash    = data.archive_file.layer_zip.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

# 6. Lambda Packaging & Execution
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../src/index.py"
  output_path = "${path.module}/lambda.zip"
}

resource "aws_iam_role" "lambda_exec_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.lambda_logs.arn}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:PutItem"]
        Resource = aws_dynamodb_table.state_table.arn
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.alerts.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

resource "aws_lambda_function" "reporter" {
  function_name    = "${var.project_name}-reporter"
  role             = aws_iam_role.lambda_exec_role.arn
  handler          = "index.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30
  memory_size      = 128
  reserved_concurrent_executions = 1
  layers           = [aws_lambda_layer_version.python_deps.arn]

  environment {
    variables = {
      TABLE_NAME       = aws_dynamodb_table.state_table.name
      SNS_TOPIC_ARN    = aws_sns_topic.alerts.arn
      SCRAPER_USERNAME = var.scraper_username
      SCRAPER_PASSWORD = var.scraper_password
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda_logs]
}

# 7. EventBridge Scheduler
resource "aws_iam_role" "scheduler_role" {
  name = "${var.project_name}-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "scheduler_invoke_lambda" {
  name = "${var.project_name}-scheduler-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.reporter.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_attach" {
  role       = aws_iam_role.scheduler_role.name
  policy_arn = aws_iam_policy.scheduler_invoke_lambda.arn
}

resource "aws_scheduler_schedule" "business_hours_schedule" {
  name       = "${var.project_name}-schedule"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  # Every 2 hours: 9am, 11am, 1pm, 3pm, 5pm Monday-Friday
  schedule_expression          = "cron(0 9,11,13,15,17 ? * MON-FRI *)"
  schedule_expression_timezone = var.schedule_timezone

  target {
    arn      = aws_lambda_function.reporter.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}

# 8. Zero-Spend Cost Budget Alert ($0.01 / ~0.01€ cap)
resource "aws_budgets_budget" "zero_spend_budget" {
  name         = "${var.project_name}-budget-cap"
  budget_type  = "COST"
  limit_amount = "0.01"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Alert immediately when actual spend exceeds $0.01
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.notification_email]
  }

  # Alert immediately if forecasted spend exceeds $0.01
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.notification_email]
  }
}
