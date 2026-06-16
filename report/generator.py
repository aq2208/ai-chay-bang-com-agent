"""
Phase 5 — Report generation.
Takes fully-enriched pipeline items and produces a markdown table report
for Product Owners.

Input items must have (set by earlier pipeline stages):
    extracted_issue  (str)  — clean English sentence
    domain           (str)  — Payment / QR Code / Account / App Performance / Merchant / Other
    segment          (str)  — sub-category
    mentions         (int)  — how many posts were merged (default 1)
    sources          (str)  — comma-separated source names
    ids              (list) — original item IDs

This module also calls KB search internally to add "suggested_approach"
before rendering, so callers don't need to.
"""

from __future__ import annotations

import base64
from datetime import date
import hashlib
from pathlib import Path

from knowledge_base.search import get_suggested_approach
from llm_client import llm

_SUMMARY_SYSTEM = (
    "You are a Product Owner report writer for Zalopay. "
    "Write a 2–3 sentence executive summary of the complaint trends shown. "
    "Be factual, concise, and actionable. Plain text only — no markdown."
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _get_image_hash(base64_str: str) -> str:
    return hashlib.md5(base64_str[:1000].encode("utf-8")).hexdigest()[:12]


def _save_base64_image(base64_str: str, filename: str) -> str | None:
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]
        data = base64.b64decode(base64_str)
        
        images_dir = OUTPUT_DIR / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = images_dir / filename
        filepath.write_bytes(data)
        return f"/output/images/{filename}"
    except Exception as e:
        print(f"[generator] Error saving base64 image: {e}")
        return None


def generate_report(items: list[dict], job_name: str = "Social Media") -> str:
    """
    Build a markdown complaint report from enriched pipeline items.

    Returns:
        Multi-line markdown string with header, executive summary, and issue table.
    """
    if not items:
        return _empty_report(job_name)

    rows = _build_rows(items)
    today = date.today().isoformat()
    total_mentions = sum(r["mentions"] for r in rows)

    summary = _executive_summary(rows, today, job_name)

    lines = [
        f"# Zalopay Complaint Report — {job_name}",
        f"**Date**: {today} | **Total Issues**: {len(rows)} | **Total Mentions**: {total_mentions}",
        "",
        "## Executive Summary",
        summary,
        "",
        "## Issue Table",
        "",
        "| Domain | Segment | Issue | Mentions | Sources | Reference Links | Screenshots | Suggested Approach |",
        "|--------|---------|-------|----------|---------|-----------------|-------------|-------------------|",
    ]

    for r in rows:
        approach = r["suggested_approach"].replace("\n", " ").replace("|", "/")
        if len(approach) > 120:
            approach = approach[:117] + "..."
            
        # Format Links
        urls = r.get("post_urls", [])
        ids = r.get("ids", [])
        links_parts = []
        if urls:
            for idx, url in enumerate(urls):
                links_parts.append(f"[Link {idx+1}]({url})")
            links_str = "<br>".join(links_parts)
        elif ids:
            import config
            for item_id in ids:
                if r["sources"].lower() == "jira" and config.JIRA_URL:
                    jira_base = config.JIRA_URL.rstrip('/')
                    links_parts.append(f"[{item_id}]({jira_base}/browse/{item_id})")
                else:
                    links_parts.append(item_id)
            links_str = "<br>".join(links_parts)
        else:
            links_str = "—"
            
        # Format Screenshots
        images = r.get("images") or []
        img_parts = []
        for idx, img_data in enumerate(images):
            if not img_data:
                continue
            img_hash = _get_image_hash(img_data)
            ext = "png"
            if "data:image/" in img_data:
                prefix = img_data.split(";")[0]
                detected_ext = prefix.split("/")[-1]
                if detected_ext in ("png", "jpeg", "jpg", "webp", "gif"):
                    ext = detected_ext
            filename = f"{img_hash}.{ext}"
            
            saved_path = _save_base64_image(img_data, filename)
            if saved_path:
                img_parts.append(
                    f'<a href="{saved_path}" target="_blank">'
                    f'<img src="{saved_path}" width="40" style="border-radius:4px; border:1px solid #334155; display:inline-block; margin:2px;" />'
                    f'</a>'
                )
        if img_parts:
            screenshots_str = " ".join(img_parts)
        else:
            screenshots_str = "—"

        lines.append(
            f"| {r['domain']} | {r['segment']} | {r['issue']} "
            f"| {r['mentions']} | {r['sources']} | {links_str} | {screenshots_str} | {approach} |"
        )

    lines += ["", "---", "*Generated by Zalopay Analytics Agent*"]
    return "\n".join(lines)


def save_report(report: str, job_name: str) -> Path:
    """Write report to output/<timestamp>_<job>.md and return the path."""
    from datetime import datetime

    OUTPUT_DIR.mkdir(exist_ok=True)
    slug = job_name.lower().replace(" ", "_")
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.md"
    path = OUTPUT_DIR / filename
    path.write_text(report, encoding="utf-8")
    return path


# ── Internal helpers ───────────────────────────────────────────────────────


def _build_rows(items: list[dict]) -> list[dict]:
    rows = []
    for item in items:
        approach = get_suggested_approach(item["extracted_issue"])
        
        post_urls = item.get("post_urls", [])
        if not post_urls and item.get("post_url"):
            post_urls = [item["post_url"]]
            
        images = item.get("all_images", [])
        if not images and item.get("images"):
            images = item["images"]
        if isinstance(images, str):
            images = [images]
            
        rows.append({
            "domain":             item.get("domain", "Other"),
            "segment":            item.get("segment", "General"),
            "issue":              item["extracted_issue"],
            "mentions":           item.get("mentions", 1),
            "sources":            item.get("sources", item.get("source", "unknown")),
            "suggested_approach": approach,
            "post_urls":          post_urls,
            "images":             images,
            "ids":                item.get("ids", [item.get("id")])
        })
    rows.sort(key=lambda r: r["mentions"], reverse=True)
    return rows


def _executive_summary(rows: list[dict], today: str, job_name: str) -> str:
    top = rows[:10]
    issue_list = "\n".join(
        f"- {r['domain']}/{r['segment']}: {r['issue']} ({r['mentions']} mention(s))"
        for r in top
    )
    return llm.chat(
        system=_SUMMARY_SYSTEM,
        user=f"Report: {job_name}, {today}\n\n{issue_list}",
        max_tokens=150,
        fast=False,
    )


def _empty_report(job_name: str) -> str:
    today = date.today().isoformat()
    return (
        f"# Zalopay Complaint Report — {job_name}\n"
        f"**Date**: {today} | **Total Issues**: 0 | **Total Mentions**: 0\n\n"
        "No issues found for this reporting period.\n"
        "\n---\n*Generated by Zalopay Analytics Agent*"
    )
