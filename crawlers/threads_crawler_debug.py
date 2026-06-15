"""
Threads crawler (DEBUG) — Playwright public keyword search → bronze JSONL.
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

from crawlers import bronze

# Hardcoded configurations for debugging
KEYWORDS = ["zalopay"]
SCROLL_TIMES = 20

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


def printCustom(action_name: str, new_posts: list[dict]):
    print(f"\n--- {action_name} ---")
    print(f"found {len(new_posts)} post(s):")
    for i, post in enumerate(new_posts, 1):
        print(f"[{i}] {post['time']} {post['url']}")


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

        # Track already printed keys to show only newly found posts at each action
        printed_keys = set()

        # Helper to extract posts currently in DOM
        async def _extract_current_posts(articles_list) -> list[dict]:
            extracted = []
            for art in articles_list:
                try:
                    # ── author ──
                    art_author = ""
                    try:
                        lines = [ln.strip() for ln in (await art.inner_text()).split("\n") if ln.strip()]
                        if len(lines) >= 2:
                            art_author = lines[0]
                            if art_author.lower() in ("follow", "theo dõi") and len(lines) > 2:
                                art_author = lines[1]
                    except Exception:
                        pass

                    # ── URL ──
                    art_url = ""
                    try:
                        post_link = art.locator('a[href*="/post/"]')
                        if await post_link.count() > 0:
                            href = await post_link.first.get_attribute("href")
                            if href:
                                if href.startswith("/"):
                                    art_url = f"https://www.threads.net{href}"
                                else:
                                    art_url = href
                    except Exception:
                        pass

                    if not art_url and art_author:
                        clean_author = art_author.strip().lstrip("@")
                        if clean_author:
                            art_url = f"https://www.threads.net/@{clean_author}"
                    if not art_url:
                        art_url = "N/A"

                    # ── Time ──
                    time_formatted = "Unknown"
                    time_el = art.locator("time")
                    if await time_el.count() > 0:
                        dt_str = await time_el.first.get_attribute("datetime")
                        if dt_str:
                            try:
                                post_time = parser.isoparse(dt_str)
                                time_formatted = post_time.strftime("%d/%m/%Y %Hh%M")
                            except Exception:
                                pass

                    # ── Content for dedup key ──
                    content_str = ""
                    try:
                        content_str = await art.inner_text()
                    except Exception:
                        pass

                    key = art_url if art_url != "N/A" else f"{art_author}_{time_formatted}_{content_str[:50]}"
                    extracted.append({
                        "url": art_url,
                        "time": time_formatted,
                        "key": key
                    })
                except Exception:
                    continue
            return extracted

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

        # First search: get current articles
        await _bypass_login_modal()
        articles = await page.locator('[role="article"]').all()
        if not articles:
            articles = await page.locator('div[data-pressable-container="true"]').all()

        current_posts = await _extract_current_posts(articles)
        new_posts = []
        for p in current_posts:
            if p["key"] not in printed_keys:
                printed_keys.add(p["key"])
                new_posts.append(p)
        printCustom("First Search", new_posts)
        await page.screenshot(path="threads_first_search.png")

        consecutive_empty_scrolls = 0

        # Scrolls
        for scroll_idx in range(1, scroll_times + 1):
            await _bypass_login_modal()
            await page.mouse.wheel(0, 3000)
            await page.wait_for_timeout(2500)

            articles = await page.locator('[role="article"]').all()
            if not articles:
                articles = await page.locator('div[data-pressable-container="true"]').all()

            current_posts = await _extract_current_posts(articles)
            new_posts = []
            for p in current_posts:
                if p["key"] not in printed_keys:
                    printed_keys.add(p["key"])
                    new_posts.append(p)
            printCustom(f"Scroll {scroll_idx}", new_posts)
            if scroll_idx in (1, 5, 20):
                await page.screenshot(path=f"threads_scroll_{scroll_idx}.png")

            if len(new_posts) == 0:
                consecutive_empty_scrolls += 1
            else:
                consecutive_empty_scrolls = 0

            if consecutive_empty_scrolls >= 2:
                print(f"  🛑 [{scroll_idx}] 2 consecutive scrolls with 0 new posts. Stopping scroll for keyword '{keyword}'...")
                break

        # After scrolling, perform the full extraction logic
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


async def _run(keywords: list[str], scroll_times: int, max_age_hours: int, token: str | None = None) -> list[dict]:
    all_records: list[dict] = []
    async with aiohttp.ClientSession() as session:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # 1. Load data/auth_state.json if exists
            auth_path = os.path.join("data", "auth_state.json")
            env_auth_state = os.getenv("THREADS_AUTH_STATE_JSON")
            if env_auth_state and not os.path.exists(auth_path):
                try:
                    auth_dir = os.path.dirname(auth_path)
                    if auth_dir:
                        os.makedirs(auth_dir, exist_ok=True)
                    with open(auth_path, "w", encoding="utf-8") as f:
                        f.write(env_auth_state)
                    print(f"🔑 [Auth] Generated {auth_path} from THREADS_AUTH_STATE_JSON environment variable.")
                except Exception as e:
                    print(f"⚠️ [Auth] Failed to write THREADS_AUTH_STATE_JSON to file: {e}")

            if os.path.exists(auth_path):
                context = await browser.new_context(user_agent=_USER_AGENT, storage_state=auth_path)
                print(f"🔑 [Auth] Loaded session from storage state: {auth_path}")
            else:
                context = await browser.new_context(user_agent=_USER_AGENT)
                if token:
                    # Parse as full cookies header or simple sessionid
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
                    print(f"🔓 [Auth] No auth state file or token found. Proceeding as guest (anonymous search)...")

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
    Crawl Threads for the given keywords (default: KEYWORDS), dedup, and (optionally)
    save a bronze JSONL. Returns the raw SocialPost records.
    """
    keywords = keywords or KEYWORDS
    scroll_times = scroll_times if scroll_times is not None else SCROLL_TIMES
    # Accepts all post from history by using a massive max_age_hours (99999999 hours)
    max_age_hours = max_age_hours if max_age_hours is not None else 99999999

    print("=" * 56)
    print("🚀 Starting Threads Crawler (DEBUG)...")
    print(f"   Keywords:     {keywords}")
    print(f"   Scroll Times: {scroll_times}")
    print(f"   Max Age:      {max_age_hours} hours")
    print("=" * 56)

    # Load token from environment or dotenv
    load_dotenv()
    token = os.getenv("THREADS_SESSION_ID") or os.getenv("THREADS_TOKEN")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        records = loop.run_until_complete(_run(keywords, scroll_times, max_age_hours, token))
    else:
        records = asyncio.run(_run(keywords, scroll_times, max_age_hours, token))

    print("\n" + "=" * 56)
    print(f"📊 {len(records)} unique post(s) across {len(keywords)} keyword(s)")
    with_images = sum(1 for r in records if r.get("images_base64"))
    print(f"   with images: {with_images}")
    if save_bronze:
        path = bronze.save(records, source="threads")
        print(f"💾 bronze saved: {path}")
    print("=" * 56)

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
