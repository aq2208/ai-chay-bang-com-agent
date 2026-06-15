# Crawlers

This directory contains offline Playwright crawlers used to harvest raw social media data. 

To prevent datacenter IP blocking and avoid heavy browser packages in the main agent image, these scripts run independently from the AgentBase runtime.

## Directory Structure

- [threads_crawler.py](./threads_crawler.py): Crawls Threads posts matching keywords configured in `config.py`.
- [threads_comment_crawler.py](./threads_comment_crawler.py): Crawls replies/comments of scraped Threads posts.
- [save_auth.py](./save_auth.py): Interactive utility to log in and capture Playwright browser authentication state.
- [bronze.py](./bronze.py): Shared utility module to read/write raw files in the `data/raw/` directory.

## Authentication (Bypassing Login Gates)

Threads restricts unauthenticated scraping, displaying login walls or limiting scroll depth. To run the crawler seamlessly on headless environments like GitHub Actions:

1. **Capture the login session locally**:
   ```bash
   python -m crawlers.save_auth
   ```
   *This launches a visible browser window. Log in manually. The script will automatically detect successful authentication, write your session cookies/localStorage to `auth_state.json`, and close.*

2. **Sync to GitHub Secrets**:
   - **Automatically**: If you have the GitHub CLI installed and logged in (`gh auth login`), `save_auth.py` automatically uploads your session JSON directly to your repo as a secret named `THREADS_AUTH_STATE_JSON`.
   - **Manually**: If you don't use the `gh` CLI, copy the full text contents of `auth_state.json` and add it as a secret named `THREADS_AUTH_STATE_JSON` in your GitHub Repository Settings.

## Getting Started

### Installation
Run these commands locally/offline to install requirements and Chromium:
```bash
pip install -r requirements-crawler.txt
python -m playwright install chromium
```

### Execution

1. **Crawl Posts**:
   ```bash
   python -m crawlers.threads_crawler
   ```
   Generates a raw JSONL file: `data/raw/threads_<timestamp>.jsonl`.

2. **Crawl Comments**:
   ```bash
   python -m crawlers.threads_comment_crawler
   ```
   Reads the latest threads JSONL file and creates comments matching the original timestamp: `data/raw/threads_comments_<timestamp>.jsonl`.
