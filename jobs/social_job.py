"""
Social Media Job — end-to-end pipeline for Facebook + Threads posts.

Pipeline stages:
  1. Fetch posts     (real API connectors or mock data)
  2. Preprocess      (clean, filter, dedup)
  3. Sentiment filter(PhoBERT + LLM → keep negatives only)
  4. Image analysis  (Vision LLM → describe screenshots, load samples once)
  5. Extract issues  (LLM → clean English sentence, with image context)
  6. Classify        (LLM → domain + segment)
  7. Group           (embeddings → merge near-duplicates)
  8. Report          (KB RAG + LLM → markdown table + guardrails check)

Usage:
    from jobs.social_job import run
    result = run(dry_run=True)   # uses mock_data
    result = run(dry_run=False)  # uses real Facebook + Threads connectors (Phase 8)
"""

from __future__ import annotations

from processors.preprocessor import preprocess
from processors.sentiment import filter_negative
from processors.image_analyzer import load_sample_images, analyze_image
from processors.issue_extractor import extract_issue
from processors.classifier import classify_domain, classify_segment
from processors.grouper import group_similar
from report.generator import generate_report
from report.guardrails import check_report


def _parse_dt(value) -> "datetime | None":
    """Safely parse a posted_at value (string or datetime) into a datetime object.
    Returns None if unparseable (e.g. 'Unknown').
    """
    from datetime import datetime as _dt
    if value is None:
        return None
    if isinstance(value, _dt):
        return value
    s = str(value).strip()
    if not s or s.lower() == "unknown":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            continue
    return None


def run(dry_run: bool = True, raw_posts: list[dict] | None = None) -> dict:
    """
    Run the Social Media complaint pipeline.

    Args:
        dry_run: True → use mock social data; False → call real FB + Threads connectors
        raw_posts: Optional list of raw posts in memory (from GitHub Action call)

    Returns:
        {"report_path": str, "issues": int, "mentions": int}
    """
    def _log(msg: str):
        print(f"[Social] {msg}")

    def _log_data(title: str, data: any):
        import pprint
        print(f"[Social] --- {title} ---")
        formatted = pprint.pformat(data, indent=2, width=120)
        for line in formatted.splitlines():
            print(f"[Social]   {line}")
        print(f"[Social] ----------------" + "-" * len(title))

    # ── Step 1: Fetch ─────────────────────────────────────────────────────
    _log(f"Step 1/8 — Starting post fetching. Mode: {'Mock Data' if dry_run else ('In-Memory Payload' if raw_posts is not None else 'Real Connectors')}")
    if dry_run:
        _log("Fetching mock social posts...")
        from mock_data import get_mock_social
        raw = get_mock_social()
    elif raw_posts is not None:
        _log(f"Fetching from memory. Normalizing {len(raw_posts)} posts...")
        from connectors.threads import _to_item
        raw = [_to_item(p) for p in raw_posts]
    else:
        # Facebook Graph API is bypassed due to API auth/request errors (400 Bad Request).
        # We only crawl from Threads for the social media dataset.
        _log("Bypassing Facebook Graph API connector. Crawling from Threads only.")
        from connectors.threads import fetch as fetch_th
        raw = []
        try:
            raw.extend(fetch_th())
            _log("Threads fetch completed successfully.")
        except Exception as e:
            _log(f"WARNING — Threads fetch failed: {e}")
            
    _log(f"Step 1/8 — Fetch complete. Total fetched: {len(raw)} posts.")
    _log_data("Raw Posts Details", [
        {
            "id": r.get("id"),
            "platform": r.get("platform", "Threads"),
            "text_preview": r.get("text", "")[:60] + "..." if r.get("text") else "",
            "images_count": len(r.get("images", [])) if r.get("images") else 0
        }
        for r in raw
    ])

    # ── Step 2: Preprocess ────────────────────────────────────────────────
    _log("Step 2/8 — Preprocessing posts (cleaning text, filtering length, deduplicating)...")
    items = preprocess(raw)
    _log(f"Step 2/8 — Preprocessing complete. Remaining: {len(items)} posts (Filtered out {len(raw) - len(items)}).")
    _log_data("Preprocessed Posts", [
        {
            "id": item.get("id"),
            "clean_text_preview": item.get("text", "")[:80] + "..."
        }
        for item in items
    ])

    # ── Step 3: Sentiment filter ──────────────────────────────────────────
    _log("Step 3/8 — Applying PhoBERT sentiment classification & LLM fallback filter...")
    items = filter_negative(items)
    _log(f"Step 3/8 — Sentiment filtering complete. Kept {len(items)} negative posts.")

    if not dry_run:
        from datetime import datetime
        from main import SessionLocal, Post
        db = SessionLocal()
        _log("Saving negative posts to 'posts' table in database...")
        try:
            # Save negative posts to 'posts' table
            for idx, it in enumerate(items):
                post_id = it.get("id")
                exists = db.query(Post).filter(Post.post_hash_id == post_id).first()
                if not exists:
                    _log(f"  [{idx+1}/{len(items)}] Saving new negative post {post_id} to DB...")
                    post = Post(
                        post_hash_id=post_id,
                        platform=it.get("source", "Threads"),
                        matched_keyword=it.get("matched_keyword"),
                        author=it.get("author"),
                        content=it.get("text"),
                        posted_at=_parse_dt(it.get("timestamp")),
                        crawled_at=datetime.utcnow(),
                        post_url=it.get("post_url"),
                        images_base64=it.get("images", [])
                    )
                    db.add(post)
                else:
                    _log(f"  [{idx+1}/{len(items)}] Negative post {post_id} already exists in DB. Skipping duplicate.")
            db.commit()
            _log("Saved negative posts to database successfully.")
        except Exception as e:
            db.rollback()
            _log(f"WARNING — Failed to save negative posts to database: {e}")
        finally:
            db.close()

    if not items:
        _log("No negative posts found — nothing saved to DB.")
        return {"issues": 0, "mentions": 0}

    total_mentions = sum(item.get("mentions", 1) for item in items)
    _log(f"Done. {len(items)} negative post(s) saved to DB. Trigger report generation from UI.")
    return {"issues": len(items), "mentions": total_mentions}


