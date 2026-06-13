"""
Phase 4 tests — Image Analyzer & Semantic Grouper

Usage:
    .venv/bin/python test_phase4.py

Notes:
  - Grouper test: no API key needed (embeddings only)
  - Image analyzer test: requires LLM_API_KEY and a public image URL
    Set SKIP_IMAGE_TEST=1 to skip it if no key is available.
"""

import os
import sys
sys.path.insert(0, ".")


# ── Grouper ────────────────────────────────────────────────────────────────

def test_grouper_merges_duplicates():
    print("=" * 50)
    print("TEST: grouper — merges near-duplicate issues")
    print("=" * 50)
    from processors.grouper import group_similar

    items = [
        # 3 Visa phrases — all score ≥ 0.82 against each other
        {"id": "FB-001", "source": "facebook", "extracted_issue": "Visa card top-up failing with error E5001"},
        {"id": "TH-002", "source": "threads",  "extracted_issue": "Visa top-up error code E5001 repeatedly"},
        {"id": "FB-003", "source": "facebook", "extracted_issue": "Cannot top up using Visa card, E5001 shown"},
        # 2 QR phrases — both score ≥ 0.82 against each other
        {"id": "FB-004", "source": "facebook", "extracted_issue": "QR code scan fails at merchant terminal"},
        {"id": "TH-005", "source": "threads",  "extracted_issue": "QR code payment scan failing at merchant terminal"},
    ]

    groups = group_similar(items)

    print(f"  Input  : {len(items)} items")
    print(f"  Output : {len(groups)} groups")
    for g in groups:
        print(f"    [{g['mentions']} mention(s)] {g['extracted_issue'][:55]}")
        print(f"           sources={g['sources']}  ids={g['ids']}")
    print()

    # The 3 Visa items should merge into one group
    visa_group = next((g for g in groups if "Visa" in g["extracted_issue"] or "visa" in g["extracted_issue"].lower()), None)
    assert visa_group is not None, "Visa group not found"
    assert visa_group["mentions"] == 3, f"Expected 3 Visa mentions, got {visa_group['mentions']}"
    assert "facebook" in visa_group["sources"]
    assert "threads" in visa_group["sources"]

    # The 2 QR items should merge into one group
    qr_group = next((g for g in groups if "QR" in g["extracted_issue"] or "qr" in g["extracted_issue"].lower()), None)
    assert qr_group is not None, "QR group not found"
    assert qr_group["mentions"] == 2, f"Expected 2 QR mentions, got {qr_group['mentions']}"

    # Sorted by mentions — Visa (3) should come before QR (2)
    assert groups[0]["mentions"] >= groups[1]["mentions"], "Not sorted by mentions"

    print("  ✅ pass\n")


def test_grouper_no_merge_for_different_issues():
    print("=" * 50)
    print("TEST: grouper — does NOT merge unrelated issues")
    print("=" * 50)
    from processors.grouper import group_similar

    items = [
        {"id": "A", "source": "facebook", "extracted_issue": "Visa card top-up failing with error E5001"},
        {"id": "B", "source": "threads",  "extracted_issue": "OTP not received after login attempt"},
        {"id": "C", "source": "jira",     "extracted_issue": "App crashes on launch on Samsung device"},
    ]

    groups = group_similar(items)

    print(f"  Input  : {len(items)} items")
    print(f"  Output : {len(groups)} groups (expected 3 — all different)")
    for g in groups:
        print(f"    {g['extracted_issue'][:55]}")
    print()

    assert len(groups) == 3, f"Expected 3 separate groups, got {len(groups)}"
    for g in groups:
        assert g["mentions"] == 1

    print("  ✅ pass\n")


def test_grouper_empty_input():
    print("=" * 50)
    print("TEST: grouper — handles empty input")
    print("=" * 50)
    from processors.grouper import group_similar

    result = group_similar([])
    assert result == [], f"Expected [], got {result}"
    print("  ✅ pass\n")


# ── Image Analyzer ─────────────────────────────────────────────────────────

def test_image_analyzer_load_samples():
    print("=" * 50)
    print("TEST: image_analyzer — load_sample_images()")
    print("=" * 50)
    from processors.image_analyzer import load_sample_images

    samples = load_sample_images()
    print(f"  Found {len(samples)} sample image(s) in sample_images/")
    if samples:
        for s in samples:
            print(f"    {s['domain']}/{s['label']}  ({s['media_type']})")
    else:
        print("  (empty — team hasn't added sample images yet)")
        print("  Add .png/.jpg files to sample_images/<Domain>/ to enable comparison")
    print("  ✅ pass (empty samples is valid)\n")


def test_image_analyzer_parse_json():
    print("=" * 50)
    print("TEST: image_analyzer — JSON parsing fallback")
    print("=" * 50)
    from processors.image_analyzer import _parse_json

    # Valid JSON
    result = _parse_json('{"description": "App crash shown", "matched_sample": null, "domain": "App Performance", "confidence": "high"}')
    assert result["description"] == "App crash shown"
    assert result["domain"] == "App Performance"
    print("  Valid JSON   ✅")

    # JSON buried in extra text (common LLM behavior)
    result = _parse_json('Here is the analysis:\n{"description": "OTP error", "matched_sample": null, "domain": "Account", "confidence": "medium"}\nEnd.')
    assert result["description"] == "OTP error"
    print("  Embedded JSON ✅")

    # Completely invalid → fallback
    result = _parse_json("I cannot analyze this image.")
    assert result["domain"] == "Other"
    assert result["confidence"] == "low"
    print("  Fallback dict ✅")

    print("  ✅ pass\n")


def test_image_analyzer_live():
    """Live test — requires LLM_API_KEY. Skipped if key is not set."""
    print("=" * 50)
    print("TEST: image_analyzer — live API call (with public image URL)")
    print("=" * 50)

    import config
    if not config.LLM_API_KEY:
        print("  ⏭  Skipped — LLM_API_KEY not set\n")
        return

    from processors.image_analyzer import analyze_image

    # Base64 red 1x1 PNG data URI to avoid remote download issues
    test_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    try:
        result = analyze_image(test_url, samples=[])
    except Exception as e:
        err = str(e)
        if any(k in err for k in ("ConnectTimeout", "timeout", "ConnectionError", "RESOURCE_EXHAUSTED", "quota")):
            print(f"  ⏭  Skipped — network/quota error: {type(e).__name__}\n")
            return
        raise

    print(f"  description    : {result['description']}")
    print(f"  matched_sample : {result['matched_sample']}")
    print(f"  domain         : {result['domain']}")
    print(f"  confidence     : {result['confidence']}")

    assert isinstance(result["description"], str) and len(result["description"]) > 5
    assert result["domain"] in ("Payment", "QR Code", "Account", "App Performance", "Merchant", "Other")
    assert result["confidence"] in ("high", "medium", "low")
    print("  ✅ pass\n")


if __name__ == "__main__":
    # Grouper — no API key needed
    test_grouper_merges_duplicates()
    test_grouper_no_merge_for_different_issues()
    test_grouper_empty_input()

    # Image analyzer — partial tests don't need API key
    test_image_analyzer_load_samples()
    test_image_analyzer_parse_json()
    test_image_analyzer_live()

    print("=" * 50)
    print("All Phase 4 tests complete ✅")
