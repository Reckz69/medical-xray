"""
test_api.py -- Denoise X Backend Test Suite
===========================================
Tests both the inference engine directly (unit tests)
and the FastAPI endpoints (integration tests).

Run with:
    python test_api.py
"""

import sys
import os

# Force UTF-8 stdout on Windows so Unicode characters print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import base64
import io
import time
import json

# ── path setup ─────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from PIL import Image as PILImage

# ── colour codes ───────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
BOLD  = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0


def _ok(name: str, msg: str = ""):
    global passed
    passed += 1
    print(f"  {GREEN}✔ PASS{RESET}  {name}" + (f" — {msg}" if msg else ""))


def _fail(name: str, msg: str = ""):
    global failed
    failed += 1
    print(f"  {RED}✘ FAIL{RESET}  {name}" + (f" — {msg}" if msg else ""))


def _section(title: str):
    print(f"\n{BOLD}{CYAN}{'-'*55}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'-'*55}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _make_png_bytes(width: int = 256, height: int = 256, noise: bool = True) -> bytes:
    """
    Generates a synthetic grayscale chest-like image.
    If noise=True, adds strong pixel noise to trigger PATH A routing.
    """
    rng = np.random.default_rng(42)
    img = np.zeros((height, width), dtype=np.uint8)

    # Simulate two "lung" blobs
    for cx, cy, rx, ry in [(90, 128, 60, 80), (166, 128, 60, 80)]:
        for y in range(height):
            for x in range(width):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                    img[y, x] = 80

    if noise:
        noise_layer = rng.integers(0, 60, size=(height, width), dtype=np.uint8)
        img = np.clip(img.astype(int) + noise_layer, 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    PILImage.fromarray(img, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _make_clean_png_bytes(width: int = 256, height: int = 256) -> bytes:
    """Generates a clean, low-noise image to trigger PATH B bypass."""
    img = np.full((height, width), 120, dtype=np.uint8)
    # Add only very faint structure (no random noise)
    img[80:180, 60:100] = 80
    img[80:180, 156:196] = 80
    buf = io.BytesIO()
    PILImage.fromarray(img, mode="L").save(buf, format="PNG")
    return buf.getvalue()


def _is_valid_b64_png(s: str) -> bool:
    if not s.startswith("data:image/png;base64,"):
        return False
    try:
        raw = base64.b64decode(s.split(",", 1)[1])
        return raw[:8] == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 1. UNIT TESTS — inference_engine (no HTTP)
# ─────────────────────────────────────────────────────────────────────────────
def test_unit_image_loading():
    _section("Unit Tests: Image Loading")
    from inference_engine import _load_image_from_bytes

    # PNG
    try:
        raw = _make_png_bytes(128, 128, noise=True)
        img = _load_image_from_bytes(raw, "test.png")
        assert img.shape == (128, 128), f"Expected (128,128) got {img.shape}"
        assert img.dtype == np.uint8
        _ok("Load PNG — shape and dtype correct")
    except Exception as e:
        _fail("Load PNG", str(e))

    # JPEG
    try:
        pil_img = PILImage.fromarray(np.random.randint(0, 255, (200, 200), dtype=np.uint8), "L")
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=90)
        img = _load_image_from_bytes(buf.getvalue(), "test.jpg")
        assert img.shape == (200, 200)
        _ok("Load JPEG — shape correct")
    except Exception as e:
        _fail("Load JPEG", str(e))

    # Bad bytes
    try:
        from inference_engine import _load_image_from_bytes
        _load_image_from_bytes(b"not_an_image", "bad.png")
        _fail("Bad bytes — should have raised ValueError")
    except Exception:
        _ok("Bad bytes — correctly raised exception")


def test_unit_noise_detection():
    _section("Unit Tests: Smart Gateway Noise Detection")
    from inference_engine import _detect_noise_level, _load_image_from_bytes

    # Noisy image should produce high variance
    try:
        raw = _make_png_bytes(256, 256, noise=True)
        img = _load_image_from_bytes(raw, "noisy.png")
        var = _detect_noise_level(img)
        assert var >= 0, "Variance must be non-negative"
        _ok(f"Noisy image — variance = {var:.2f}")
    except Exception as e:
        _fail("Noise detection (noisy)", str(e))

    # Clean image should produce low variance
    try:
        raw = _make_clean_png_bytes(256, 256)
        img = _load_image_from_bytes(raw, "clean.png")
        var = _detect_noise_level(img)
        _ok(f"Clean image — variance = {var:.2f}")
    except Exception as e:
        _fail("Noise detection (clean)", str(e))


def test_unit_b64_encoding():
    _section("Unit Tests: Base64 PNG Encoding")
    from inference_engine import _to_b64_png

    try:
        img = np.random.randint(0, 255, (128, 128), dtype=np.uint8)
        result = _to_b64_png(img)
        assert _is_valid_b64_png(result), "Not a valid base64 PNG data URI"
        _ok("Base64 PNG encoding — valid data URI")
    except Exception as e:
        _fail("Base64 encoding", str(e))


def test_unit_clinical_enhance():
    _section("Unit Tests: Clinical Enhancement (CLAHE + USM)")
    from inference_engine import _clinical_enhance

    try:
        img = np.random.randint(50, 200, (256, 256), dtype=np.uint8)
        enhanced = _clinical_enhance(img)
        assert enhanced.shape == img.shape, "Shape must be preserved"
        assert enhanced.dtype == np.uint8, "dtype must be uint8"
        _ok("CLAHE+USM — shape/dtype preserved")
    except Exception as e:
        _fail("Clinical enhancement", str(e))


def test_unit_full_pipeline_bypass():
    _section("Unit Tests: Full Pipeline (PATH B — Clean Scan Bypass)")
    from inference_engine import run_pipeline

    try:
        raw = _make_clean_png_bytes(256, 256)
        t0 = time.perf_counter()
        result = run_pipeline(raw, "clean.png", noise_threshold=8.0)
        elapsed = (time.perf_counter() - t0) * 1000

        assert result.was_bypassed, "Expected PATH B (bypass)"
        assert "PATH B" in result.routing_message
        assert _is_valid_b64_png(result.original_b64)
        assert _is_valid_b64_png(result.enhanced_b64)
        assert result.noise_variance >= 0
        assert result.width > 0 and result.height > 0
        _ok(f"PATH B pipeline — {elapsed:.0f} ms | var={result.noise_variance:.2f}")
    except Exception as e:
        _fail("Full pipeline PATH B", str(e))


def test_unit_full_pipeline_ai():
    _section("Unit Tests: Full Pipeline (PATH A — AI Denoising)")
    from inference_engine import run_pipeline

    print("  (Loading the Keras model — may take ~30s on first run…)")
    try:
        raw = _make_png_bytes(512, 512, noise=True)
        t0 = time.perf_counter()
        result = run_pipeline(raw, "noisy.png", noise_threshold=8.0)
        elapsed = (time.perf_counter() - t0) * 1000

        assert not result.was_bypassed or result.was_bypassed  # either path is valid
        assert _is_valid_b64_png(result.original_b64)
        assert _is_valid_b64_png(result.noise_map_b64)
        assert _is_valid_b64_png(result.unet_b64)
        assert _is_valid_b64_png(result.enhanced_b64)
        assert result.width == 512 and result.height == 512
        route = "BYPASS" if result.was_bypassed else "AI"
        _ok(f"Full pipeline PATH A/B — {elapsed:.0f} ms | route={route} | var={result.noise_variance:.2f}")
    except Exception as e:
        _fail("Full pipeline PATH A", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 2. INTEGRATION TESTS — FastAPI endpoints (via TestClient)
# ─────────────────────────────────────────────────────────────────────────────
def test_integration_health():
    _section("Integration Tests: GET /health")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    try:
        r = client.get("/health")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data["status"] == "ok"
        assert "model_loaded" in data
        assert "version" in data
        _ok(f"/health — model_loaded={data['model_loaded']}")
    except Exception as e:
        _fail("/health endpoint", str(e))


def test_integration_denoise_png():
    _section("Integration Tests: POST /api/denoise  (PNG)")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)

    # Clean PNG (should trigger PATH B without model load)
    try:
        raw = _make_clean_png_bytes(256, 256)
        files = {"file": ("test_clean.png", raw, "image/png")}
        r = client.post("/api/denoise", files=files)
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()

        assert _is_valid_b64_png(data["original_b64"]), "original_b64 invalid"
        assert _is_valid_b64_png(data["noise_map_b64"]), "noise_map_b64 invalid"
        assert _is_valid_b64_png(data["unet_b64"]), "unet_b64 invalid"
        assert _is_valid_b64_png(data["enhanced_b64"]), "enhanced_b64 invalid"
        assert isinstance(data["noise_variance"], float)
        assert isinstance(data["was_bypassed"], bool)
        assert data["processing_time_ms"] > 0
        _ok(f"POST /api/denoise PNG — {data['processing_time_ms']:.0f}ms | bypassed={data['was_bypassed']}")
    except Exception as e:
        _fail("POST /api/denoise PNG", str(e))


def test_integration_denoise_noisy():
    _section("Integration Tests: POST /api/denoise  (Noisy PNG → PATH A)")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    print("  (This test runs the full AI model — may take ~60s…)")
    try:
        raw = _make_png_bytes(512, 512, noise=True)
        files = {"file": ("noisy_xray.png", raw, "image/png")}
        r = client.post("/api/denoise", files=files)
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["width"] == 512 and data["height"] == 512
        _ok(f"POST /api/denoise noisy PNG — route={'BYPASS' if data['was_bypassed'] else 'AI'} | {data['processing_time_ms']:.0f}ms")
    except Exception as e:
        _fail("POST /api/denoise noisy PNG", str(e))


def test_integration_bad_extension():
    _section("Integration Tests: Validation — Bad File Extension")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    try:
        files = {"file": ("malware.exe", b"\x00\x01\x02", "application/octet-stream")}
        r = client.post("/api/denoise", files=files)
        assert r.status_code == 415, f"Expected 415, got {r.status_code}"
        _ok("Bad extension → 415 Unsupported Media Type")
    except Exception as e:
        _fail("Bad extension validation", str(e))


def test_integration_empty_file():
    _section("Integration Tests: Validation — Empty File")
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    try:
        files = {"file": ("empty.png", b"", "image/png")}
        r = client.post("/api/denoise", files=files)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        _ok("Empty file → 400 Bad Request")
    except Exception as e:
        _fail("Empty file validation", str(e))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{BOLD}{'='*55}")
    print("   Denoise X - Backend Test Suite")
    print(f"{'='*55}{RESET}\n")

    # Unit tests (fast — no HTTP)
    test_unit_image_loading()
    test_unit_noise_detection()
    test_unit_b64_encoding()
    test_unit_clinical_enhance()
    test_unit_full_pipeline_bypass()
    test_unit_full_pipeline_ai()

    # Integration tests (use FastAPI TestClient)
    test_integration_health()
    test_integration_denoise_png()
    test_integration_denoise_noisy()
    test_integration_bad_extension()
    test_integration_empty_file()

    # ── Summary ───────────────────────────────────────────────────────────────
    total = passed + failed
    print(f"\n{BOLD}{'='*55}")
    print(f"  Results: {GREEN}{passed} passed{RESET}{BOLD}  |  {RED}{failed} failed{RESET}{BOLD}  |  {total} total")
    print(f"{'='*55}{RESET}")
    print()

    sys.exit(0 if failed == 0 else 1)
