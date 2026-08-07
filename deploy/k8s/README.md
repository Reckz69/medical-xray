# Denoise X — Kubernetes Reference Manifests (REFERENCE ONLY)

> **Status: Reference scaffold. NOT a supported deployment path.**
> These manifests document the Kubernetes alternative topology (ADR-012). The
> canonical production deployment is Docker Compose on a single VM
> (`deploy/production/`). Do not apply these to a cluster expecting them to be
> production-ready — they omit secrets, StorageClasses, networking policies,
> and cluster-specific wiring by design.

## When this path is used

The Kubernetes migration is warranted when (ADR-012) sustained load exceeds a
single VM, multi-zone availability becomes a requirement, or HPA-based scaling
becomes the operating model. Before then, prefer the compose deployment.

## Topology mapping (compose → Kubernetes)

| Compose service | Manifest | Notes |
| --- | --- | --- |
| gateway | `gateway.yaml` | Deployment + ClusterIP Service + HPA + PDB |
| worker | `worker.yaml` | Deployment + (commented) KEDA ScaledObject |
| scheduler | `scheduler.yaml` | Deployment + ClusterIP Service + PDB |
| postgres | `state.yaml` | StatefulSet + PVC |
| redis | `state.yaml` | Deployment + PVC (cache; loss-tolerant) |
| rabbitmq | `state.yaml` | StatefulSet + PVC |
| minio | `state.yaml` | StatefulSet + PVC |
| caddy / ingress | `ingress.yaml` | Ingress + cert-manager (replaces Caddy) |
| config (non-secret) | `configmap.yaml` | mirrors `deploy/production/.env.example` |
| secrets | `secrets.yaml` | placeholders → SealedSecrets / cloud manager (ADR-014) |

## Apply order (illustrative — see caveats above)

```sh
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml      # fill values first (SealedSecrets)
kubectl apply -f configmap.yaml
kubectl apply -f state.yaml
kubectl apply -f gateway.yaml -f worker.yaml -f scheduler.yaml
kubectl apply -f ingress.yaml
```

## Secrets (ADR-014)

`secrets.yaml` contains **placeholders only** — never plaintext credentials.
In a real cluster, provision them via:

- **SealedSecrets** (recommended): `kubeseal` the values, commit only the
  encrypted `SealedSecret`, let the controller produce the `Secret`.
- **Cloud secret manager** (AWS Secrets Manager / GCP Secret Manager)
  referenced by name and synced by a controller.

## Images (ADR-016)

All Deployments reference `ghcr.io/<owner>/<service>:latest` as a placeholder.
Pin to a concrete `<sha>` / `v<semver>` / `<sprint-tag>` (ADR-017) before any
real use. A cluster must be able to pull GHCR (ImagePullSecret / workload
identity) — see `secrets.yaml`.

## Model weights (ADR-011)

The worker mounts the weights file `:ro`. In Kubernetes this is a
`ConfigMap`/init-container populated from the `weights-v1` release, or an
existing `PersistentVolume` containing the verified file (see the worker
manifest's volumeMount comments). Verify with `scripts/verify_weights.sh`
after download, as in CI.

## Validation

These files are YAML-parse-checked in the repo gate only (no cluster, no
`kubectl apply`). Treat them as architecture documentation with executable
syntax, not as tested cluster configuration.
