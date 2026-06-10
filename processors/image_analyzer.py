"""
Stage 3 — Image analysis (Social Media job only).
Describes screenshots in posts and optionally matches them against
team-provided sample images in sample_images/<Domain>/.

Flow:
  1. load_sample_images() — called once at job startup, loads all PNGs/JPGs as base64
  2. analyze_image(url, samples) — per post: sends user screenshot + samples to Vision LLM
  3. Returns a dict with description, matched domain, confidence

If sample_images/ is empty (team hasn't added any yet), the analyzer still runs
and returns a plain description without domain matching.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from llm_client import llm

SAMPLE_DIR = Path(__file__).parent.parent / "sample_images"

_SYSTEM = (
    "You are a mobile app technical analyst. "
    "Analyze screenshots to identify UI errors, error messages, and failure states. "
    "Be concise and technical."
)


def load_sample_images(folder: str | Path | None = None) -> list[dict]:
    """
    Load all reference images from sample_images/<Domain>/ as base64.
    Called once at job startup — not per post.

    Returns:
        List of {"data": b64str, "media_type": str, "label": str, "domain": str}
        Empty list if no sample images are found (analyzer still works, just no comparison).
    """
    root = Path(folder) if folder else SAMPLE_DIR
    samples = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        data = base64.standard_b64encode(path.read_bytes()).decode()
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        samples.append({
            "data":       data,
            "media_type": media_type,
            "label":      path.stem.replace("_", " "),
            "domain":     path.parent.name.replace("_", " "),
        })
    return samples


def analyze_image(image_url: str, samples: list[dict] | None = None) -> dict:
    """
    Analyze a screenshot from a social media post.

    Args:
        image_url: public URL of the user screenshot
        samples:   list from load_sample_images() — pass [] or None to skip comparison

    Returns:
        {
            "description":    "one English sentence describing the technical issue",
            "matched_sample": "label of the closest reference sample, or null",
            "domain":         "matched domain (Payment / QR Code / ...) or Other",
            "confidence":     "high | medium | low",
        }
    """
    images: list[dict] = [{"type": "url", "url": image_url}]

    if samples:
        for s in samples:
            images.append({
                "type":       "base64",
                "data":       s["data"],
                "media_type": s["media_type"],
            })
        sample_labels = ", ".join(f'{s["label"]} ({s["domain"]})' for s in samples)
        prompt = (
            f"The first image is a user screenshot from a social media complaint.\n"
            f"The remaining {len(samples)} images are labeled reference samples: {sample_labels}.\n\n"
            "Identify the technical issue shown and find the closest matching reference.\n"
            "Reply ONLY with valid JSON (no markdown fences):\n"
            '{"description": "<one English sentence>", '
            '"matched_sample": "<label or null>", '
            '"domain": "<domain or Other>", '
            '"confidence": "<high|medium|low>"}'
        )
    else:
        prompt = (
            "Describe the technical issue shown in this screenshot in one clear English sentence.\n"
            "Reply ONLY with valid JSON (no markdown fences):\n"
            '{"description": "<one English sentence>", '
            '"matched_sample": null, '
            '"domain": "Other", '
            '"confidence": "low"}'
        )

    raw = llm.vision(system=_SYSTEM, prompt=prompt, images=images, max_tokens=200)

    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    """Extract JSON from LLM output, return fallback dict on parse failure."""
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    return {
        "description":    raw.strip() or "Unable to parse image.",
        "matched_sample": None,
        "domain":         "Other",
        "confidence":     "low",
    }
