"""ModelManager — the loaded denoising model, loaded once and shared (ADR-006).

Owned by the worker process. ``startup`` loads TensorFlow and the weights,
detects the GPU (best-effort), captures the git commit of the loaded weights,
and persists a ``model_versions`` row (reusing an existing one when present).
``get_pipeline`` returns the cached Keras model — never reloaded per job.
``shutdown`` releases it.

The model is blocking to load; callers should run ``startup`` in a worker
thread (``asyncio.to_thread``) so the event loop is not blocked.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from gateway.core.config import settings
from gateway.models.model_version import ModelVersion
from gateway.repositories.model_repository import ModelVersionRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("denoise.worker")

_MODEL_PATH = Path(__file__).resolve().parents[1] / settings.model_path


def _git_commit() -> str | None:
    """Best-effort short git commit of the repository at load time."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001 — provenance is best-effort
        logger.warning("could not resolve git commit for model_versions: %s", exc)
        return None


def _gpu_name() -> str | None:
    """Best-effort GPU name from TensorFlow's device list."""
    try:
        import tensorflow as tf

        gpus = tf.config.list_physical_devices("GPU")
        return gpus[0].name if gpus else None
    except Exception:  # noqa: BLE001 — detection must never break startup
        return None


class ModelManager:
    """Lifecycle holder for the Keras denoising model."""

    def __init__(
        self,
        *,
        model_path: Path | None = None,
        model_name: str | None = None,
        model_version: str | None = None,
        tile: int | None = None,
    ) -> None:
        self._model_path = model_path or _MODEL_PATH
        self.model_name = model_name or settings.model_name
        self.model_version = model_version or settings.model_version
        self.tile = tile or settings.model_tile
        self.git_commit: str | None = None
        self.gpu_name: str | None = None
        self.model_id: UUID | None = None
        self._pipeline = None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def startup(self) -> None:
        """Load TensorFlow and the weights once. Blocking; call via to_thread."""
        import tensorflow as tf  # deferred: keeps converter imports TF-free

        self.gpu_name = _gpu_name()
        logger.info(
            "loading %s (%s) from %s [gpu=%s]",
            self.model_name,
            self.model_version,
            self._model_path,
            self.gpu_name or "cpu",
        )
        self._pipeline = tf.keras.models.load_model(str(self._model_path), compile=False)
        assert self._pipeline is not None
        self.git_commit = _git_commit()

        in_shape = tuple(self._pipeline.inputs[0].shape[1:])
        out_shape = tuple(self._pipeline.outputs[0].shape[1:])
        expected = (self.tile, self.tile, 1)
        if in_shape != expected:
            raise ValueError(
                f"model input shape {in_shape} does not match expected {expected}"
            )
        if out_shape != (self.tile, self.tile, 1):
            raise ValueError(
                f"model output shape {out_shape} does not match expected tile "
                f"{(self.tile, self.tile, 1)}"
            )
        logger.info("model %s loaded (in=%s out=%s)", self.model_name, in_shape, out_shape)

    def get_pipeline(self):
        """Return the cached model, loading it once on first access."""
        if self._pipeline is None:
            self.startup()
        return self._pipeline

    def shutdown(self) -> None:
        """Release the model (best-effort)."""
        self._pipeline = None
        self.model_id = None

    # ── metadata persistence ──────────────────────────────────────────────────
    async def persist_version(self, session: AsyncSession) -> ModelVersion:
        """Create or reuse the ``model_versions`` row and record ``model_id``."""
        repo = ModelVersionRepository(session)
        existing = await repo.get_by_name_version(self.model_name, self.model_version)
        if existing is not None:
            self.model_id = existing.id
            return existing
        params = {"tile": self.tile}
        created = await repo.create(
            model_name=self.model_name,
            model_version=self.model_version,
            git_commit=self.git_commit,
            gpu_name=self.gpu_name,
            params_json=params,
        )
        self.model_id = created.id
        return created


__all__ = ["ModelManager"]
