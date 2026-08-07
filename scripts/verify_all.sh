#!/usr/bin/env bash
# Local gate runner — mirrors the full CI pipeline (ci-full.yml) so local
# verification and CI stay aligned. Order matches the workflow:
#   validate (compose) -> weights -> ruff -> mypy -> pytest -> golden
#     -> tsc -> eslint -> e2e
#
# The script manages the Docker stack like CI does: app services are stopped
# for the pytest stages (a competing worker/scheduler would corrupt the
# integration tests), then the full stack is built and started for the final
# E2E stage. See docs/engineering/ci.md for the per-stage commands.
#
# Prerequisites:
#   * `backend/.venv` with runtime + dev deps (`requirements-dev.txt`)
#   * `frontend/node_modules` installed (`npm ci`)
#   * model weights present + valid at the repo root (ADR-011)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
PY="$BACKEND/.venv/bin/python"

section() {
    printf '\n\033[1;36m===== %s =====\033[0m\n' "$*"
}

section "1/9 docker compose validate"
docker compose -f "$BACKEND/deploy/docker-compose.yml" config -q
docker compose -f "$BACKEND/deploy/docker-compose.yml" -f "$BACKEND/deploy/observability.yml" config -q
docker compose -f "$BACKEND/deploy/docker-compose.yml" -f "$BACKEND/deploy/docker-compose.test.yml" config -q
echo "ok: base, overlay, and test-override compose files are valid"

section "2/9 weights integrity (ADR-011)"
"$REPO_ROOT/scripts/verify_weights.sh"

section "3/9 ruff"
(cd "$BACKEND" && "$PY" -m ruff check .)
echo "ok: ruff clean"

section "4/9 mypy (scoped gate)"
(cd "$BACKEND" && "$PY" -m mypy --config-file mypy.ini)

section "5/9 infra up + app services stopped (for pytest)"
(cd "$BACKEND" && docker compose -f deploy/docker-compose.yml stop gateway worker scheduler 2>/dev/null || true)
(cd "$BACKEND" && docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.test.yml up -d)

section "6/9 pytest (unit + integration)"
(cd "$BACKEND" && "$PY" -m pytest -q -p no:cacheprovider)

section "7/9 pytest (golden)"
(cd "$BACKEND" && "$PY" -m pytest -q -m golden -p no:cacheprovider)

section "8/9 frontend (tsc + eslint)"
(cd "$FRONTEND" && npx tsc --noEmit --incremental false)
(cd "$FRONTEND" && npm run lint)

section "9/9 playwright e2e (full stack)"
(cd "$BACKEND" && docker compose -f deploy/docker-compose.yml up -d --build)
for _ in $(seq 1 60); do
    if curl -fsS http://localhost:8000/health/ready >/dev/null 2>&1; then
        echo "gateway ready"
        break
    fi
    sleep 5
done
if ! curl -fsS http://localhost:8000/health/ready >/dev/null 2>&1; then
    echo "gateway not ready in time"
    exit 1
fi
(cd "$FRONTEND" && npm run e2e)

printf '\n\033[1;32mAll gates passed.\033[0m\n'
