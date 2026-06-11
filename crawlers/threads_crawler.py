"""
Threads crawler — Playwright public keyword search → bronze JSONL.

Runs OFFLINE (Colab / a worker / locally), NOT inside the AgentBase runtime: it drives a headless
Chromium browser, which is too heavy and easily blocked from datacenter IPs. It writes raw records to
data/raw/threads_<ts>.jsonl; the agent's connectors/threads.py reads that bronze file.

Raw record schema (SocialPost) — kept rich on purpose; the connector normalizes on read:
    post_hash_id, platform, matched_keyword, author, content, posted_at, crawled_at, images_base64

Run:
    # one-off install (not part of the agent image):
    pip install -r requirements-crawler.txt && python -m playwright install chromium
    python crawlers/threads_crawler.py            # crawls config.KEYWORDS, writes bronze

In Colab: import and call crawl(); a running event loop is handled automatically.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import random
import urllib.parse
from datetime import datetime, timezone

import aiohttp
from dateutil import parser
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

from config import KEYWORDS, DAYS_BACK
from crawlers import bronze

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class SocialPost(BaseModel):
    post_hash_id: str = Field(description="MD5 of content for dedup")
    platform: str = Field(description="Source platform")
    matched_keyword: str = Field(description="Keyword that surfaced this post")
    author: str = Field(description="Display name")
    content: str = Field(description="Raw post text")
    posted_at: str = Field(description="When the user posted (YYYY-MM-DD HH:MM:SS)")
    crawled_at: str = Field(description="When we crawled it")
    images_base64: list = Field(default=[], description="Attached images as base64 data URIs")


async def _fetch_and_encode_image(session: aiohttp.ClientSession, image_url: str) -> str | None:
    """Download an image and return it as a base64 data URI (None on failure)."""
    try:
        async with session.get(image_url, timeout=10) as response:
            if response.status == 200:
                content_type = response.headers.get("Content-Type", "image/jpeg")
                data = await response.read()
                encoded = base64.b64encode(data).decode("utf-8")
                return f"data:{content_type};base64,{encoded}"
            return None
    except Exception as e:
        print(f"    [!] image fetch failed ({image_url[:30]}...): {e}")
        return None


async def _crawl_keyword(
    context, session, keyword: str, scroll_times: int, max_age_hours: int
) -> list[dict]:
    """Scrape one keyword's Threads search results into SocialPost dicts."""
    search_url = f"https://www.threads.net/search?q={urllib.parse.quote(keyword)}&serp_type=default"
    posts: list[dict] = []
    page = await context.new_page()
    print(f"\n🔍 [Search] keyword: '{keyword}'...")

    try:
        await page.goto(search_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        for _ in range(scroll_times):
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)

        articles = await page.locator('[role="article"]').all()
        if not articles:
            articles = await page.locator('div[data-pressable-container="true"]').all()

        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for article in articles:
            try:
                # ── time filter ──
                posted_at_str = "Unknown"
                time_el = article.locator("time")
                if await time_el.count() > 0:
                    dt_str = await time_el.first.get_attribute("datetime")
                    if dt_str:
                        post_time = parser.isoparse(dt_str)
                        age_h = (datetime.now(timezone.utc) - post_time).total_seconds() / 3600
                        if age_h > max_age_hours:
                            continue
                        posted_at_str = post_time.strftime("%Y-%m-%d %H:%M:%S")

                # ── text ──
                lines = [ln.strip() for ln in (await article.inner_text()).split("\n") if ln.strip()]
                author, content = "", ""
                if len(lines) >= 2:
                    author = lines[0]
                    if author.lower() in ("follow", "theo dõi") and len(lines) > 2:
                        author = lines[1]
                        content = " ".join(lines[2:min(8, len(lines))])
                    else:
                        content = " ".join(lines[1:min(8, len(lines))])

                # ── images (download + base64, in parallel) ──
                urls = []
                for img in await article.locator("img").all():
                    src = await img.get_attribute("src")
                    alt = (await img.get_attribute("alt")) or ""
                    if src and "http" in src and "profile" not in alt.lower():
                        urls.append(src)
                images_b64: list = []
                if urls:
                    results = await asyncio.gather(*[_fetch_and_encode_image(session, u) for u in urls])
                    images_b64 = [r for r in results if r]
                    if images_b64:
                        print(f"  📸 encoded {len(images_b64)} image(s) for {author}")

                # ── keep if enough text OR an image ──
                if len(content) > 15 or images_b64:
                    hash_input = content if content else f"{author}_{posted_at_str}"
                    post = SocialPost(
                        post_hash_id=hashlib.md5(hash_input.encode("utf-8")).hexdigest(),
                        platform="Threads",
                        matched_keyword=keyword,
                        author=author,
                        content=content,
                        posted_at=posted_at_str,
                        crawled_at=crawled_at,
                        images_base64=images_b64,
                    )
                    posts.append(post.model_dump())
            except Exception:
                continue
    except Exception as e:
        print(f"  ❌ error on '{keyword}': {e}")
    finally:
        await page.close()

    print(f"  ✅ {len(posts)} post(s) for '{keyword}'")
    return posts


async def _run(keywords: list[str], scroll_times: int, max_age_hours: int) -> list[dict]:
    all_records: list[dict] = []
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=_USER_AGENT)
            for kw in keywords:
                all_records.extend(await _crawl_keyword(context, session, kw, scroll_times, max_age_hours))
                await asyncio.sleep(random.uniform(3.0, 6.0))  # anti-bot jitter
            await browser.close()

    # global dedup by content hash
    seen, unique = set(), []
    for rec in all_records:
        h = rec["post_hash_id"]
        if h not in seen:
            seen.add(h)
            unique.append(rec)
    return unique


def crawl(
    keywords: list[str] | None = None,
    scroll_times: int = 4,
    max_age_hours: int | None = None,
    save_bronze: bool = True,
) -> list[dict]:
    """
    Crawl Threads for the given keywords (default: config.KEYWORDS), dedup, and (optionally)
    save a bronze JSONL. Returns the raw SocialPost records.

    Works both as a script (no running loop) and in Colab (running loop → nest_asyncio).
    """
    keywords = keywords or KEYWORDS
    max_age_hours = max_age_hours if max_age_hours is not None else DAYS_BACK * 24

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        records = loop.run_until_complete(_run(keywords, scroll_times, max_age_hours))
    else:
        records = asyncio.run(_run(keywords, scroll_times, max_age_hours))

    print("\n" + "=" * 56)
    print(f"📊 {len(records)} unique post(s) across {len(keywords)} keyword(s)")
    with_images = sum(1 for r in records if r.get("images_base64"))
    print(f"   with images: {with_images}")
    if save_bronze and records:
        path = bronze.save(records, source="threads")
        print(f"💾 bronze saved: {path}")
    print("=" * 56)
    return records


if __name__ == "__main__":
    crawl()
