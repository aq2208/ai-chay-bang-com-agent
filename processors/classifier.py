"""
Stage 6 — Domain and segment classification (RAG-grounded).

Two separate LLM calls: domain first, then segment (segment options depend on domain).

Instead of handing the LLM a bare list of label names, we retrieve the most similar
taxonomy/known-issue entries from the knowledge base and inject them as grounding
("reference examples"). This sharply improves precision on ambiguous Vietnamese
complaints. Output is still strictly validated against DOMAINS / SEGMENTS — if retrieval
is unavailable (index not built), it degrades cleanly to bare-list classification.
"""

from __future__ import annotations

import re

from config import DOMAINS, SEGMENTS
from llm_client import llm


def _definition(text: str) -> str:
    m = re.search(r"^Definition:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _domain_grounding(issue: str) -> str:
    """Build reference-example text from taxonomy + solution retrieval (best-effort)."""
    try:
        from knowledge_base.search import search_taxonomy, search
        tax = search_taxonomy(issue, top_k=4)
        sol = search(issue, top_k=2)
    except Exception:
        return ""

    lines = []
    for m in tax:
        defn = _definition(m["text"])
        hint = f'{m["domain"]} / {m["segment"]}'
        lines.append(f"- {hint}{f': {defn}' if defn else ''}")
    for m in sol:
        if m.get("domain"):
            lines.append(f'- (known solution doc) → Domain: {m["domain"]}')

    if not lines:
        return ""
    return "Reference examples (similar issues → their domain/segment):\n" + "\n".join(lines) + "\n\n"


def _segment_grounding(issue: str, domain: str) -> str:
    """Build reference-example text restricted to the chosen domain (best-effort)."""
    try:
        from knowledge_base.search import search_taxonomy
        tax = search_taxonomy(issue, top_k=4, domain=domain)
    except Exception:
        return ""

    lines = []
    for m in tax:
        defn = _definition(m["text"])
        lines.append(f'- {m["segment"]}{f": {defn}" if defn else ""}')

    if not lines:
        return ""
    return f"Reference examples for {domain} segments:\n" + "\n".join(lines) + "\n\n"


def classify_domain(issue: str) -> str:
    grounding = _domain_grounding(issue)
    label = llm.chat(
        system=(
            "Classify the issue into exactly one domain.\n"
            "Reply with the domain name only — no punctuation, no explanation.\n\n"
            f"{grounding}"
            f"Domains: {', '.join(DOMAINS)}"
        ),
        user=issue,
        max_tokens=10,
    )
    label = label.strip()
    return label if label in DOMAINS else "Other"


def classify_segment(issue: str, domain: str) -> str:
    options = SEGMENTS.get(domain, ["General"])
    grounding = _segment_grounding(issue, domain)
    label = llm.chat(
        system=(
            "Classify the issue into exactly one segment.\n"
            "Reply with the segment name only — no punctuation, no explanation.\n\n"
            f"{grounding}"
            f"Segments: {', '.join(options)}"
        ),
        user=issue,
        max_tokens=10,
    )
    label = label.strip()
    return label if label in options else options[0]
