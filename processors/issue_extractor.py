"""
Stage 5 — Issue extraction.
Converts messy user complaints into clean, consistent English issue statements.

Input : raw post text (Vietnamese/English) + optional image description
Output: one clean English sentence e.g. "Visa card top-up failing with error E5001"
"""

from __future__ import annotations

from llm_client import llm

_SYSTEM = (
    "Extract the core technical issue from this user complaint.\n"
    "Output exactly one clear English sentence, 8–15 words.\n"
    "Focus on: what failed, which feature, any visible error code.\n"
    "Do not include emotional language, user names, or opinions.\n"
    "If multiple issues are mentioned, extract only the most severe one."
)


def extract_issue(text: str, image_description: str = "") -> str:
    content = text
    if image_description:
        content += f"\n[Image shows: {image_description}]"

    return llm.chat(system=_SYSTEM, user=content, max_tokens=60)
