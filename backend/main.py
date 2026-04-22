"""
main.py — Denoise X FastAPI Backend
=====================================
Exposes two endpoints:
  GET  /health          → liveness check
  POST /api/denoise     → accepts X-ray image, returns 4 enhanced images + metadata
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from inference_engine import run_pipeline, DenoiseResult

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("denoise_x.api")

# ── Supported formats ─────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".dcm", ".dicom"}
MAX_FILE_SIZE_MB = 50


# ── Lifespan (model warm-up on startup) ──────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Denoise X API starting up…")
    # Pre-warm the model so first request isn't slow
    try:
        from inference_engine import _load_model
        _load_model()
        logger.info("✅ Model pre-loaded successfully.")
    except Exception as e:
        logger.error("⚠️  Model pre-load failed: %s — will retry on first request.", e)
    yield
    logger.info("🛑 Denoise X API shutting down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Denoise X API",
    description="Clinical-grade AI X-Ray denoising using N2N U-Net.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — allow Next.js dev server and any production origin ─────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Response schema ───────────────────────────────────────────────────────────
class DenoiseResponse(BaseModel):
    original_b64: str
    noise_map_b64: str
    unet_b64: str
    enhanced_b64: str
    routing_message: str
    noise_variance: float
    was_bypassed: bool
    width: int
    height: int
    processing_time_ms: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    version: str


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Liveness + readiness check. Returns model load status."""
    from inference_engine import _model
    return HealthResponse(
        status="ok",
        model_loaded=_model is not None,
        version="1.0.0",
    )


@app.post("/api/denoise", response_model=DenoiseResponse, tags=["Inference"])
async def denoise(file: UploadFile = File(...)):
    """
    Accept an X-ray image (PNG / JPEG / DICOM) and return:
    - original_b64    : raw uploaded image (base64 PNG)
    - noise_map_b64   : isolated noise residual (base64 PNG)
    - unet_b64        : raw U-Net output (base64 PNG)
    - enhanced_b64    : final CLAHE-enhanced clinical output (base64 PNG)
    - routing_message : Gateway routing decision string
    - noise_variance  : measured flat-tissue variance
    - was_bypassed    : True if scan was clean and AI was skipped
    - width / height  : original image dimensions in pixels
    - processing_time_ms : wall-clock time for the pipeline
    """
    t_start = time.perf_counter()

    # ── Validate file extension ────────────────────────────────────────────
    filename = file.filename or "upload"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. "
                   f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # ── Read bytes & size-check ────────────────────────────────────────────
    image_bytes = await file.read()
    size_mb = len(image_bytes) / (1024 * 1024)
    logger.info("Received file: %s  (%.2f MB)", filename, size_mb)

    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Maximum is {MAX_FILE_SIZE_MB} MB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file received.")

    # ── Run the ML pipeline ────────────────────────────────────────────────
    try:
        result: DenoiseResult = run_pipeline(image_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error for file %s", filename)
        raise HTTPException(status_code=500, detail=f"Internal pipeline error: {e}")

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    logger.info(
        "Done — routing: %s | var: %.2f | %.0f ms",
        "BYPASS" if result.was_bypassed else "AI",
        result.noise_variance,
        elapsed_ms,
    )

    return DenoiseResponse(
        original_b64=result.original_b64,
        noise_map_b64=result.noise_map_b64,
        unet_b64=result.unet_b64,
        enhanced_b64=result.enhanced_b64,
        routing_message=result.routing_message,
        noise_variance=result.noise_variance,
        was_bypassed=result.was_bypassed,
        width=result.width,
        height=result.height,
        processing_time_ms=round(elapsed_ms, 1),
    )
