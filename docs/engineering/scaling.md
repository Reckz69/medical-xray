# Denoise X — Scaling Design

> Sprint 4D (ADR-012). This is the **design** for how scaling works today
> (single VM) and how it works on the Kubernetes path. The K8s path is
> reference material — see `deploy/k8s/README.md`.

## Where the load is

Three workload profiles:

| Service | Driver | Scaling signal |
| --- | --- | --- |
| gateway | request rate (QPS) | CPU / concurrent requests |
| worker | job queue depth | RabbitMQ queue length (inference is CPU/GPU bound) |
| scheduler | low, periodic | none (fixed 1) |

## Single VM (canonical deployment)

- **Compute headroom is the VM's CPU/RAM.** The worker dominates (TensorFlow
  inference). Sizing guidance: size the VM for the worker's batch + the
  gateway's request rate; the scheduler is negligible.
- **Workers already scale horizontally within the VM** — RabbitMQ competing
  consumers mean running a second worker container (or a second worker host
  pointing at the same queue) adds inference throughput with **no queue
  semantics change** and no scheduler change:
  ```sh
  docker compose up -d --scale worker=2
  ```
- **Everything else is vertical** (bigger VM) until the Kubernetes path.
- Limits: one host = one availability domain; a VM restart takes the stack
  down (ADR-012).

## Kubernetes path

### Gateway — HPA on CPU

`deploy/k8s/gateway.yaml` ships a `HorizontalPodAutoscaler`: CPU 70%, `min 2`,
`max 6`. Rationale: the gateway is stateless (state lives in Postgres/Redis),
so replicas behind the ClusterIP Service balance cleanly. Add a second metric
(p99 latency via Prometheus adapter) before pushing `max` higher.

### Worker — KEDA on queue depth

Worker replicas should follow the **job queue**, not CPU. The design (commented
ScaledObject in `deploy/k8s/worker.yaml`) uses the KEDA RabbitMQ trigger:

- `mode: QueueLength`, `value: "10"` — scale up when >10 jobs are waiting
  behind the worker consumer; scale down after a 300s cooldown.
- `minReplicaCount: 1`, `maxReplicaCount: 8` — upper bound matched to the
  worker's memory budget (inference, ~4 Gi each).

Why queue depth over CPU: a worker at 100% CPU is exactly the state that *does*
need more workers; CPU-based HPA reacts late (it sees saturation, not backlog)
and the metric lags the real driver.

The RabbitMQ trigger needs the connection string in KEDA metadata — in a real
cluster that is injected from the same Secret (ADR-014), never committed.

### Scheduler — fixed 1

Scheduler replicas cooperate via Redis distributed locks (ADR-009); more than
one is fine but not load-driven. PDB keeps one available during upgrades.

## When to move to Kubernetes

Per ADR-012, migrate when two or more of: sustained load exceeds one VM,
multi-zone availability required, or HPA/KEDA becomes the operating model. The
compose services map one-to-one onto the reference Deployments.
