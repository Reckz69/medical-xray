"""Inference pipeline seam.

Sprint 2B runs the worker over the full production path (download -> process
-> upload -> persist -> publish) with an identity transform so there is no ML
dependency. Sprint 3 replaces `run` with the real denoising model; the executor
calls exactly this function and nothing else changes.
"""

from __future__ import annotations


async def run(data: bytes, *, fmt: str) -> bytes:
    """Denoise `data` and return the processed image bytes (identity for now)."""
    return data
