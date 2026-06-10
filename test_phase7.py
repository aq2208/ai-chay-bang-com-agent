"""
Phase 7 tests — FastAPI server

Tests the API layer only. Job execution is already covered by test_phase6.py.
Uses FastAPI's TestClient + unittest.mock to avoid triggering real pipeline runs.

Usage:
    .venv/bin/python test_phase7.py
"""

import sys
sys.path.insert(0, ".")

from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# Stub result returned by the mock job runner
_MOCK_RESULT = {"report_path": "/tmp/report.md", "issues": 3, "mentions": 6}


def test_health():
    print("=" * 50)
    print("TEST: GET /health")
    print("=" * 50)
    resp = client.get("/health")
    print(f"  status_code : {resp.status_code}")
    print(f"  body        : {resp.json()}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "timestamp" in resp.json()
    print("  ✅ pass\n")


def test_status_initial():
    print("=" * 50)
    print("TEST: GET /status — initial state is idle")
    print("=" * 50)
    resp = client.get("/status")
    print(f"  status_code : {resp.status_code}")
    print(f"  body        : {resp.json()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jira"]["status"] in ("idle", "done", "error")   # may have run from a prior test
    assert body["social"]["status"] in ("idle", "done", "error")
    print("  ✅ pass\n")


def test_run_jira_trigger():
    print("=" * 50)
    print("TEST: POST /run/jira — returns immediately, job runs in background")
    print("=" * 50)

    # Patch the job runner so no real LLM calls are made
    with patch("main._run_job", side_effect=lambda name, dry_run: None) as mock_run:
        import main as m
        with m._lock:
            m._status["jira"] = {"status": "idle"}  # reset

        resp = client.post("/run/jira?dry_run=true")
        print(f"  status_code : {resp.status_code}")
        print(f"  body        : {resp.json()}")
        assert resp.status_code == 200
        body = resp.json()
        assert "jira" in body["message"].lower()
        assert body["dry_run"] is True
    print("  ✅ pass\n")


def test_run_social_trigger():
    print("=" * 50)
    print("TEST: POST /run/social — returns immediately, job runs in background")
    print("=" * 50)

    with patch("main._run_job", side_effect=lambda name, dry_run: None):
        import main as m
        with m._lock:
            m._status["social"] = {"status": "idle"}

        resp = client.post("/run/social?dry_run=true")
        print(f"  status_code : {resp.status_code}")
        print(f"  body        : {resp.json()}")
        assert resp.status_code == 200
        body = resp.json()
        assert "social" in body["message"].lower()
        assert body["dry_run"] is True
    print("  ✅ pass\n")


def test_duplicate_trigger_blocked():
    print("=" * 50)
    print("TEST: POST /run/jira twice — second blocked while first is running")
    print("=" * 50)
    import main as m

    # Simulate an in-progress job
    with m._lock:
        m._status["jira"]["status"] = "running"

    resp = client.post("/run/jira?dry_run=true")
    print(f"  status_code : {resp.status_code}")
    print(f"  body        : {resp.json()}")
    assert resp.status_code == 200
    assert "already running" in resp.json()["message"].lower()

    # Restore
    with m._lock:
        m._status["jira"]["status"] = "idle"
    print("  ✅ pass\n")


def test_status_reflects_completed_job():
    print("=" * 50)
    print("TEST: GET /status — shows done after job completes")
    print("=" * 50)
    import main as m

    # Simulate a completed run
    with m._lock:
        m._status["jira"] = {
            "status":      "done",
            "started_at":  "2026-06-10T08:00:00+00:00",
            "finished_at": "2026-06-10T08:05:00+00:00",
            "dry_run":     True,
            "result":      _MOCK_RESULT,
        }

    resp = client.get("/status")
    print(f"  status_code : {resp.status_code}")
    body = resp.json()
    print(f"  jira status : {body['jira']['status']}")
    print(f"  jira result : {body['jira']['result']}")
    assert resp.status_code == 200
    assert body["jira"]["status"] == "done"
    assert body["jira"]["result"]["issues"] == 3

    # Restore
    with m._lock:
        m._status["jira"] = {"status": "idle"}
    print("  ✅ pass\n")


def test_openapi_docs():
    print("=" * 50)
    print("TEST: GET /docs — OpenAPI UI available")
    print("=" * 50)
    resp = client.get("/docs")
    print(f"  status_code : {resp.status_code}")
    assert resp.status_code == 200
    print("  ✅ pass\n")


if __name__ == "__main__":
    test_health()
    test_status_initial()
    test_run_jira_trigger()
    test_run_social_trigger()
    test_duplicate_trigger_blocked()
    test_status_reflects_completed_job()
    test_openapi_docs()

    print("=" * 50)
    print("All Phase 7 tests complete ✅")