def run_report_only(raw_posts: list[dict]) -> dict:
    """
    Run report-generation pipeline on a pre-fetched list of posts from the DB.
    Skips crawl / preprocess / sentiment steps — starts from step 4 (image analysis).

    Args:
        raw_posts: list of post dicts (already negative-filtered, stored in posts table)

    Returns:
        {"report_path": str, "issues": int, "mentions": int}
    """
    def _log(msg: str):
        print(f"[ReportOnly] {msg}")

    def _log_data(title: str, data: any):
        import pprint
        print(f"[ReportOnly] --- {title} ---")
        formatted = pprint.pformat(data, indent=2, width=120)
        for line in formatted.splitlines():
            print(f"[ReportOnly]   {line}")
        print(f"[ReportOnly] ----------------" + "-" * len(title))

    # Normalise to pipeline item format
    _log("Normalizing posts fetched from database...")
    from connectors.threads import _to_item
    items = [_to_item(p) for p in raw_posts]
    _log(f"Loaded {len(items)} posts for report generation")

    if not items:
        _log("No posts provided — generating empty report.")
        report = generate_report([], job_name="Social Media")
        return {"report_content": report, "issues": 0, "mentions": 0}

    # ── Step 4: Load sample images ────────────────────────────────────────
    _log("Step 4/8 — Loading sample reference screenshot images for vision matching...")
    samples = load_sample_images()
    if samples:
        _log(f"Step 4/8 — Loaded {len(samples)} sample reference image(s).")
        _log_data("Loaded Samples", [
            {
                "label": s.get("label"),
                "domain": s.get("domain")
            }
            for s in samples
        ])
    else:
        _log("Step 4/8 — No sample reference images found in sample_images/<Domain>/ directory.")

    # ── Step 5: Extract issues ────────────────────────────────────────────
    _log("Step 5/8 — Extracting technical issue sentences via LLM...")
    for idx, item in enumerate(items):
        image_desc = ""
        _log(f"Processing post {idx + 1}/{len(items)} (ID: {item['id']})")
        if item.get("images"):
            _log(f"  Post has an associated screenshot: {item['images'][0][:60]}...")
            try:
                _log("  Sending screenshot to Vision LLM for description and reference matching...")
                analysis = analyze_image(item["images"][0], samples)
                image_desc = analysis.get("description", "")
                item["image_analysis"] = analysis
                _log(f"  => Vision Analysis Result: matched_domain={analysis.get('domain')}, "
                     f"confidence={analysis.get('confidence')}, description='{image_desc[:60]}...'")
            except Exception as e:
                _log(f"  WARNING — Vision analysis failed for post {item['id']}: {e}")

        _log("  Calling LLM to extract a clean English technical issue description...")
        item["extracted_issue"] = extract_issue(item["text"], image_description=image_desc)
        _log(f"  => Extracted Issue: '{item['extracted_issue']}'")

    _log("Step 5/8 — Technical issue extraction complete.")
    _log_data("Extracted Issues Data State", [
        {
            "id": item.get("id"),
            "extracted_issue": item.get("extracted_issue"),
            "has_image_analysis": "image_analysis" in item
        }
        for item in items
    ])

    # ── Step 6: Classify ──────────────────────────────────────────────────
    _log("Step 6/8 — Classifying issue domain and sub-segment via LLM...")
    for idx, item in enumerate(items):
        _log(f"Classifying post {idx + 1}/{len(items)} (ID: {item['id']}): '{item['extracted_issue'][:60]}...'")
        item["domain"] = classify_domain(item["extracted_issue"])
        item["segment"] = classify_segment(item["extracted_issue"], item["domain"])
        _log(f"  => Result: Domain='{item['domain']}', Segment='{item['segment']}'")

    _log("Step 6/8 — Classification complete.")
    _log_data("Classified Items Data State", [
        {
            "id": item.get("id"),
            "issue": item.get("extracted_issue")[:60] + "...",
            "domain": item.get("domain"),
            "segment": item.get("segment")
        }
        for item in items
    ])

    # ── Step 7: Group ─────────────────────────────────────────────────────
    _log("Step 7/8 — Grouping near-duplicate issues using SentenceTransformer embeddings...")
    items = group_similar(items)
    _log(f"Step 7/8 — Grouping complete. Resulted in {len(items)} unique issue groups.")
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

    # ── Step 8: Report ────────────────────────────────────────────────────
    _log("Step 8/8 — Rendering final markdown report and performing checks...")
    report = generate_report(items, job_name="Social Media")

    _log("Running report guardrail validation checks...")
    guardrail = check_report(report, items)
    if not guardrail["ok"]:
        _log(f"  WARNING — guardrail issues detected: {guardrail['issues']}")
    else:
        _log("  Guardrail checks passed successfully.")

    _log("Step 8/8 — Report generated.")

    # Index issues for the agentic Q&A store (best-effort — never block report delivery).
    _log("Indexing grouped issues into ChromaDB collection for Agentic Q&A...")
    try:
        from knowledge_base.issues_store import index_issues
        n = index_issues(items, job_name="Social Media")
        _log(f"Successfully indexed {n} issue(s) into ChromaDB issues store.")
    except Exception as e:
        _log(f"WARNING — issues indexing failed: {e}")

    total_mentions = sum(item.get("mentions", 1) for item in items)
    _log(f"ReportOnly Pipeline Run finished. Issues: {len(items)}, Mentions: {total_mentions}")
    return {"report_content": report, "issues": len(items), "mentions": total_mentions}
