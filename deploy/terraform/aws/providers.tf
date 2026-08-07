# Denoise X — Terraform scaffold (reference only, NOT production-ready).
# See README.md in this directory. Provider pinned conservatively; upgrade at
# IaC-sprint time.
terraform {
  required_version = ">= 1.5"

  # Local state ONLY — this is a sketch. The IaC sprint adds remote state +
  # locking (S3 + DynamoDB on AWS).
  backend "local" {}

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
