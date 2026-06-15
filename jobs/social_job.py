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
from report.generator import generate_report, save_report
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
    _log = lambda msg: print(f"[Social] {msg}")

    # ── Step 1: Fetch ─────────────────────────────────────────────────────
    _log("Step 1/8 — fetching social posts...")
    if dry_run:
        from mock_data import get_mock_social
        raw = get_mock_social()
    elif raw_posts is not None:
        _log(f"Step 1/8 — using {len(raw_posts)} posts passed in memory")
        # Normalize the incoming posts (map raw post fields to pipeline items format)
        from connectors.threads import _to_item
        raw = [_to_item(p) for p in raw_posts]
    else:
        # Facebook Graph API is bypassed due to API auth/request errors (400 Bad Request).
        # We only crawl from Threads for the social media dataset.
        from connectors.threads import fetch as fetch_th
        raw = []
        try:
            raw.extend(fetch_fb())
        except Exception as e:
            _log(f"WARNING — Facebook fetch failed: {e}")
        try:
            raw.extend(fetch_th())
        except Exception as e:
            _log(f"WARNING — Threads fetch failed: {e}")
    _log(f"Step 1/8 — {len(raw)} posts fetched")

    # ── Step 2: Preprocess ────────────────────────────────────────────────
    _log("Step 2/8 — preprocessing...")
    items = preprocess(raw)
    _log(f"Step 2/8 — {len(items)} posts after clean/dedup")

    # ── Step 3: Sentiment filter ──────────────────────────────────────────
    _log("Step 3/8 — filtering negative posts (PhoBERT)...")
    items = filter_negative(items)
    _log(f"Step 3/8 — {len(items)} negative posts kept")

    if not dry_run:
        from datetime import datetime
        from main import SessionLocal, Post
        db = SessionLocal()
        try:
            # Save negative posts to 'posts' table
            for it in items:
                post_id = it.get("id")
                exists = db.query(Post).filter(Post.post_hash_id == post_id).first()
                if not exists:
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
            db.commit()
            _log("Saved negative posts to database.")
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
    _log = lambda msg: print(f"[ReportOnly] {msg}")

    # Normalise to pipeline item format
    from connectors.threads import _to_item
    items = [_to_item(p) for p in raw_posts]
    _log(f"{len(items)} posts loaded for report generation")

    if not items:
        _log("No posts provided — writing empty report.")
        report = generate_report([], job_name="Social Media")
        path = save_report(report, "Social Media")
        return {"report_path": str(path), "issues": 0, "mentions": 0}

    # ── Step 4: Load sample images ────────────────────────────────────────
    _log("Step 4 — loading reference sample images...")
    samples = load_sample_images()

    # ── Step 5: Extract issues ────────────────────────────────────────────
    _log("Step 5 — extracting issues (LLM)...")
    for item in items:
        image_desc = ""
        if item.get("images"):
            try:
                analysis = analyze_image(item["images"][0], samples)
                image_desc = analysis.get("description", "")
                item["image_analysis"] = analysis
            except Exception as e:
                _log(f"  {item['id']}: image analysis failed — {e}")
        item["extracted_issue"] = extract_issue(item["text"], image_description=image_desc)
        _log(f"  {item['id']}: {item['extracted_issue']}")

    # ── Step 6: Classify ──────────────────────────────────────────────────
    _log("Step 6 — classifying domain & segment (LLM)...")
    for item in items:
        item["domain"] = classify_domain(item["extracted_issue"])
        item["segment"] = classify_segment(item["extracted_issue"], item["domain"])

    # ── Step 7: Group ─────────────────────────────────────────────────────
    _log("Step 7 — grouping similar issues...")
    items = group_similar(items)
    _log(f"Step 7 — {len(items)} unique issue group(s)")

    # ── Step 8: Report ────────────────────────────────────────────────────
    _log("Step 8 — generating report (KB search + LLM)...")
    report = generate_report(items, job_name="Social Media")

    guardrail = check_report(report, items)
    if not guardrail["ok"]:
        _log(f"  WARNING — guardrail issues: {guardrail['issues']}")

    path = save_report(report, "Social Media")
    _log(f"Step 8 — report saved: {path}")

    try:
        from knowledge_base.issues_store import index_issues
        n = index_issues(items, job_name="Social Media")
        _log(f"Indexed {n} issue(s) into the Q&A store")
    except Exception as e:
        _log(f"WARNING — issue indexing failed: {e}")

    total_mentions = sum(item.get("mentions", 1) for item in items)
    return {"report_path": str(path), "issues": len(items), "mentions": total_mentions}
