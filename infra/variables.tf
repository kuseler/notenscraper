variable "aws_region" {
  type        = string
  default     = "us-east-1"
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
  default     = "America/New_York"
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
