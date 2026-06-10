"""
Stage 6 — Domain and segment classification.
Assigns each issue to a domain (e.g. Payment) and segment (e.g. Top-up).

Two separate LLM calls: domain first, then segment (segment options depend on domain).
"""

from __future__ import annotations

from config import DOMAINS, SEGMENTS
from llm_client import llm


def classify_domain(issue: str) -> str:
    label = llm.chat(
        system=(
            f"Classify the issue into exactly one domain.\n"
            f"Reply with the domain name only — no punctuation, no explanation.\n"
            f"Domains: {', '.join(DOMAINS)}"
        ),
        user=issue,
        max_tokens=10,
    )
    return label if label in DOMAINS else "Other"


def classify_segment(issue: str, domain: str) -> str:
    options = SEGMENTS.get(domain, ["General"])
    label = llm.chat(
        system=(
            f"Classify the issue into exactly one segment.\n"
            f"Reply with the segment name only — no punctuation, no explanation.\n"
            f"Segments: {', '.join(options)}"
        ),
        user=issue,
        max_tokens=10,
    )
    return label if label in options else options[0]
