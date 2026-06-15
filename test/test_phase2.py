"""
Phase 2 test — run after setting ANTHROPIC_API_KEY in .env

Usage:
    .venv/bin/python test_phase2.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



def test_preprocessor():
    print("=" * 50)
    print("TEST: preprocessor.py")
    print("=" * 50)
    from processors.preprocessor import clean_text, is_meaningful, preprocess
    from mock_data import get_mock_jira, get_mock_social

    # clean_text
    noisy = "Zalopay bị lỗi rồi!!!! 😡😡 http://fb.com Không nạp tiền được!!"
    clean = clean_text(noisy)
    print(f"clean_text:")
    print(f"  IN : {noisy}")
    print(f"  OUT: {clean}")
    assert "http" not in clean, "URL not removed"
    assert len(clean) < len(noisy), "Should be shorter after cleaning"
    print("  ✅ pass")

    # is_meaningful
    assert not is_meaningful("Lỗi"), "Too short — should fail"
    assert is_meaningful("Không nạp tiền được bằng Visa"), "Long enough — should pass"
    print("is_meaningful ✅")

    # preprocess on mock data
    raw_jira   = get_mock_jira()
    raw_social = get_mock_social()
    jira_clean   = preprocess(raw_jira)
    social_clean = preprocess(raw_social)
    print(f"preprocess: Jira {len(raw_jira)}→{len(jira_clean)}, Social {len(raw_social)}→{len(social_clean)}")
    assert len(jira_clean) == len(raw_jira), "All Jira tickets should survive (all meaningful)"
    print("  ✅ pass\n")


def test_issue_extractor():
    print("=" * 50)
    print("TEST: issue_extractor.py")
    print("=" * 50)
    from processors.issue_extractor import extract_issue

    cases = [
        ("Không nạp tiền được bằng Visa suốt 2 tiếng, lỗi E5001", ""),
        ("Quét QR không được tại Circle K", ""),
        ("Zalopay không gửi OTP về điện thoại", ""),
        ("App crash liên tục khi mở lên", "Screenshot shows app crash on launch screen"),
    ]

    for text, img_desc in cases:
        issue = extract_issue(text, img_desc)
        print(f"  IN : {text[:60]}")
        print(f"  OUT: {issue}")
        assert len(issue.split()) >= 5, "Issue too short"
        print()
    print("  ✅ pass\n")


def test_classifier():
    print("=" * 50)
    print("TEST: classifier.py")
    print("=" * 50)
    from processors.classifier import classify_domain, classify_segment
    from config import DOMAINS, SEGMENTS

    cases = [
        "Visa card top-up failing with error E5001",
        "QR code scan failure at merchant terminal",
        "OTP not received after login attempt",
        "App crash on launch — Samsung Galaxy S21",
        "Duplicate charge on single transaction",
    ]

    for issue in cases:
        domain  = classify_domain(issue)
        segment = classify_segment(issue, domain)
        assert domain in DOMAINS, f"Unknown domain: {domain}"
        assert segment in SEGMENTS[domain], f"Unknown segment: {segment}"
        print(f"  '{issue[:50]}'")
        print(f"   → {domain} / {segment}")
        print()
    print("  ✅ pass\n")


def test_sentiment():
    print("=" * 50)
    print("TEST: sentiment.py  (requires transformers + torch)")
    print("=" * 50)
    try:
        from processors.sentiment import is_negative, filter_negative
        from mock_data import get_mock_social
        from processors.preprocessor import preprocess

        social = preprocess(get_mock_social())
        negative = filter_negative(social)

        print(f"  {len(social)} posts → {len(negative)} negative")
        for p in negative:
            print(f"  [KEEP] {p['text'][:65]}")

        dropped = [p for p in social if p not in negative]
        for p in dropped:
            print(f"  [DROP] {p['text'][:65]}")

        # The 2 positive posts should be dropped
        assert len(negative) < len(social), "Should have filtered some out"
        print("  ✅ pass\n")
    except ImportError as e:
        print(f"  ⚠️  Skipped — {e}")
        print("  Run again after: pip install transformers torch\n")


if __name__ == "__main__":
    import config
    if not config.LLM_API_KEY:
        print(f"❌ LLM_API_KEY not set in .env  (LLM_PROVIDER={config.LLM_PROVIDER})")
        print("   Edit .env and add your API key, then re-run.")
        sys.exit(1)

    test_preprocessor()
    test_issue_extractor()
    test_classifier()
    test_sentiment()

    print("=" * 50)
    print("All Phase 2 tests complete ✅")
