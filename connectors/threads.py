"""
Threads connector — reads the latest bronze JSONL produced by the offline Playwright crawler
(crawlers/threads_crawler.py) and normalizes it into pipeline items.

Crawling itself does NOT run here (or in the AgentBase runtime) — it's a separate offline step.
See crawlers/threads_crawler.py and crawlers/bronze.py.

Bronze record (SocialPost) → normalized item:
    post_hash_id → id, platform → source, content → text, images_base64 → images,
    posted_at → timestamp  (+ author, matched_keyword kept as extras)
"""

from __future__ import annotations

from crawlers import bronze

SOURCE = "threads"


def _to_item(rec: dict) -> dict:
    posted = rec.get("posted_at") or ""
    if not posted or posted == "Unknown":
        posted = rec.get("crawled_at", "")
    return {
        "id":              rec.get("post_hash_id", ""),
        "source":          SOURCE,
        "text":            rec.get("content", ""),
        "images":          rec.get("images_base64", []),  # base64 data URIs
        "timestamp":       posted,
        "author":          rec.get("author", ""),
        "matched_keyword": rec.get("matched_keyword", ""),
        "post_url":        rec.get("post_url", ""),
    }


def fetch() -> list[dict]:
    """
    Load recent Threads posts from the database, falling back to local files if empty.
    """
    import os
    import config
    
    token = os.getenv("THREADS_ACCESS_TOKEN") or config.THREADS_TOKEN
    if not token or token == "...":
        raise RuntimeError(
            "Threads credentials not configured. "
            "Set THREADS_ACCESS_TOKEN in .env — or use dry_run=True."
        )

    from main import SessionLocal, RawPost
    
    db = SessionLocal()
    try:
        posts = db.query(RawPost).filter(RawPost.platform == "Threads").all()
        if not posts:
            print("[connector.threads] No raw posts found in database. Falling back to offline bronze files...")
            records = bronze.load_latest(SOURCE)
            if not records:
                raise RuntimeError(
                    "No Threads data found in database or local data/raw/ files. "
                    "Please run the crawler first or use dry_run=True."
                )
            return [_to_item(r) for r in records]
        
        records = []
        for p in posts:
            records.append({
                "post_hash_id": p.post_hash_id,
                "platform": p.platform,
                "matched_keyword": p.matched_keyword,
                "author": p.author,
                "content": p.content,
                "posted_at": p.posted_at,
                "crawled_at": p.crawled_at,
                "post_url": p.post_url,
                "images_base64": p.images_base64 or []
            })
        return [_to_item(r) for r in records]
    finally:
        db.close()
