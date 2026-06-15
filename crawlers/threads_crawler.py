"""
Threads crawler — Playwright public keyword search → bronze JSONL.

Runs OFFLINE (Colab / a worker / locally), NOT inside the AgentBase runtime: it drives a headless
Chromium browser, which is too heavy and easily blocked from datacenter IPs. It writes raw records to
data/raw/threads_<ts>.jsonl; the agent's connectors/threads.py reads that bronze file.

Raw record schema (SocialPost) — kept rich on purpose; the connector normalizes on read:
    post_hash_id, platform, matched_keyword, author, content, posted_at, crawled_at, post_url, images_base64

Input:
    None (reads crawler parameters dynamically from configuration).

Output:
    Raw post records saved to data/raw/ as `threads_<YYYYMMDD_HHMM>.jsonl`.

Configs read from config.py:
    - KEYWORDS: List of keywords/search queries to crawl on Threads.
    - DAYS_BACK: Time window in days to fetch posts (used to calculate max age filter).
    - SCROLL_TIMES: Number of times to scroll down to load search results.

Run:
    # one-off install (not part of the agent image):
    pip install -r requirements-crawler.txt && python -m playwright install chromium
    python crawlers/threads_crawler.py            # crawls config.KEYWORDS, writes bronze

Run:
    python -m crawlers.threads_crawler


In Colab: import and call crawl(); a running event loop is handled automatically.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import random
import urllib.parse
from datetime import datetime, timezone

import aiohttp
from dateutil import parser
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

from config import KEYWORDS, DAYS_BACK, SCROLL_TIMES
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
    post_url: str = Field(default="", description="Original post URL or fallback profile link")
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

        async def _bypass_login_modal():
            try:
                await page.evaluate("""() => {
                    const loginTexts = ["Continue with Instagram", "Say more with Threads", "Log in or sign up for Threads"];
                    let targetElement = null;
                    for (const text of loginTexts) {
                        const matches = Array.from(document.querySelectorAll('*')).filter(x => x.textContent && x.textContent.includes(text));
                        if (matches.length > 0) {
                            targetElement = matches.pop(); // Deepest child containing the text
                            break;
                        }
                    }

                    if (targetElement) {
                        let current = targetElement;
                        let deepestSafeParent = null;
                        while (current && current !== document.body) {
                            const hasTime = current.querySelector('time');
                            if (!hasTime) {
                                deepestSafeParent = current;
                            } else {
                                break;
                            }
                            current = current.parentElement;
                        }
                        if (deepestSafeParent) {
                            deepestSafeParent.remove();
                        }
                    }
                    document.body.style.setProperty('overflow', 'auto', 'important');
                    document.documentElement.style.setProperty('overflow', 'auto', 'important');
                }""")
            except Exception as e:
                print(f"  [!] bypass login modal failed: {e}")

        # Track keys to count new posts during scrolling
        seen_keys = set()
        
        async def _get_new_posts_count() -> int:
            articles = await page.locator('[role="article"]').all()
            if not articles:
                articles = await page.locator('div[data-pressable-container="true"]').all()
            
            new_count = 0
            for art in articles:
                try:
                    text = await art.inner_text()
                    h = hashlib.md5(text.encode("utf-8")).hexdigest()
                    if h not in seen_keys:
                        seen_keys.add(h)
                        new_count += 1
                except Exception:
                    continue
            return new_count

        async def _log_articles_stats(prefix: str):
            articles = await page.locator('[role="article"]').all()
            if not articles:
                articles = await page.locator('div[data-pressable-container="true"]').all()
            
            times = []
            for art in articles:
                try:
                    time_el = art.locator("time")
                    if await time_el.count() > 0:
                        dt_str = await time_el.first.get_attribute("datetime")
                        if dt_str:
                            from dateutil import parser
                            times.append(parser.isoparse(dt_str))
                except Exception:
                    continue
            
            count = len(articles)
            if times:
                furthest = min(times).strftime("%Y-%m-%d %H:%M:%S")
                nearest = max(times).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    {prefix} - found {count} posts, furthest: {furthest}, nearest: {nearest}")
            else:
                print(f"    {prefix} - found {count} posts, no timestamps found")

        await _bypass_login_modal()
        await _get_new_posts_count()
        await _log_articles_stats("First search")

        consecutive_empty_scrolls = 0
        for scroll_idx in range(1, scroll_times + 1):
            await _bypass_login_modal()
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)
            
            new_found = await _get_new_posts_count()
            await _log_articles_stats(f"Scroll {scroll_idx}")
            if new_found == 0:
                consecutive_empty_scrolls += 1
            else:
                consecutive_empty_scrolls = 0
                
            if consecutive_empty_scrolls >= 2:
                print(f"    🛑 [{scroll_idx}] 2 consecutive scrolls with 0 new posts. Stopping scroll for keyword '{keyword}'...")
                break

        await _bypass_login_modal()
        articles = await page.locator('[role="article"]').all()
        if not articles:
            articles = await page.locator('div[data-pressable-container="true"]').all()

        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        post_times = []

        for article in articles:
            try:
                # ── post URL ──
                post_url = ""
                try:
                    post_link = article.locator('a[href*="/post/"]')
                    if await post_link.count() > 0:
                        href = await post_link.first.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                post_url = f"https://www.threads.net{href}"
                            else:
                                post_url = href
                except Exception:
                    pass

                # ── time filter ──
                posted_at_str = "Unknown"
                time_el = article.locator("time")
                if await time_el.count() > 0:
                    dt_str = await time_el.first.get_attribute("datetime")
                    if dt_str:
                        post_time = parser.isoparse(dt_str)
                        post_times.append(post_time)
                        age_h = (datetime.now(timezone.utc) - post_time).total_seconds() / 3600
                        if max_age_hours is not None and age_h > max_age_hours:
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
                    if not post_url and author:
                        clean_author = author.strip().lstrip("@")
                        if clean_author:
                            post_url = f"https://www.threads.net/@{clean_author}"
                    hash_input = content if content else f"{author}_{posted_at_str}"
                    post = SocialPost(
                        post_hash_id=hashlib.md5(hash_input.encode("utf-8")).hexdigest(),
                        platform="Threads",
                        matched_keyword=keyword,
                        author=author,
                        content=content,
                        posted_at=posted_at_str,
                        crawled_at=crawled_at,
                        post_url=post_url,
                        images_base64=images_b64,
                    )
                    posts.append(post.model_dump())
            except Exception:
                continue

        furthest_str = "N/A"
        nearest_str = "N/A"
        if post_times:
            oldest_time = min(post_times)
            newest_time = max(post_times)
            furthest_str = oldest_time.strftime("%d/%m/%Y")
            nearest_str = newest_time.strftime("%d/%m/%Y")
        print(f"  found total {len(articles)} post(s), furthest post is: {furthest_str}, nearest post is: {nearest_str}")
    except Exception as e:
        print(f"  ❌ error on '{keyword}': {e}")
    finally:
        await page.close()

    print(f"  ✅ {len(posts)} post(s) for '{keyword}'")
    return posts


async def _run(keywords: list[str], scroll_times: int, max_age_hours: int) -> list[dict]:
    load_dotenv()
    all_records: list[dict] = []
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            storage_state = None
            env_auth_state = os.getenv("THREADS_AUTH_STATE_JSON")
            auth_path = os.path.join("data", "auth_state.json")
            
            if env_auth_state:
                try:
                    import json
                    storage_state = json.loads(env_auth_state)
                    print("🔑 [Auth] Loaded session from THREADS_AUTH_STATE_JSON environment variable.")
                except Exception as e:
                    print(f"⚠️ [Auth] Failed to parse THREADS_AUTH_STATE_JSON environment variable: {e}")
            
            if not storage_state and os.path.exists(auth_path):
                storage_state = auth_path
                print(f"🔑 [Auth] Loaded session from storage state file: {auth_path}")
            
            if storage_state:
                context = await browser.new_context(user_agent=_USER_AGENT, storage_state=storage_state)
            else:
                context = await browser.new_context(user_agent=_USER_AGENT)
                token = os.getenv("THREADS_SESSION_ID") or os.getenv("THREADS_TOKEN")
                if token:
                    if "=" in token:
                        cookies = []
                        for pair in token.split(";"):
                            pair = pair.strip()
                            if "=" in pair:
                                name, val = pair.split("=", 1)
                                cookies.append({
                                    "name": name,
                                    "value": val,
                                    "domain": ".threads.net",
                                    "path": "/"
                                })
                        if cookies:
                            await context.add_cookies(cookies)
                            print(f"🔑 [Auth] Added {len(cookies)} cookies from THREADS_SESSION_ID / THREADS_TOKEN.")
                    else:
                        cookies = [
                            {
                                "name": "sessionid",
                                "value": token,
                                "domain": ".threads.net",
                                "path": "/",
                                "secure": True,
                                "httpOnly": True
                            }
                        ]
                        await context.add_cookies(cookies)
                        print(f"🔑 [Auth] Added sessionid cookie from THREADS_SESSION_ID / THREADS_TOKEN.")
                else:
                    print("🔓 [Auth] No auth state or token found. Proceeding as guest (anonymous search)...")

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
    scroll_times: int | None = None,
    max_age_hours: int | None = None,
    save_bronze: bool = True,
) -> list[dict]:
    """
    Crawl Threads for the given keywords (default: config.KEYWORDS), dedup, and (optionally)
    save a bronze JSONL. Returns the raw SocialPost records.

    Works both as a script (no running loop) and in Colab (running loop → nest_asyncio).
    """
    keywords = keywords or KEYWORDS
    scroll_times = scroll_times if scroll_times is not None else SCROLL_TIMES
    if max_age_hours is None:
    max_age_hours = None if DAYS_BACK == 0 else DAYS_BACK * 24

    print("=" * 56)
    print("🚀 Starting Threads Crawler...")
    print(f"   Keywords:     {keywords}")
    print(f"   Scroll Times: {scroll_times}")
    print(f"   Max Age:      {max_age_hours} hours")
    print("=" * 56)

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
    if save_bronze:
        path = bronze.save(records, source="threads")
        print(f"💾 bronze saved: {path}")
    print("=" * 56)

    # Set step output for GitHub Actions if environment variable is present
    import os
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        try:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"has_posts={'true' if records else 'false'}\n")
        except Exception as e:
            print(f"[crawler] Failed to write to GITHUB_OUTPUT: {e}")

    return records


if __name__ == "__main__":
    crawl()
