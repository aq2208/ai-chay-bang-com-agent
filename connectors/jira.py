"""
Phase 8 — Jira connector (stub).
Fill in the implementation when real Jira credentials are available.
"""

from __future__ import annotations

from config import JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, DAYS_BACK


def fetch() -> list[dict]:
    """
    Fetch recent ZaloPay complaint tickets from Jira.

    Returns:
        List of items with keys: id, source, text, images, timestamp
    """
    if not JIRA_URL or not JIRA_EMAIL or not JIRA_API_TOKEN:
        raise RuntimeError(
            "Jira credentials not configured. "
            "Set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env — or use dry_run=True."
        )
    raise NotImplementedError("Jira connector not yet implemented — coming in Phase 8.")
