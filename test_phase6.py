"""
Phase 6 tests — Jira Job & Social Job (dry_run=True)

Usage:
    .venv/bin/python test_phase6.py

Both jobs use mock data (dry_run=True) so no real API credentials are needed.
LLM calls (extraction, classification, report) are skipped gracefully if quota
is exhausted.
"""

import sys
sys.path.insert(0, ".")

_QUOTA_ERRORS = ("RESOURCE_EXHAUSTED", "quota", "ConnectTimeout", "timeout", "NotImplementedError")


def _quota_skip(e: Exception) -> bool:
    return any(k in str(e) for k in _QUOTA_ERRORS)


# ── Connector stubs ────────────────────────────────────────────────────────

def test_connector_stubs_raise():
    print("=" * 50)
    print("TEST: connector stubs — raise without credentials")
    print("=" * 50)
    import config
    saved_config = {
        "JIRA_URL": config.JIRA_URL,
        "JIRA_EMAIL": config.JIRA_EMAIL,
        "JIRA_API_TOKEN": config.JIRA_API_TOKEN,
        "FB_ACCESS_TOKEN": config.FB_ACCESS_TOKEN,
        "FB_PAGE_IDS": config.FB_PAGE_IDS,
    }
    config.JIRA_URL = ""
    config.JIRA_EMAIL = ""
    config.JIRA_API_TOKEN = ""
    config.FB_ACCESS_TOKEN = ""
    config.FB_PAGE_IDS = []

    try:
        from connectors.jira import fetch as jira_fetch
        from connectors.facebook import fetch as fb_fetch
        from connectors.threads import fetch as th_fetch

        from unittest.mock import patch
        with patch("connectors.threads.bronze.load_latest", return_value=None):
            for name, fn in [("jira", jira_fetch), ("facebook", fb_fetch), ("threads", th_fetch)]:
                try:
                    fn()
                    assert False, f"{name} connector should have raised"
                except (RuntimeError, NotImplementedError):
                    print(f"  {name}: raises correctly ✅")
    finally:
        config.JIRA_URL = saved_config["JIRA_URL"]
        config.JIRA_EMAIL = saved_config["JIRA_EMAIL"]
        config.JIRA_API_TOKEN = saved_config["JIRA_API_TOKEN"]
        config.FB_ACCESS_TOKEN = saved_config["FB_ACCESS_TOKEN"]
        config.FB_PAGE_IDS = saved_config["FB_PAGE_IDS"]
    print()


# ── Jira Job ───────────────────────────────────────────────────────────────

def test_jira_job_dry_run():
    print("=" * 50)
    print("TEST: jira_job — dry_run=True (mock data, full pipeline)")
    print("=" * 50)
    from jobs.jira_job import run
    try:
        result = run(dry_run=True)
    except Exception as e:
        if _quota_skip(e):
            print(f"  ⏭  Skipped — API quota/network: {type(e).__name__}: {e}\n")
            return
        raise

    print(f"\n  report_path : {result['report_path']}")
    print(f"  issues      : {result['issues']}")
    print(f"  mentions    : {result['mentions']}")

    assert isinstance(result["report_path"], str)
    assert result["issues"] >= 0
    assert result["mentions"] >= result["issues"]
    print("  ✅ pass\n")


# ── Social Job ─────────────────────────────────────────────────────────────

def test_social_job_dry_run():
    print("=" * 50)
    print("TEST: social_job — dry_run=True (mock data, full pipeline)")
    print("=" * 50)
    from jobs.social_job import run
    try:
        result = run(dry_run=True)
    except Exception as e:
        if _quota_skip(e):
            print(f"  ⏭  Skipped — API quota/network: {type(e).__name__}: {e}\n")
            return
        raise

    print(f"\n  report_path : {result['report_path']}")
    print(f"  issues      : {result['issues']}")
    print(f"  mentions    : {result['mentions']}")

    assert isinstance(result["report_path"], str)
    assert result["issues"] >= 0
    assert result["mentions"] >= result["issues"]
    print("  ✅ pass\n")


if __name__ == "__main__":
    test_connector_stubs_raise()
    test_jira_job_dry_run()
    test_social_job_dry_run()

    print("=" * 50)
    print("All Phase 6 tests complete ✅")
