# Data Sources

#project

> [!info] Canonical design: **[[Projects/00 - Project Home]]**. Updated 2026-06-11. **Crawling is
> decoupled into an offline Bronze layer:** crawlers write `data/raw/<source>_<ts>.jsonl`; the agent's
> connectors read the latest bronze file and normalize it. **Threads uses a Playwright public-keyword-search
> crawler** (`crawlers/threads_crawler.py`) — *not* the Graph API shown in the Threads section below.

---

## Overview

| Source | Type | Library | Complexity |
|--------|------|---------|-----------|
| Jira | Internal tickets | `jira` Python lib | Low |
| Facebook | Social posts + images | Facebook Graph API | Medium |
| Threads | Social posts + images | Threads API | Medium |
| Mock data | Development/testing | Hardcoded JSON | None |

**Recommendation:** Start with mock data + Jira (easiest). Add Facebook/Threads later.

---

## Mock Data (Start Here)

Use this for development so you don't need real API credentials during the hackathon.

```python
MOCK_DATA = [
    # Jira tickets
    {
        "id": "JIRA-1001",
        "source": "jira",
        "text": "User reports top-up failing repeatedly with Visa card. Error E5001.",
        "images": [],
        "timestamp": "2026-06-10T09:00:00",
    },
    {
        "id": "JIRA-1002",
        "source": "jira",
        "text": "QR code scan not working at merchant Highlands Coffee. Multiple users affected.",
        "images": [],
        "timestamp": "2026-06-10T10:00:00",
    },
    # Facebook posts (negative)
    {
        "id": "FB-2001",
        "source": "facebook",
        "text": "Zalopay bị lỗi rồi! Không nạp tiền được suốt 2 tiếng!!",
        "images": ["https://example.com/screenshot1.jpg"],
        "timestamp": "2026-06-10T08:30:00",
    },
    {
        "id": "FB-2002",
        "source": "facebook",
        "text": "Great app, been using it for years!",  # positive — will be filtered out
        "images": [],
        "timestamp": "2026-06-10T08:45:00",
    },
    # Threads posts
    {
        "id": "TH-3001",
        "source": "threads",
        "text": "Zalopay login OTP không về điện thoại. Đợi 10 phút vẫn không thấy.",
        "images": [],
        "timestamp": "2026-06-10T07:00:00",
    },
]

def fetch_all_mock() -> list[dict]:
    return MOCK_DATA
```

---

## Jira

### Setup
```bash
pip install jira
```

```python
from jira import JIRA

jira = JIRA(
    server="https://your-company.atlassian.net",
    basic_auth=("your-email@company.com", "your-api-token")
    # Get API token: https://id.atlassian.com/manage-profile/security/api-tokens
)
```

### Fetch Recent Tickets
```python
from datetime import datetime, timedelta

def fetch_jira_tickets(days_back: int = 1) -> list[dict]:
    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # JQL = Jira Query Language
    jql = f'project = "YOUR_PROJECT" AND created >= "{since}" ORDER BY created DESC'
    issues = jira.search_issues(jql, maxResults=100)

    items = []
    for issue in issues:
        items.append({
            "id": issue.key,
            "source": "jira",
            "text": f"{issue.fields.summary}\n{issue.fields.description or ''}",
            "images": [],  # can extract from attachments if needed
            "timestamp": issue.fields.created,
            "priority": str(issue.fields.priority),
            "status": str(issue.fields.status),
        })
    return items
```

### JQL Examples
```
# All bugs created today
project = ZLP AND issuetype = Bug AND created >= startOfDay()

# All user-reported issues in the last 24h
project = ZLP AND labels = "user-complaint" AND created >= -1d

# High priority tickets
project = ZLP AND priority in (High, Critical) AND created >= -1d
```

---

## Facebook Graph API

Social media search works by **keyword/hashtag** — you search for posts mentioning your product, not just your own page's posts.

### Setup
1. Create a Meta Developer account at developers.facebook.com
2. Create an app → add "Pages" product
3. Get a Page Access Token (long-lived, 60 days)

```bash
pip install requests
```

### Keyword Search Strategy

Facebook Graph API does not allow open public keyword search (Meta restricts this). The practical approaches:

| Approach | How | Best for |
|----------|-----|---------|
| **Monitor your own Page** | Fetch comments on your page's posts | Official channel complaints |
| **Search hashtags** | `/hashtag/{tag}/recent_media` (Instagram Graph) | Hashtag monitoring |
| **Page mentions** | `/me/tagged` — posts that tag your page | Direct mentions |
| **Inbox / comments** | Page Inbox API — comments on ads and posts | Hidden comments, DMs |

