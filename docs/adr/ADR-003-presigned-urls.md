# ADR-003: Presigned URLs over proxying images through FastAPI

- **Status:** Accepted
- **Date:** 2026-07-31
- **Deciders:** Architecture review
- **Related:** [sequence-download.md](../architecture/sequence-download.md)

## Context

Result images (original, noise map, U-Net output, enhanced) live in private
object storage. The question: how do browsers download them?

Options: (a) FastAPI streams every image by reading from storage and forwarding
bytes; (b) FastAPI verifies authorization then returns a short-lived presigned
URL and the browser downloads directly from object storage.

## Decision

Use **presigned URLs**. `GET /api/v1/scans/{scan_id}/output/{type}/url` verifies
the JWT + ownership, records an audit DOWNLOAD entry, and returns a 15-minute
presigned URL. The browser fetches the object directly from MinIO/S3.

## Rationale

- **Zero image bandwidth through the gateway** — saves enormous bandwidth at
  scale; the gateway only ever moves small JSON.
- **CDN-friendly and cheaper** — S3/MinIO handle scale and caching; object
  storage is designed exactly for this.
- **Security preserved** — the URL is object-scoped, short-lived (15 min), and
  gated by the same ownership checks as any other endpoint; downloads are audited.
- Standard practice for virtually all cloud storage systems.

## Consequences

**Positive**
- Backend stays thin and horizontally scalable.
- Downloads scale with the storage backend, not the API.

**Negative**
- Presigned URLs can be leaked if copied; mitigated by short TTL + audit.
- Slightly more moving parts (URL endpoint + client must handle direct download).
- Bucket must be private and correctly permissioned (never public read).
