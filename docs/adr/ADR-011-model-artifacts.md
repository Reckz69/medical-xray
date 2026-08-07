# ADR-011: Model Artifact Distribution — GitHub Releases with integrity verification

- **Status:** Accepted
- **Date:** 2026-08-07
- **Deciders:** Architecture review
- **Related:** [`ADR-006-model-manager.md`](ADR-006-model-manager.md), `docs/engineering/ci.md`, `docs/technical-debt.md`

## Context

The denoising weights (`n2n_unet_best_weights04 (2).keras`, ~89 MB) are a
runtime dependency of the worker (`MODEL_PATH`), and of three test groups:
`tests/test_model_manager.py`, `tests/test_inference.py`, and the golden suite
(`tests/golden/`). They are gitignored (`*.keras`) and until Sprint 4C existed
only on the development machine.

Sprint 4C introduces CI. The pipeline needs those weights on a fresh runner in
the backend test job and in the full-stack E2E job. That forces a decision on
where the artifact lives and how it reaches CI without (a) bloating the git
history, (b) hard-coding a machine-specific path, or (c) silently skipping the
tests that genuinely need the real model.

## Decision

### Distribution channel: GitHub Releases

The weights are published as an asset of a GitHub Release named `weights-v1`
on the `denoisex` remote. CI downloads them with the built-in token:

```yaml
GH_TOKEN: ${{ github.token }}
gh release download weights-v1 \
  --pattern 'n2n_unet_best_weights04 (2).keras' \
  --dir .
```

`GITHUB_TOKEN` has `contents: read` on the same repository, so this works on a
private repo without storing credentials, and it fails loudly if the asset is
missing — there is no silent skip of weight-gated tests.

### Versioning

- The GitHub Release tag **`weights-vN`** identifies the artifact.
- The app's `MODEL_VERSION` (`settings.model_version`, default `v1.0.0`)
  identifies the model the code expects.
- A new model release bumps both together and records the mapping in
  `docs/engineering/ci.md` so the two stay in lockstep.

### Integrity verification

Downloading alone is not enough — a corrupted transfer or the wrong model
uploaded must fail the pipeline. A checksum manifest is committed to the
repository (`scripts/weights.sha256`) containing the expected filename, size,
and SHA-256 digest. CI (and `scripts/verify_all.sh`) verifies all three before
any test that loads the model runs:

1. expected filename exists at the repo root,
2. `stat` size matches,
3. `sha256sum -c` passes.

### Publishing future versions

Documented step (see `docs/engineering/ci.md`): build/export the `.keras`,
compute `shasum -a 256`, update `scripts/weights.sha256`, create the
`weights-vN` release, upload the asset, bump `MODEL_VERSION`, commit, push.

## Alternatives considered

- **Commit the weights to git** — rejected. ~89 MB permanent bloat in history
  for every clone, forever; the artifact changes rarely but the repo pays
  forever. Git LFS would mitigate bloat but couples the host to LFS tooling.
- **Git LFS** — rejected. Adds a per-repo host dependency and a bandwidth
  quota that varies by provider; GitHub Releases has no per-file-size toll for
  our scale and is provider-native.
- **S3/Object storage** — rejected for now. Would require real credentials in
  CI (secret management, rotation) to serve a public-to-the-org artifact that
  Releases already serves for free. A better fit when artifacts move to a
  shared model store.
- **Hugging Face Hub** — rejected for now. Purpose-built for model hosting,
  but adds an external account dependency; see future options.

## Future storage options

GitHub Releases is today's choice, not a permanent one. As the artifact
strategy grows, the seam to watch is the single download step in CI and
`scripts/verify_all.sh` — the checksum manifest keeps every option safe to
switch to:

| Option | When it wins |
| --- | --- |
| **GitHub Releases** (current) | Small team, private repo, zero credentials, one artifact |
| **S3/Object storage** | Shared model store, multiple artifacts, need access control/auditing |
| **Hugging Face Hub** | Multiple ML artifacts, want versioned model cards + public distribution |
| **Internal artifact registry** (e.g. Artifactory/Nexus) | Enterprise policy requires a single artifact registry for everything |

## Consequences

**Positive**
- CI downloads the real model in ~seconds and runs the true weight-gated tests;
  a missing/corrupt artifact fails the pipeline instead of silently skipping.
- No secrets, no git bloat, no machine-specific paths; the repo is the single
  source of truth for the checksum.
- The exact same download+verify path is used locally by `verify_all.sh`, so CI
  and development cannot diverge.

**Negative**
- Weights live outside the repo: a fresh contributor must run the documented
  download step (or rely on CI) before weight-gated tests pass locally.
- Releasing a new model is a multi-step manual process (asset + manifest +
  version bump) — documented in `docs/engineering/ci.md`, but still manual.
- Private-repo Releases are scoped to users with repo access; a future
  read-only CI consumer outside this repo would need a different channel.
