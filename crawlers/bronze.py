"""
Bronze (raw) data layer — JSONL storage shared by crawlers (write) and connectors (read).

Crawling is decoupled from the agent: a crawler (e.g. the Playwright Threads crawler) runs
offline / in Colab / as a worker and writes raw records here; the agent's connectors read the
latest bronze file and normalize it into pipeline items. This keeps headless-browser deps out of
the AgentBase runtime image and lets processing be re-run without re-crawling.

Files: data/raw/<source>_<YYYYMMDD_HHMM>.jsonl  (one JSON object per line, UTF-8, raw schema).
No Playwright/heavy imports here — safe to import from the agent.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def save(records: list[dict], source: str, raw_dir: Path | None = None, timestamp: str | None = None) -> Path:
    """Write raw records to data/raw/<source>_<timestamp>.jsonl and return the path."""
    out_dir = raw_dir or RAW_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M")
    path = out_dir / f"{source}_{ts}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return path


def latest_path(source: str, raw_dir: Path | None = None) -> Path | None:
    """Return the most recent bronze file for a source (by name; names are timestamp-sorted)."""
    out_dir = raw_dir or RAW_DIR
    files = []
    for f in out_dir.glob(f"{source}_*.jsonl"):
        if source == "threads" and f.name.startswith("threads_comments_"):
            continue
        files.append(f)
    files = sorted(files)
    return files[-1] if files else None


def load_latest(source: str, raw_dir: Path | None = None) -> list[dict]:
    """Load raw records from the most recent bronze file for a source ([] if none)."""
    path = latest_path(source, raw_dir)
    if path is None:
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
