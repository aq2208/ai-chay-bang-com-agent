"""
Jira Job — end-to-end pipeline for Jira complaint tickets.

Pipeline stages:
  1. Fetch tickets  (real Jira API or mock data)
  2. Preprocess     (clean, filter, dedup)
  3. Extract issues (LLM → clean English sentence)
  4. Classify       (LLM → domain + segment)
  5. Group          (embeddings → merge near-duplicates)
  6. Report         (KB RAG + LLM → markdown table + guardrails check)

Usage:
    from jobs.jira_job import run
    result = run(dry_run=True)   # uses mock_data
    result = run(dry_run=False)  # uses real Jira connector (Phase 8)
"""

from __future__ import annotations

from processors.preprocessor import preprocess
from processors.issue_extractor import extract_issue
from processors.classifier import classify_domain, classify_segment
from processors.grouper import group_similar
from report.generator import generate_report, save_report
from report.guardrails import check_report


def run(dry_run: bool = True) -> dict:
    """
    Run the Jira complaint pipeline.

    Args:
        dry_run: True → use mock Jira data; False → call real Jira connector

    Returns:
        {"report_path": str, "issues": int, "mentions": int}
    """
    _log = lambda msg: print(f"[Jira] {msg}")

    # ── Step 1: Fetch ─────────────────────────────────────────────────────
    _log("Step 1/6 — fetching Jira tickets...")
    if dry_run:
        from mock_data import get_mock_jira
        raw = get_mock_jira()
    else:
        from connectors.jira import fetch
        raw = fetch()
    _log(f"Step 1/6 — {len(raw)} tickets fetched")

    # ── Step 2: Preprocess ────────────────────────────────────────────────
    _log("Step 2/6 — preprocessing...")
    items = preprocess(raw)
    _log(f"Step 2/6 — {len(items)} items after clean/dedup")

    if not items:
        _log("No items after preprocessing — writing empty report.")
        report = generate_report([], job_name="Jira")
        path = save_report(report, "Jira")
        return {"report_path": str(path), "issues": 0, "mentions": 0}

    # ── Step 3: Extract issues ────────────────────────────────────────────
    _log("Step 3/6 — extracting issues (LLM)...")
    for item in items:
        item["extracted_issue"] = extract_issue(item["text"])
        _log(f"  {item['id']}: {item['extracted_issue']}")
    _log("Step 3/6 — done")

    # ── Step 4: Classify ──────────────────────────────────────────────────
    _log("Step 4/6 — classifying domain & segment (LLM)...")
    for item in items:
        item["domain"]  = classify_domain(item["extracted_issue"])
        item["segment"] = classify_segment(item["extracted_issue"], item["domain"])
        _log(f"  {item['id']}: {item['domain']} / {item['segment']}")
    _log("Step 4/6 — done")

    # ── Step 5: Group ─────────────────────────────────────────────────────
    _log("Step 5/6 — grouping similar issues (embeddings)...")
    items = group_similar(items)
    _log(f"Step 5/6 — {len(items)} unique issue group(s)")
    for g in items:
        _log(f"  [{g['mentions']} mention(s)] {g['extracted_issue']}")

    # ── Step 6: Report ────────────────────────────────────────────────────
    _log("Step 6/6 — generating report (KB search + LLM)...")
    report = generate_report(items, job_name="Jira")

    guardrail = check_report(report, items)
    if not guardrail["ok"]:
        _log(f"  WARNING — guardrail issues: {guardrail['issues']}")

    path = save_report(report, "Jira")
    _log(f"Step 6/6 — report saved: {path}")

    total_mentions = sum(item.get("mentions", 1) for item in items)
    return {"report_path": str(path), "issues": len(items), "mentions": total_mentions}
