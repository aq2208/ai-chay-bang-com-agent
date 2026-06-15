"""
Threads comment crawler — Playwright public post depth search → bronze JSONL.

Runs OFFLINE (Colab / a worker / locally), NOT inside the AgentBase runtime: it drives a headless
Chromium browser, which is too heavy and easily blocked from datacenter IPs. It reads raw records from
the latest bronze threads file (threads_<ts>.jsonl), navigates to each thread's post_url,
scrolls to load comments, and writes consolidated comments to data/raw/threads_comments_<ts>.jsonl.

Raw record schema (ThreadComment) — kept rich on purpose; the connector normalizes on read:
    comment_hash_id, parent_post_hash_id, parent_post_url, author, content, posted_at, crawled_at, comment_url, images_base64

Input:
    Latest (or specified) bronze threads JSONL file: data/raw/`threads_<YYYYMMDD_HHMM>.jsonl`.

Output:
    Raw comment records saved to data/raw/ as `threads_comments_<YYYYMMDD_HHMM>.jsonl` matching the parent run timestamp.

Configs read from config.py:
    - SCROLL_TIMES: Number of times to scroll down to load search results.

Run:
    # one-off install (not part of the agent image):
    pip install -r requirements-crawler.txt && python -m playwright install chromium
    python crawlers/threads_comment_crawler.py

Run:
    python -m crawlers.threads_comment_crawler

In Colab: import and call crawl_comments(); a running event loop is handled automatically.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import random
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from dateutil import parser
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

import os
import sys
from dotenv import load_dotenv
sys.path.append(str(Path(__file__).resolve().parent.parent))

from config import SCROLL_TIMES
from crawlers import bronze

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class ThreadComment(BaseModel):
    comment_hash_id: str = Field(description="MD5 of content for dedup")
    parent_post_hash_id: str = Field(description="Hash ID of the parent thread post")
    parent_post_url: str = Field(description="URL of the parent thread post")
    author: str = Field(description="Display name of commenter")
    content: str = Field(description="Raw comment text")
    posted_at: str = Field(description="When the user commented (YYYY-MM-DD HH:MM:SS)")
    crawled_at: str = Field(description="When we crawled it")
    comment_url: str = Field(default="", description="Permalink to the comment or commenter profile")
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


async def _crawl_comments_for_thread(
    context, session, post: dict, scroll_times: int
) -> list[dict]:
    """Scrape comments for a single Thread post URL."""
    post_url = post.get("post_url") or post.get("url")
    parent_hash_id = post.get("post_hash_id") or post.get("id")
    parent_content = post.get("content") or ""
    parent_author = post.get("author") or ""

    if not post_url or not post_url.startswith("http"):
        return []

    comments: list[dict] = []
    page = await context.new_page()
    print(f"\n💬 [Comments] Crawling thread: {post_url}...")

    try:
        await page.goto(post_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)

        async def _bypass_login_modal():
            try:
                await page.evaluate("""() => {
                    const loginTexts = ["Continue with Instagram", "Say more with Threads", "Log in or sign up for Threads"];
                    let targetElement = null;
                    for (const text of loginTexts) {
                        const matches = Array.from(document.querySelectorAll('*')).filter(x => x.textContent && x.textContent.includes(text));
                        if (matches.length > 0) {
                            targetElement = matches.pop();
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
            except Exception:
                pass

        # Track keys to count new comments during scrolling
        seen_keys = set()
        
        async def _get_new_comments_count() -> int:
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
                print(f"    {prefix} - found {count} comments, furthest: {furthest}, nearest: {nearest}")
            else:
                print(f"    {prefix} - found {count} comments, no timestamps found")

        await _bypass_login_modal()
        await _get_new_comments_count()
        await _log_articles_stats("First load")

        consecutive_empty_scrolls = 0
        for scroll_idx in range(1, scroll_times + 1):
            await _bypass_login_modal()
            await page.mouse.wheel(0, 2000)
            await page.wait_for_timeout(2000)
            
            new_found = await _get_new_comments_count()
            await _log_articles_stats(f"Scroll {scroll_idx}")
            if new_found == 0:
                consecutive_empty_scrolls += 1
            else:
                consecutive_empty_scrolls = 0
                
            if consecutive_empty_scrolls >= 2:
                print(f"  🛑 [{scroll_idx}] 2 consecutive scrolls with 0 new comments. Stopping scroll for thread...")
                break

        await _bypass_login_modal()
        articles = await page.locator('[role="article"]').all()
        if not articles:
            articles = await page.locator('div[data-pressable-container="true"]').all()

        crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for i, article in enumerate(articles):
            try:
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

                # Skip parent post itself
                is_parent = (i == 0) or (content == parent_content) or (author == parent_author and content[:20] in parent_content)
                if is_parent:
                    continue

                # ── comment URL ──
                comment_url = ""
                try:
                    comment_link = article.locator('a[href*="/post/"]')
                    if await comment_link.count() > 0:
                        href = await comment_link.first.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                comment_url = f"https://www.threads.net{href}"
                            else:
                                comment_url = href
                except Exception:
                    pass
                if not comment_url and author:
                    clean_author = author.strip().lstrip("@")
                    if clean_author:
                        comment_url = f"https://www.threads.net/@{clean_author}"

                # ── time ──
                posted_at_str = "Unknown"
                time_el = article.locator("time")
                if await time_el.count() > 0:
                    dt_str = await time_el.first.get_attribute("datetime")
                    if dt_str:
                        post_time = parser.isoparse(dt_str)
                        posted_at_str = post_time.strftime("%Y-%m-%d %H:%M:%S")

                # ── images ──
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
                        print(f"  📸 encoded {len(images_b64)} image(s) for comment by {author}")

                # ── keep if enough text OR an image ──
                if len(content) > 5 or images_b64:
                    hash_input = content if content else f"{author}_{posted_at_str}"
                    comment = ThreadComment(
                        comment_hash_id=hashlib.md5(hash_input.encode("utf-8")).hexdigest(),
                        parent_post_hash_id=parent_hash_id,
                        parent_post_url=post_url,
                        author=author,
                        content=content,
                        posted_at=posted_at_str,
                        crawled_at=crawled_at,
                        comment_url=comment_url,
                        images_base64=images_b64,
                    )
                    comments.append(comment.model_dump())
            except Exception:
                continue
    except Exception as e:
        print(f"  ❌ error on thread comments '{post_url}': {e}")
    finally:
        await page.close()

    print(f"  ✅ {len(comments)} comment(s) found for this thread")
    return comments


async def _run(threads: list[dict], scroll_times: int) -> list[dict]:
    load_dotenv()
    all_comments: list[dict] = []
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

            for post in threads:
                all_comments.extend(await _crawl_comments_for_thread(context, session, post, scroll_times))
                await asyncio.sleep(random.uniform(3.0, 6.0))  # anti-bot jitter
            await browser.close()

    # global dedup by comment hash
    seen, unique = set(), []
    for comment in all_comments:
        h = comment["comment_hash_id"]
        if h not in seen:
            seen.add(h)
            unique.append(comment)
    return unique


def crawl_comments(
    threads_file_path: str | Path | None = None,
    scroll_times: int = SCROLL_TIMES,
    save_bronze: bool = True,
) -> list[dict]:
    """
    Crawl comments for all threads loaded from a bronze threads file.
    Consolidates the comments and saves them matching the original file's timestamp.
    """
    # 1. Resolve input file
    input_file = Path(threads_file_path) if threads_file_path else bronze.latest_path("threads")
    if not input_file or not input_file.exists():
        print("❌ No Threads bronze file found to fetch comments for.")
        return []

    # 2. Extract timestamp from original filename
    filename = input_file.name
    m = re.search(r'threads_(\d{8}_\d{4})\.jsonl', filename)
    timestamp = m.group(1) if m else None

    print("=" * 56)
    print("🚀 Starting Threads Comments Crawler...")
    print(f"   Input file: {filename}")
    print(f"   Timestamp:  {timestamp or 'N/A'}")
    print(f"   Scroll Times: {scroll_times}")
    print("=" * 56)

    # 3. Load threads
    records = []
    with input_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("⚠️ Threads file is empty.")
        return []

    # Filter threads that have valid urls
    valid_threads = [r for r in records if r.get("post_url") or r.get("url")]
    print(f"📋 Found {len(valid_threads)} thread(s) to scan for comments.")

    # 4. Run loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        comments = loop.run_until_complete(_run(valid_threads, scroll_times))
    else:
        comments = asyncio.run(_run(valid_threads, scroll_times))

    print("\n" + "=" * 56)
    print(f"📊 {len(comments)} unique comment(s) found across {len(valid_threads)} thread(s)")
    if save_bronze and comments:
        # Save matching the parent file timestamp
        path = bronze.save(comments, source="threads_comments", timestamp=timestamp)
        print(f"💾 bronze comments saved: {path}")
    print("=" * 56)
    return comments


if __name__ == "__main__":
    crawl_comments()
