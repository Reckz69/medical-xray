# Denoise X — Terraform Scaffold

> **Status: Reference scaffold. NOT production-ready.**
> These files document the intended infrastructure layout for a future
> infrastructure-as-code sprint. They are a starting point for discussion, not
> a deployable configuration: running `terraform apply` will NOT produce a
> working environment, and `terraform validate` succeeding is expected (it
> checks syntax, not completeness).

## Why it is a scaffold, not IaC

The canonical deployment is Docker Compose on a single VM (ADR-012), and the
cloud provider / networking topology is **not yet decided**. Terraform is
tightly coupled to the target: `aws_instance` vs `azurerm_virtual_machine` vs
`hcloud_server` vs an EKS cluster are entirely different resource graphs. A
skeleton cannot be made deployable until that decision is made — and the plan
is to prove the architecture manually on a VM first.

## Intended sequence

1. **Sprint 4D (now):** decide architecture (ADR-012), ship production
   Compose, deploy manually to a VM, verify.
2. **Sprint 4E (future, IaC-only sprint):**
   - Choose the cloud provider (AWS is the most common default).
   - **Replace this scaffold** with a deployable configuration that
     provisions everything: networking (VPC, subnets, NAT, security groups),
     compute (VM or EKS), storage (EBS/S3 + lifecycle), state services
     (RDS/ElastiCache or self-hosted), secrets (Secrets Manager / SSM), DNS
     (Route53 + ACM), monitoring (CloudWatch), and outputs.
   - Add remote state + locking (e.g. S3 bucket + DynamoDB for AWS).

## Directory layout

```
deploy/terraform/
├── README.md            <- this file
└── aws/                 <- AWS-flavored starting point only
    ├── providers.tf     <- provider + backend (local state — for sketch only)
    ├── variables.tf     <- inputs a real config will need
    └── main.tf          <- VPC + compute + storage skeleton
```

The `aws/` directory is illustrative (the most common choice), not a
commitment. GCP/Azure/Hetzner variants would follow the same shape with their
own providers/resources.

## Caveats

- Local state only (no remote backend/locking yet).
- No IAM, no security groups wired to the app, no monitoring, no outputs.
- The single-`aws_instance` sketch models the canonical single-VM topology;
  the EKS + managed-state alternative (ADR-015) is a separate resource graph
  for a later decision.
