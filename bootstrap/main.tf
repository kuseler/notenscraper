terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_repo" {
  type        = string
  description = "Format: 'organization/repo-name' or 'username/repo-name'"
}

# 1. GitHub OIDC Identity Provider
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58e3a859067b07c1144143a5796248da50f0e0"
  ]
}

# 2. IAM Role for GitHub Actions
resource "aws_iam_role" "github_actions_role" {
  name = "github-actions-infra-deployer"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "deployer_admin" {
  role       = aws_iam_role.github_actions_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

# 3. S3 Bucket for OpenTofu Remote State
resource "aws_s3_bucket" "tf_state" {
  bucket_prefix = "tofu-state-${replace(var.github_repo, "/", "-")}-"
}

resource "aws_s3_bucket_versioning" "tf_state_versioning" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

output "role_arn" {
  value       = aws_iam_role.github_actions_role.arn
  description = "Add this value as AWS_ROLE_ARN in GitHub Actions Secrets."
}

output "state_bucket_name" {
  value       = aws_s3_bucket.tf_state.bucket
  description = "Put this into infra/main.tf in the backend block."
}
