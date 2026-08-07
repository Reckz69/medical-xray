# Denoise X — Terraform scaffold (reference only, NOT production-ready).
#
# Sketches the canonical single-VM topology (ADR-012): one VPC, one compute
# host running the compose stack, one object-storage bucket. This file is NOT
# deployable — it has no IAM/security groups, no DNS/TLS, no monitoring, no
# outputs, and local state only. See README.md.

# Networking — one VPC with a public subnet and an internet gateway.
# (A real config adds private subnets, NAT, route tables, and security groups
# that expose only :80/:443 per ADR-013.)
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true

  tags = { Name = "${var.project}-vpc" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 0)
  map_public_ip_on_launch = true

  tags = { Name = "${var.project}-public" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${var.project}-igw" }
}

# Compute — the single host that runs deploy/production/docker-compose.yml.
# SSH access and the exact AMI/OS are decided at IaC-sprint time; this is the
# shape of the resource, not a finished definition.
resource "aws_instance" "app" {
  ami           = "ami-CHANGE_ME" # pin an OS image at IaC-sprint time
  instance_type = var.instance_type
  subnet_id     = aws_subnet.public.id

  tags = { Name = "${var.project}-app" }
}

# Storage — object store bucket. With STORAGE_PROVIDER=s3 the app uses this
# instead of MinIO (ADR-015); lifecycle/versioning are wired in Phase 5.
resource "aws_s3_bucket" "objects" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "objects" {
  bucket = aws_s3_bucket.objects.id
  versioning_configuration {
    status = "Enabled"
  }
}
