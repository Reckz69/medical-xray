# Denoise X — Terraform scaffold variables (reference only, NOT production-ready).
variable "aws_region" {
  description = "AWS region for the reference topology."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Resource name prefix / tags."
  type        = string
  default     = "denoise-x"
}

variable "vpc_cidr" {
  description = "CIDR for the reference VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "instance_type" {
  description = "VM size for the canonical single-host compose deployment."
  type        = string
  default     = "t3.large" # ~2 vCPU / 8 GiB — sized for gateway + worker + infra
}

variable "bucket_name" {
  description = "Object store bucket (MinIO local default; S3 when managed)."
  type        = string
  default     = "denoise-xray"
}
