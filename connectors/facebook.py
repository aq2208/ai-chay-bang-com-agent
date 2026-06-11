"""
Facebook Graph API connector.
Fetches posts and comments from one or more ZaloPay Facebook pages.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from config import FB_PAGE_IDS, FB_ACCESS_TOKEN, KEYWORDS, DAYS_BACK

_BASE = "https://graph.facebook.com/v20.0"


def fetch() -> list[dict]:
    """
    Fetch posts + comments from all pages in FB_PAGE_IDS for the past DAYS_BACK days.

    Returns:
        List of items with keys: id, source, text, images, timestamp
    """
    if not FB_PAGE_IDS or not FB_ACCESS_TOKEN:
        raise RuntimeError(
            "Facebook credentials not configured. "
            "Set FB_PAGE_IDS and FB_ACCESS_TOKEN in .env — or use dry_run=True."
        )

    since_ts = int((datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)).timestamp())
    items: list[dict] = []

    for page_id in FB_PAGE_IDS:
        items.extend(_fetch_one_page(page_id, since_ts))

    return items


# ── Private helpers ────────────────────────────────────────────────────────

def _fetch_one_page(page_id: str, since_ts: int) -> list[dict]:
    items = []
    for post in _get_feed(page_id, since_ts):
        text = post.get("message") or post.get("story") or ""
        if text and _matches(text):
            items.append(_make_item(post["id"], text, _images(post), post["created_time"]))

        for comment in _get_comments(post["id"]):
            ctext = comment.get("message", "")
            if ctext and _matches(ctext):
                items.append(_make_item(comment["id"], ctext, [], comment["created_time"]))
    return items


def _get_feed(page_id: str, since_ts: int) -> list[dict]:
    params = {
        "access_token": FB_ACCESS_TOKEN,
        "fields": "id,message,story,created_time,attachments{media{image{src}},type}",
        "since": since_ts,
        "limit": 100,
    }
    return _paginate(f"{_BASE}/{page_id}/feed", params)


def _get_comments(post_id: str) -> list[dict]:
    params = {
        "access_token": FB_ACCESS_TOKEN,
        "fields": "id,message,created_time",
        "limit": 100,
    }
    return _paginate(f"{_BASE}/{post_id}/comments", params)


def _paginate(url: str, params: dict, max_pages: int = 10) -> list[dict]:
    results: list[dict] = []
    for _ in range(max_pages):
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("data", []))
        next_url = body.get("paging", {}).get("next")
        if not next_url:
            break
        url, params = next_url, {}
    return results


def _matches(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in KEYWORDS)


def _images(post: dict) -> list[str]:
    urls = []
    for att in (post.get("attachments") or {}).get("data", []):
        src = ((att.get("media") or {}).get("image") or {}).get("src")
        if src:
            urls.append(src)
    return urls


def _make_item(item_id: str, text: str, images: list[str], timestamp: str) -> dict:
    return {"id": item_id, "source": "facebook", "text": text, "images": images, "timestamp": timestamp}
