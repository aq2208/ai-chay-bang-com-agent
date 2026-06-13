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
    if not records:
        print("[sync] Warning: Crawl file is empty. Skipping upload.")
        return
        
    # 3. Read endpoint config
    agent_url = os.getenv("AGENT_ENDPOINT_URL", "http://localhost:8080").rstrip("/")
    print(f"[sync] Target Agent Base URL: {agent_url}")
    
    # 4. Ingest raw posts
    ingest_url = f"{agent_url}/api/ingest/social"
    try:
        print(f"[sync] Sending POST {ingest_url}...")
        r = requests.post(ingest_url, json=records, timeout=60)
        r.raise_for_status()
        print(f"[sync] Ingest response: {r.json()}")
    except Exception as e:
        print(f"[sync] Ingestion failed: {e}")
        sys.exit(1)
        
    # 5. Trigger social job pipeline
    trigger_url = f"{agent_url}/run/social?dry_run=false&triggered_by=github_workflow"
    try:
        print(f"[sync] Sending POST {trigger_url}...")
        r = requests.post(trigger_url, timeout=30)
        r.raise_for_status()
        print(f"[sync] Social job pipeline triggered successfully: {r.json()}")
    except Exception as e:
        print(f"[sync] Failed to trigger social job pipeline: {e}")
        sys.exit(1)
        
    print("[sync] Completed successfully.")

if __name__ == "__main__":
    run()
