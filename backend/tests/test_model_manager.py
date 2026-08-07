"""ModelManager tests (Stage 3.3 gate).

Verifies the load-once lifecycle against the real weights when present, and
model_versions persistence against the running database. The heavy model test
is skipped when the gitignored weights file is not available.
"""

from __future__ import annotations

import pathlib

import pytest

from worker.model_manager import ModelManager

_WEIGHTS = pathlib.Path(__file__).resolve().parents[2] / "n2n_unet_best_weights04.keras"

pytestmark = pytest.mark.skipif(
    not _WEIGHTS.exists(), reason="model weights not present (gitignored)"
)


@pytest.fixture()
def manager() -> ModelManager:
    return ModelManager()


def test_startup_loads_model_once(manager: ModelManager) -> None:
    manager.startup()
    assert manager.get_pipeline() is not None
    first = manager.get_pipeline()
    assert manager.get_pipeline() is first, "model must be cached, not reloaded"


def test_model_input_output_shapes_match_tile(manager: ModelManager) -> None:
    manager.startup()
    model = manager.get_pipeline()
    assert tuple(model.inputs[0].shape[1:]) == (manager.tile, manager.tile, 1)
    assert tuple(model.outputs[0].shape[1:]) == (manager.tile, manager.tile, 1)


def test_startup_captures_provenance(manager: ModelManager) -> None:
    manager.startup()
    assert isinstance(manager.git_commit, str) and manager.git_commit
    assert manager.gpu_name is None or isinstance(manager.gpu_name, str)


def test_shutdown_releases_model(manager: ModelManager) -> None:
    manager.startup()
    manager.shutdown()
    assert manager._pipeline is None


async def test_persist_version_reuses_existing_row(
    manager: ModelManager, _fresh_engine
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from gateway.repositories.model_repository import ModelVersionRepository

    manager.model_name = "n2n_unet_test"
    manager.model_version = "test-v1"
    session_factory = async_sessionmaker(_fresh_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        first = await manager.persist_version(session)
        await session.commit()
        manager.model_id = None  # simulate a fresh manager for the same weights
        second = await manager.persist_version(session)
        assert first.id == second.id, "same weights/version must reuse the row"
        assert manager.model_id == first.id
    async with session_factory() as session:
        existing = await ModelVersionRepository(session).get_by_name_version(
            "n2n_unet_test", "test-v1"
        )
        assert existing is not None
