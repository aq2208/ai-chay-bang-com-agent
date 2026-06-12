# Crawlers

This directory contains offline Playwright crawlers used to harvest raw social media data. 

To prevent datacenter IP blocking and avoid heavy browser packages in the main agent image, these scripts run independently from the AgentBase runtime.

## Directory Structure

- [threads_crawler.py](file:///Users/lap15864-local/temp/claw-a-thon/ai-chay-bang-com-agent/crawlers/threads_crawler.py): Crawls Threads posts matching keywords configured in `config.py`.
- [threads_comment_crawler.py](file:///Users/lap15864-local/temp/claw-a-thon/ai-chay-bang-com-agent/crawlers/threads_comment_crawler.py): Crawls replies/comments of scraped Threads posts.
- [bronze.py](file:///Users/lap15864-local/temp/claw-a-thon/ai-chay-bang-com-agent/crawlers/bronze.py): Shared utility module to read/write raw files in the `data/raw/` directory.

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