```python
import requests

PAGE_ID = "your_page_id"
ACCESS_TOKEN = "your_page_access_token"
KEYWORDS = ["Zalopay", "zalopay", "ví điện tử lỗi", "nạp tiền lỗi"]

def fetch_facebook_page_comments(days_back: int = 1) -> list[dict]:
    """Fetch comments on your page — most common source of complaints."""
    since = int((datetime.now() - timedelta(days=days_back)).timestamp())

    # Step 1: Get recent posts on your page
    posts_url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/posts"
    posts = requests.get(posts_url, params={
        "access_token": ACCESS_TOKEN,
        "since": since,
        "fields": "id",
        "limit": 50
    }).json().get("data", [])

    items = []
    for post in posts:
        # Step 2: Get comments on each post
        comments_url = f"https://graph.facebook.com/v19.0/{post['id']}/comments"
        comments = requests.get(comments_url, params={
            "access_token": ACCESS_TOKEN,
            "fields": "id,message,created_time,attachments",
            "limit": 100
        }).json().get("data", [])

        for c in comments:
            # Step 3: Keyword filter — only keep relevant complaints
            text = c.get("message", "")
            if not any(kw.lower() in text.lower() for kw in KEYWORDS):
                continue  # skip unrelated comments

            images = []
            for att in c.get("attachments", {}).get("data", []):
                if att.get("media", {}).get("image", {}).get("src"):
                    images.append(att["media"]["image"]["src"])

            items.append({
                "id": c["id"],
                "source": "facebook",
                "text": text,
                "images": images,
                "timestamp": c["created_time"],
            })
    return items

def fetch_facebook_mentions(days_back: int = 1) -> list[dict]:
    """Fetch posts where users tag your page."""
    since = int((datetime.now() - timedelta(days=days_back)).timestamp())
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/tagged"
    data = requests.get(url, params={
        "access_token": ACCESS_TOKEN,
        "since": since,
        "fields": "id,message,created_time,attachments",
        "limit": 100
    }).json()

    items = []
    for post in data.get("data", []):
        text = post.get("message", "")
        images = []
        for att in post.get("attachments", {}).get("data", []):
            if att.get("media", {}).get("image", {}).get("src"):
                images.append(att["media"]["image"]["src"])
        items.append({
            "id": post["id"],
            "source": "facebook",
            "text": text,
            "images": images,
            "timestamp": post["created_time"],
        })
    return items

def fetch_facebook(days_back: int = 1) -> list[dict]:
    return fetch_facebook_page_comments(days_back) + fetch_facebook_mentions(days_back)
```

---

## Threads — Playwright crawler (implemented) ✅

> [!important] This is the **real** Threads approach. The "Threads API" subsection that follows is kept
> for reference only.

`crawlers/threads_crawler.py` drives headless Chromium (Playwright) against
`https://www.threads.net/search?q=<keyword>` for each keyword in `config.KEYWORDS`:
- scrolls the results, extracts `[role="article"]` posts (author + text),
- filters by post age (`DAYS_BACK × 24` hours via the `<time datetime>` attribute),
- downloads attached images async (`aiohttp`) and encodes them **inline as base64 data URIs**,
- dedups by MD5 content hash,
- writes `data/raw/threads_<ts>.jsonl` (rich `SocialPost` schema) via `crawlers/bronze.py`.

`connectors/threads.py` reads the latest bronze file and maps `SocialPost` → the normalized
`{id, source, text, images, timestamp}`. Runs **offline** (Colab/worker), not in the AgentBase runtime.
Crawler deps live in `requirements-crawler.txt` (`playwright`, `aiohttp`, `python-dateutil`, `nest-asyncio`).

Run: `pip install -r requirements-crawler.txt && python -m playwright install chromium && python crawlers/threads_crawler.py`

---

## Threads API (reference only — not used)

> [!note] Superseded by the Playwright crawler above. Kept for reference.

Threads has a **keyword search endpoint** — use it to find posts mentioning your product.

### Setup
1. Create a Meta Developer account (same as Facebook)
2. Add "Threads" product to your app
3. Authenticate with OAuth 2.0

```python
import requests

THREADS_ACCESS_TOKEN = "your_threads_token"
KEYWORDS = ["Zalopay", "zalopay", "lỗi ví"]

def fetch_threads_by_keyword(days_back: int = 1) -> list[dict]:
    """Search Threads posts by keyword."""
    since = int((datetime.now() - timedelta(days=days_back)).timestamp())
    items = []

    for keyword in KEYWORDS:
        url = "https://graph.threads.net/v1.0/threads/search"
        params = {
            "access_token": THREADS_ACCESS_TOKEN,
            "q": keyword,          # keyword search
            "since": since,
            "fields": "id,text,timestamp,media_type,media_url",
            "limit": 100
        }
        data = requests.get(url, params=params).json()

        for post in data.get("data", []):
            images = []
            if post.get("media_type") == "IMAGE" and post.get("media_url"):
                images.append(post["media_url"])

            items.append({
                "id": post["id"],
                "source": "threads",
                "text": post.get("text", ""),
                "images": images,
                "timestamp": post["timestamp"],
                "keyword_matched": keyword,
            })

    # Deduplicate (same post may match multiple keywords)
    seen = set()
    unique = []
    for item in items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
    return unique
```

> **Note:** Threads API keyword search requires your app to be approved for the `threads_keyword_search` permission. For the hackathon demo, use mock data or your own Threads account posts.

---

## Ingestion Coordinator

Runs all sources in parallel and combines results:

```python
from concurrent.futures import ThreadPoolExecutor

def fetch_all(days_back: int = 1) -> list[dict]:
    with ThreadPoolExecutor(max_workers=3) as executor:
        jira_future    = executor.submit(fetch_jira_tickets, days_back)
        facebook_future = executor.submit(fetch_facebook_posts, days_back)
        threads_future  = executor.submit(fetch_threads_posts, days_back)

    all_items = (
        jira_future.result() +
        facebook_future.result() +
        threads_future.result()
    )
    return all_items
```

---

## Related Notes

- [[Projects/Architecture]] — where ingestion fits in the pipeline
- [[Projects/Hackathon]] — project overview
- [[Projects/Image Processing]] — handling images from Facebook/Threads
