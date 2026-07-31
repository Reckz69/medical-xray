# ADR-004: Server-side encryption (SSE-KMS) over app-level AES-GCM

- **Status:** Accepted
- **Date:** 2026-07-31
- **Deciders:** Architecture review
- **Related:** [threat-model.md](../security/threat-model.md)

## Context

X-ray images are patient PHI and must be encrypted at rest in object storage.
Two viable approaches:

1. **App-level client-side encryption** — the gateway encrypts bytes with
   AES-256-GCM using a key from `.env` before upload, decrypts on download.
2. **Server-side encryption** — delegate to the storage backend: `aws:kms` SSE
   (S3) or MinIO SSE locally. The application never sees keys or ciphertext
   transforms.

## Decision

Use **server-side encryption** for v1: `aws:kms` on S3 (target AWS), MinIO SSE
locally. Do **not** implement application-level AES-GCM.

## Rationale

Client-side encryption turns the platform into a cryptography project:

- key rotation, key management, lost-key recovery, envelope encryption,
  multi-server key sharing — all required to do it safely;
- an application-level bug can silently produce undecryptable data;
- keys in `.env` create a single point of catastrophic failure.

Server-side encryption is far less code, delegated to battle-tested providers,
and `aws:kms` takes over with zero application change when moving to AWS.

## Consequences

**Positive**
- Minimal code, no key lifecycle in the app.
- Migrating MinIO → S3 → R2 keeps the same `StorageProvider` interface.

**Negative**
- At-rest encryption strength is delegated to the provider (acceptable).
- Bucket must be configured private; SSE config is part of infrastructure, not code.
