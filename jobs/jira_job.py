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
from processors.issue_extractor import extract_issue, is_valid_issue
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
    def _log(msg: str):
        print(f"[Jira] {msg}")

    def _log_data(title: str, data: any):
        import pprint
        print(f"[Jira] --- {title} ---")
        formatted = pprint.pformat(data, indent=2, width=120)
        for line in formatted.splitlines():
            print(f"[Jira]   {line}")
        print(f"[Jira] ----------------" + "-" * len(title))

    # ── Step 1: Fetch ─────────────────────────────────────────────────────
    _log(f"Step 1/6 — Starting ticket fetching. Mode: {'Mock Data' if dry_run else 'Real Connector'}")
    if dry_run:
        _log("Fetching mock Jira tickets...")
        from mock_data import get_mock_jira
        raw = get_mock_jira()
    else:
        _log("Fetching active Jira tickets from Jira API...")
        from connectors.jira import fetch
        raw = fetch()
        
    _log(f"Step 1/6 — Fetch complete. Total fetched: {len(raw)} tickets.")
    _log_data("Raw Tickets Details", [
        {
            "id": r.get("id"),
            "key": r.get("key"),
            "summary_preview": r.get("summary", "")[:60] + "..." if r.get("summary") else "",
            "description_preview": r.get("description", "")[:60] + "..." if r.get("description") else ""
        }
        for r in raw
    ])

    # ── Step 2: Preprocess ────────────────────────────────────────────────
    _log("Step 2/6 — Preprocessing tickets (cleaning text, filtering length, deduplicating)...")
    items = preprocess(raw)
    _log(f"Step 2/6 — Preprocessing complete. Remaining: {len(items)} items (Filtered out {len(raw) - len(items)}).")
    _log_data("Preprocessed Tickets", [
        {
            "id": item.get("id"),
            "clean_text_preview": item.get("text", "")[:80] + "..."
        }
        for item in items
    ])

    if not items:
        _log("No items remaining after preprocessing — generating empty report.")
        report = generate_report([], job_name="Jira")
        path = save_report(report, "Jira")
        _log(f"Empty report saved to: {path}")
        return {"report_path": str(path), "issues": 0, "mentions": 0}

    # ── Step 3: Extract issues ────────────────────────────────────────────
    _log("Step 3/6 — Extracting technical issue sentences via LLM...")
    for idx, item in enumerate(items):
        _log(f"Processing ticket {idx + 1}/{len(items)} (ID: {item['id']})")
        _log("  Calling LLM to extract clean English technical issue description...")
        item["extracted_issue"] = extract_issue(item["text"])
        _log(f"  => Extracted Issue: '{item['extracted_issue']}'")
        
    _log("Step 3/6 — Technical issue extraction complete.")
    before = len(items)
    items = [item for item in items if is_valid_issue(item.get("extracted_issue", ""))]
    _log(f"Filtered out {before - len(items)} non-issue / off-topic item(s) after extraction.")
    _log_data("Extracted Issues Data State", [
        {
            "id": item.get("id"),
            "extracted_issue": item.get("extracted_issue")
        }
        for item in items
    ])

    # ── Step 4: Classify ──────────────────────────────────────────────────
    _log("Step 4/6 — Classifying issue domain and sub-segment via LLM...")
    for idx, item in enumerate(items):
        _log(f"Classifying ticket {idx + 1}/{len(items)} (ID: {item['id']}): '{item['extracted_issue'][:60]}...'")
        item["domain"]  = classify_domain(item["extracted_issue"])
        item["segment"] = classify_segment(item["extracted_issue"], item["domain"])
        _log(f"  => Result: Domain='{item['domain']}', Segment='{item['segment']}'")
        
    _log("Step 4/6 — Classification complete.")
    _log_data("Classified Items Data State", [
        {
            "id": item.get("id"),
            "issue": item.get("extracted_issue")[:60] + "...",
            "domain": item.get("domain"),
            "segment": item.get("segment")
        }
        for item in items
    ])

    # ── Step 5: Group ─────────────────────────────────────────────────────
    _log("Step 5/6 — Grouping near-duplicate issues using SentenceTransformer embeddings...")
    items = group_similar(items)
    _log(f"Step 5/6 — Grouping complete. Resulted in {len(items)} unique issue groups.")
    _log_data("Grouped Issues Data State", [
        {
            "mentions": g.get("mentions"),
            "sources": g.get("sources"),
            "issue": g.get("extracted_issue"),
            "domain": g.get("domain"),
            "segment": g.get("segment"),
            "merged_ids": g.get("ids")
        }
        for g in items
    ])

    # ── Step 6: Report ────────────────────────────────────────────────────
    _log("Step 6/6 — Rendering final markdown report and performing checks...")
    report = generate_report(items, job_name="Jira")

    _log("Running report guardrail validation checks...")
    guardrail = check_report(report, items)
    if not guardrail["ok"]:
        _log(f"  WARNING — guardrail issues detected: {guardrail['issues']}")
    else:
        _log("  Guardrail checks passed successfully.")

    _log("Saving report markdown file to local disk...")
    path = save_report(report, "Jira")
    _log(f"Step 6/6 — Report successfully saved: {path}")

    # Index issues for the agentic Q&A store (best-effort — never block report delivery).
    _log("Indexing grouped issues into ChromaDB collection for Agentic Q&A...")
    try:
        from knowledge_base.issues_store import index_issues
        n = index_issues(items, job_name="Jira")
        _log(f"Successfully indexed {n} issue(s) into ChromaDB issues store.")
    except Exception as e:
        _log(f"WARNING — issues indexing failed: {e}")

    total_mentions = sum(item.get("mentions", 1) for item in items)
    _log(f"Jira Pipeline Run finished. Issues: {len(items)}, Mentions: {total_mentions}")
    return {"report_path": str(path), "issues": len(items), "mentions": total_mentions}
