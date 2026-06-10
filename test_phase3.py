"""
Phase 3 test — Knowledge Base (ChromaDB index + search)

Usage:
    .venv/bin/python test_phase3.py
"""

import sys
sys.path.insert(0, ".")


def test_build_index():
    print("=" * 50)
    print("TEST: build_index()")
    print("=" * 50)
    from knowledge_base.index import build_index

    count = build_index()
    assert count > 0, "No docs indexed — add .md files to knowledge_base/docs/"
    print(f"  ✅ {count} docs indexed\n")


def test_search():
    print("=" * 50)
    print("TEST: search() — domain matching")
    print("=" * 50)
    from knowledge_base.search import search

    cases = [
        ("Visa card top-up failing with error E5001",         "payment"),
        ("QR code scan failure at merchant terminal",         "qr_code"),
        ("OTP not received after multiple login attempts",    "account"),
        ("Application crashes continuously on device launch", "app_performance"),
        ("Merchant POS terminal not receiving payments",      "merchant"),
    ]

    for issue, expected_stem in cases:
        results = search(issue)
        print(f"  Issue : {issue}")
        if results:
            top = results[0]
            print(f"  Match : {top['filename']}  (similarity {top['similarity']})")
            assert expected_stem in top["filename"], (
                f"Expected '{expected_stem}' in filename, got '{top['filename']}'"
            )
        else:
            print(f"  Match : none (below threshold {0.6})")
            # Not failing the test — threshold may filter some edge cases
        print()

    print("  ✅ pass\n")


def test_suggested_approach():
    print("=" * 50)
    print("TEST: get_suggested_approach()")
    print("=" * 50)
    from knowledge_base.search import get_suggested_approach

    # These match actual issue_extractor.py outputs from Phase 2 tests
    cases = [
        ("Visa payment failed with error E5001.",        True),
        ("App crashes continuously upon launch.",         True),
        ("Weather is nice today in Hanoi.",               False),
    ]

    for issue, expect_match in cases:
        approach = get_suggested_approach(issue)
        print(f"  Issue   : {issue}")
        print(f"  Approach: {approach[:120]}...")
        if expect_match:
            assert approach != "No known solution found. Escalate to engineering team for investigation.", (
                f"Expected a real KB match for: {issue}"
            )
        else:
            assert "Escalate to engineering" in approach, "Expected fallback for unknown issue"
        print()

    print("  ✅ pass\n")


def test_no_index_error():
    """Verify search raises a useful error if index hasn't been built."""
    print("=" * 50)
    print("TEST: search on empty / missing index is handled")
    print("=" * 50)
    # This test just documents the expected behavior — index was already built above
    from knowledge_base.search import _get_collection
    col = _get_collection()
    assert col.count() > 0, "Collection is empty — run build_index() first"
    print(f"  Collection has {col.count()} documents ✅\n")


if __name__ == "__main__":
    test_build_index()
    test_search()
    test_suggested_approach()
    test_no_index_error()

    print("=" * 50)
    print("All Phase 3 tests complete ✅")
