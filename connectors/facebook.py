"""
Phase 8 — Facebook connector (stub).
Fill in the implementation when Facebook Graph API credentials are available.
"""

from __future__ import annotations

from config import FB_PAGE_ID, FB_ACCESS_TOKEN, KEYWORDS, DAYS_BACK


def fetch() -> list[dict]:
    """
    Search Facebook for posts mentioning ZaloPay keywords.

    Returns:
        List of items with keys: id, source, text, images, timestamp
    """
    if not FB_PAGE_ID or not FB_ACCESS_TOKEN:
        raise RuntimeError(
            "Facebook credentials not configured. "
            "Set FB_PAGE_ID, FB_ACCESS_TOKEN in .env — or use dry_run=True."
        )
    raise NotImplementedError("Facebook connector not yet implemented — coming in Phase 8.")
