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
                        posted_at=it.get("timestamp"),
                        crawled_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
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
        _log("No negative posts found — writing empty report.")
        report = generate_report([], job_name="Social Media")
        path = save_report(report, "Social Media")
        return {"report_path": str(path), "issues": 0, "mentions": 0}

    # ── Step 4: Load sample images (once per job run) ─────────────────────
    _log("Step 4/8 — loading reference sample images...")
    samples = load_sample_images()
    if samples:
        _log(f"Step 4/8 — {len(samples)} sample image(s) loaded")
    else:
        _log("Step 4/8 — no sample images found (add to sample_images/<Domain>/)")

    # ── Step 5: Extract issues (with image analysis for image posts) ───────
    _log("Step 5/8 — extracting issues (LLM)...")
    for item in items:
        image_desc = ""
        if item.get("images"):
            try:
                analysis = analyze_image(item["images"][0], samples)
                image_desc = analysis.get("description", "")
                item["image_analysis"] = analysis
                _log(f"  {item['id']}: image → {image_desc[:60]}")
            except Exception as e:
                _log(f"  {item['id']}: image analysis failed — {e}")

        item["extracted_issue"] = extract_issue(item["text"], image_description=image_desc)
        _log(f"  {item['id']}: {item['extracted_issue']}")
    _log("Step 5/8 — done")

    # ── Step 6: Classify ──────────────────────────────────────────────────
    _log("Step 6/8 — classifying domain & segment (LLM)...")
    for item in items:
        item["domain"]  = classify_domain(item["extracted_issue"])
        item["segment"] = classify_segment(item["extracted_issue"], item["domain"])
        _log(f"  {item['id']}: {item['domain']} / {item['segment']}")
    _log("Step 6/8 — done")

    # ── Step 7: Group ─────────────────────────────────────────────────────
    _log("Step 7/8 — grouping similar issues (embeddings)...")
    items = group_similar(items)
    _log(f"Step 7/8 — {len(items)} unique issue group(s)")
    for g in items:
        _log(f"  [{g['mentions']} mention(s)] {g['extracted_issue']}")

    # ── Step 8: Report ────────────────────────────────────────────────────
    _log("Step 8/8 — generating report (KB search + LLM)...")
    report = generate_report(items, job_name="Social Media")

    guardrail = check_report(report, items)
    if not guardrail["ok"]:
        _log(f"  WARNING — guardrail issues: {guardrail['issues']}")

    path = save_report(report, "Social Media")
    _log(f"Step 8/8 — report saved: {path}")

    # Index issues for the agentic Q&A store (best-effort — never block report delivery).
    try:
        from knowledge_base.issues_store import index_issues
        n = index_issues(items, job_name="Social Media")
        _log(f"Indexed {n} issue(s) into the Q&A store")
    except Exception as e:
        _log(f"WARNING — issue indexing failed: {e}")

    total_mentions = sum(item.get("mentions", 1) for item in items)
    return {"report_path": str(path), "issues": len(items), "mentions": total_mentions}
