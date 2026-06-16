"""
Stage 5 — Issue extraction.
Converts messy user complaints into clean, consistent English issue statements.

Input : raw post text (Vietnamese/English) + optional image description
Output: one clean English sentence e.g. "Visa card top-up failing with error E5001"
"""

from __future__ import annotations

from llm_client import llm

SKIP = "SKIP"

_SYSTEM = (
    "You are an issue extractor for the Zalopay app support team.\n"
    "Extract the core technical issue from this user complaint.\n"
    "Output exactly one clear English sentence, 8–15 words.\n"
    "Focus on: what failed, which feature, any visible error code.\n"
    "Do not include emotional language, user names, or opinions.\n"
    "If multiple issues are mentioned, extract only the most severe one.\n"
    "Output exactly 'SKIP' (no other text) if ANY of the following is true:\n"
    "  - The content contains no real technical problem (e.g. praise, general questions, spam).\n"
    "  - The content is completely unrelated to the Zalopay app.\n"
    "  - The content is too vague to identify any specific failure."
)


def extract_issue(text: str, image_description: str = "") -> str:
    content = text
    if image_description:
        content += f"\n[Image shows: {image_description}]"

    return llm.chat(system=_SYSTEM, user=content, max_tokens=60)


def is_valid_issue(extracted: str) -> bool:
    """Return False for SKIP sentinel or empty extraction results."""
    return bool(extracted) and extracted.strip().upper() != SKIP
