"""Release provenance, captured once at import time (Sprint 4F).

`APP_GIT_SHA` is resolved a single time when this module is imported, never
per request — no subprocess on the hot path, and it keeps working after the
.git directory is stripped from a container image. CI can pin the value via
the ``GIT_SHA`` setting instead of auto-detection.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from gateway.core.config import settings

logger = logging.getLogger("denoise")

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve_git_sha() -> str | None:
    if settings.git_sha:
        return settings.git_sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
        )
        sha = out.stdout.strip()
        return sha or None
    except Exception as exc:  # noqa: BLE001 — provenance is best-effort
        logger.warning("could not resolve git sha: %s", exc)
        return None


APP_GIT_SHA: str | None = _resolve_git_sha()
