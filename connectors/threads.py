"""
Phase 8 — Threads connector (stub).
Fill in the implementation when Threads API credentials are available.
"""

from __future__ import annotations

from config import THREADS_TOKEN, KEYWORDS, DAYS_BACK


def fetch() -> list[dict]:
    """
    Search Threads for posts mentioning ZaloPay keywords.

    Returns:
        List of items with keys: id, source, text, images, timestamp
    """
    if not THREADS_TOKEN:
        raise RuntimeError(
            "Threads credentials not configured. "
            "Set THREADS_ACCESS_TOKEN in .env — or use dry_run=True."
        )
    raise NotImplementedError("Threads connector not yet implemented — coming in Phase 8.")
