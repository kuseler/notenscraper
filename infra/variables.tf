variable "aws_region" {
  type        = string
  default     = "eu-central-1"
  description = "AWS deployment region."
}

variable "project_name" {
  type        = string
  default     = "json-change-monitor"
  description = "Prefix for all resource names."
}

variable "notification_email" {
  type        = string
  description = "Destination email for SNS change alerts."
}

variable "schedule_timezone" {
  type        = string
  default     = "Europe/Berlin"
  description = "IANA timezone for business hours (e.g., America/Chicago, Europe/London)."
}

variable "scraper_username" {
  type        = string
  sensitive   = true
  description = "Username for target site scraper."
}

variable "scraper_password" {
  type        = string
  sensitive   = true
  description = "Password for target site scraper."
}

variable "role_arn" {
  type        = string
  default     = null
  description = "IAM Role ARN, configurable via TF_VAR_role_arn or AWS_ROLE_ARN."
}

variable "state_bucket_name" {
  type        = string
  default     = null
  description = "S3 state bucket name, configurable via TF_VAR_state_bucket_name or STATE_BUCKET_NAME."
}
