"""
Sync To Agent — reads the latest threads bronze JSONL file and pushes it to the agent API.
Then triggers the pipeline execution on the backend.
"""

from __future__ import annotations

import glob
import json
import os
import sys
import requests

def run():
    # 1. Locate latest threads JSONL file
    raw_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
    files = glob.glob(os.path.join(raw_dir, "threads_*.jsonl"))
    
    # Filter out comments file
    files = [f for f in files if "threads_comments_" not in os.path.basename(f)]
    
    if not files:
        print("[sync] Error: No Threads bronze JSONL files found in data/raw/.")
        sys.exit(1)
        
    latest_file = max(files)
    print(f"[sync] Found latest crawl file: {os.path.basename(latest_file)}")
    
    # 2. Parse JSONL file
    records = []
    with open(latest_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
                
    print(f"[sync] Loaded {len(records)} raw posts.")

    # 3. Read endpoint config
    agent_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8080").rstrip("/")
    print(f"[sync] Target Agent Base URL: {agent_url}")

    # 4. Trigger social job pipeline and pass raw posts in body
    trigger_url = f"{agent_url}/run/social/callback?dry_run=false"
    try:
        print(f"[sync] Sending POST {trigger_url} with {len(records)} records...")
        r = requests.post(trigger_url, json=records, timeout=60)
        r.raise_for_status()
        print(f"[sync] Social job pipeline triggered successfully: {r.json()}")
    except Exception as e:
        print(f"[sync] Failed to trigger social job pipeline: {e}")
        sys.exit(1)

    print("[sync] Completed successfully.")


if __name__ == "__main__":
    run()
