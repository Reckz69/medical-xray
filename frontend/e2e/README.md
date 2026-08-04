# DenoiseX — Playwright E2E (smoke)

One intentionally small smoke spec covering the full user journey:

```
register/login → upload → 202 → poll to COMPLETED → results gallery shows
4 outputs (Original / Noise Map / U-Net / Enhanced) → images load via
presigned URLs → download links present → logout
```

No auth-failure, rate-limit, or validation edge cases — those belong in the
backend pytest suite (`backend/tests/`). This spec proves the wiring end to end
in a real browser.

## Prerequisites

The **full stack must be running** before the test starts:

1. Docker infra (Postgres, Redis, RabbitMQ, MinIO):

   ```bash
   docker compose -f backend/deploy/docker-compose.yml up -d
   ```

2. Gateway:

   ```bash
   cd backend
   .venv/bin/uvicorn main:app --reload   # http://localhost:8000
   ```

3. Worker (must be running so the job reaches COMPLETED — do NOT run it
   concurrently with the backend integration tests):

   ```bash
   cd backend
   .venv/bin/python -m worker.main
   ```

4. Playwright browser (once):

   ```bash
   cd frontend
   npm run e2e:install
   ```

## Run

```bash
cd frontend
npm run e2e
```

Playwright starts the Next dev server on `:3000` (reusing one that is already
running). The spec:

- registers a throwaway account (`e2e-<timestamp>@example.com`)
- uploads a **fresh random 256×256 grayscale PNG generated in-test**
  (`e2e/lib/png.ts`, dependency-free encoder) — unique bytes per run so the
  backend's per-organization content-hash dedup never short-circuits the journey
- polls `GET /api/v1/jobs/{id}` until the scan is `COMPLETED`
- asserts all 4 outputs render and carry `http…` download URLs
- opens the gallery, expands the scan, then signs out

## Caveats

- **Register rate limit**: signups are limited to 3/day per IP. After a few
  runs the spec hits `429`; flush Redis or wait for the window to reset.
- **Upload rate limit**: 20 uploads/hour per user — irrelevant for a single run.
- **CPU cold start**: the first inference loads the `.keras` weights into RAM;
  the spec allows up to 5 minutes for the full poll.

## CI

Optional. Run only after the backend suite + golden tests pass, and only when
the stack is provisioned:

```bash
npm run e2e
```
