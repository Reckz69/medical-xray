#!/usr/bin/env bash
# Verify the model weights artifact against the committed manifest (ADR-011).
#
# Usage: scripts/verify_weights.sh [path-to-weights]
#   Defaults to the repo root (where CI downloads the GitHub Release asset and
#   where the weight-gated tests look for it).
#
# Exits non-zero on any mismatch (missing file, wrong size, wrong SHA-256) so
# CI fails loudly instead of silently skipping weight-gated tests.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/scripts/weights.sha256"

EXPECTED_NAME="$(sed -n 's/^name //p' "$MANIFEST")"
EXPECTED_SIZE="$(sed -n 's/^size //p' "$MANIFEST")"
EXPECTED_SHA="$(sed -n 's/^sha256 //p' "$MANIFEST")"

WEIGHTS="${1:-$REPO_ROOT/$EXPECTED_NAME}"

echo "==> Verifying model weights (ADR-011): $(basename "$WEIGHTS")"

if [[ ! -f "$WEIGHTS" ]]; then
    echo "ERROR: weights not found at $WEIGHTS" >&2
    echo "Download them first, e.g.: gh release download weights-v1 --repo <owner>/<repo> --dir ." >&2
    exit 1
fi

ACTUAL_SIZE="$(stat -f%z "$WEIGHTS" 2>/dev/null || stat -c%s "$WEIGHTS")"
if [[ "$ACTUAL_SIZE" != "$EXPECTED_SIZE" ]]; then
    echo "ERROR: size mismatch (expected $EXPECTED_SIZE, got $ACTUAL_SIZE)" >&2
    exit 1
fi

ACTUAL_SHA="$(shasum -a 256 "$WEIGHTS" | awk '{print $1}')"
if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "ERROR: SHA-256 mismatch (expected $EXPECTED_SHA, got $ACTUAL_SHA)" >&2
    exit 1
fi

echo "OK: $(basename "$WEIGHTS") — $ACTUAL_SIZE bytes, sha256 ${ACTUAL_SHA:0:16}..."
