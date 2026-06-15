"""
image_utils.py — Image downgrade utilities for the crawler pipeline.

Purpose:
    Reduce image resolution/size before storing as base64 data URIs.
    We only need images good enough for AI reports and human review,
    not full HD / 4K originals.

Format comparison for base64 DB storage:
    PNG   — lossless, largest size. Avoid for photos.
    JPEG  — lossy, compact. Good, but WebP is better.
    WebP  — lossy, ~30-50% smaller than JPEG at same quality. ✅ Default.
            Supported by Gemini Vision, GPT-4V, and all modern browsers.

Default target: max_height=720 (HD 720p), WebP quality=75.
    - Readable text in screenshots/post images
    - ~5-15× smaller base64 payload vs original PNG/JPEG full-res
    - Aspect ratio is always preserved

Usage:
    from crawlers.image_utils import downgrade_image

    smaller = downgrade_image(data_uri)                              # WebP 720p, q=75
    smaller = downgrade_image(data_uri, max_height=480)             # WebP 480p
    smaller = downgrade_image(data_uri, fmt="JPEG", quality=80)     # force JPEG
"""

from __future__ import annotations

import base64
import io
from typing import Literal, Optional

# Supported output formats and their MIME types
_MIME = {
    "WEBP": "image/webp",
    "JPEG": "image/jpeg",
    "PNG":  "image/png",
}

OutputFormat = Literal["WEBP", "JPEG", "PNG"]


def downgrade_image(
    data_uri: str,
    max_height: int = 720,
    quality: int = 75,
    fmt: OutputFormat = "WEBP",
) -> Optional[str]:
    """Resize + re-encode a base64 data URI image.

    - Height is capped at *max_height*; width scales proportionally.
    - If the image is already shorter than *max_height* it is only re-encoded
      (no upscaling).
    - Aspect ratio is always preserved.
    - Default output format is WebP: ~30-50% smaller than JPEG at same quality,
      fully supported by Gemini Vision, GPT-4V, and modern browsers.
    - Returns the original *data_uri* unchanged if Pillow is unavailable or
      any error occurs (crawler never crashes).

    Args:
        data_uri:   Input base64 data URI, e.g. "data:image/jpeg;base64,..."
        max_height: Maximum output height in pixels. Default 720 (HD 720p).
        quality:    Compression quality 1-95. Default 75.
                    For WebP: 75 ≈ JPEG 90+ visually.
        fmt:        Output format — "WEBP" (default), "JPEG", or "PNG".

    Returns:
        New base64 data URI string, or original on error.
    """
    try:
        from PIL import Image  # lazy import — Pillow only needed at crawl time
    except ImportError:
        # Pillow not installed — return original unchanged, never crash
        return data_uri

    try:
        # ── decode base64 payload ──
        if "," not in data_uri:
            return None
        _header, b64_payload = data_uri.split(",", 1)

        raw_bytes = base64.b64decode(b64_payload)
        img = Image.open(io.BytesIO(raw_bytes))

        # WebP/JPEG cannot handle palette or RGBA — convert to RGB
        if fmt in ("WEBP", "JPEG") and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        orig_w, orig_h = img.size

        # ── resize only if taller than max_height ──
        if orig_h > max_height:
            ratio = max_height / orig_h
            new_w = max(1, int(orig_w * ratio))
            img = img.resize((new_w, max_height), Image.LANCZOS)

        # ── re-encode ──
        buf = io.BytesIO()
        save_kwargs: dict = {"format": fmt, "quality": quality}
        if fmt == "JPEG":
            save_kwargs["optimize"] = True
        img.save(buf, **save_kwargs)

        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        mime = _MIME.get(fmt, "image/webp")
        return f"data:{mime};base64,{encoded}"

    except Exception as e:
        # Never crash the crawler — fall back to original
        print(f"    [image_utils] downgrade failed: {e}")
        return data_uri
