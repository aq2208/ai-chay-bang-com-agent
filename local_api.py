"""
Local development API — FastAPI server + APScheduler.

NOTE: This is for LOCAL development/testing only. The deployed AgentBase runtime
uses main.py (greennode-agentbase Custom Agent, /invocations). APScheduler is not
used in production — scheduling on AgentBase is external/on-demand.

Endpoints:
  GET  /health          — liveness check
  GET  /status          — last run result for each job
  POST /run/jira        — trigger Jira job now  (?dry_run=true)
  POST /run/social      — trigger Social job now (?dry_run=true)

Scheduler (runs daily):
  Jira job   → JIRA_SCHEDULE_HOUR:JIRA_SCHEDULE_MINUTE   (default 08:00)
  Social job → SOCIAL_SCHEDULE_HOUR:SOCIAL_SCHEDULE_MINUTE (default 08:30)

Start the server:
    .venv/bin/uvicorn local_api:app --host 0.0.0.0 --port 8000 --reload

Or run directly:
    .venv/bin/python local_api.py
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI
from apscheduler.schedulers.background import BackgroundScheduler

import config
from jobs import jira_job, social_job

app = FastAPI(
    title="ZaloPay Complaint Analytics (local dev)",
    description="Local FastAPI harness for the Jira and Social Media pipelines.",
    version="1.0.0",
)

# ── In-memory job status ───────────────────────────────────────────────────
# Keyed by job name. Each entry: {"status", "started_at", "finished_at", "result"/"error"}
_status: dict[str, dict] = {
    "jira":   {"status": "idle"},
    "social": {"status": "idle"},
}
_lock = threading.Lock()


def _run_job(name: str, dry_run: bool) -> None:
    """Worker executed in background thread. Updates _status in-place."""
    runner = jira_job.run if name == "jira" else social_job.run
    with _lock:
        _status[name] = {
            "status":     "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "dry_run":    dry_run,
        }
    try:
        result = runner(dry_run=dry_run)
        with _lock:
            _status[name].update({
                "status":      "done",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result":      result,
            })
    except Exception as exc:
        with _lock:
            _status[name].update({
                "status":      "error",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error":       str(exc),
            })


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/status", tags=["ops"])
def status():
    with _lock:
        return dict(_status)


@app.post("/invocations", tags=["agent"])
def invocations(payload: dict):
    """
    AgentBase invocations mock endpoint.
    Accepts payloads like:
      {"action": "run", "job": "social", "dry_run": false}
      {"action": "query", "question": "..."}
    """
    from main import handle_payload
    return handle_payload(payload)


@app.post("/run/jira", tags=["jobs"])
def run_jira(background_tasks: BackgroundTasks, dry_run: bool = True):
    """
    Trigger the Jira complaint pipeline.
    Returns immediately; job runs in background.
    Poll GET /status for results.
    """
    with _lock:
        if _status["jira"].get("status") == "running":
            return {"message": "Jira job is already running", "status": _status["jira"]}
    background_tasks.add_task(_run_job, "jira", dry_run)
    return {"message": "Jira job started", "dry_run": dry_run}


@app.post("/run/social", tags=["jobs"])
def run_social(background_tasks: BackgroundTasks, dry_run: bool = True):
    """
    Trigger the Social Media complaint pipeline.
    Returns immediately; job runs in background.
    Poll GET /status for results.
    """
    with _lock:
        if _status["social"].get("status") == "running":
            return {"message": "Social job is already running", "status": _status["social"]}
    background_tasks.add_task(_run_job, "social", dry_run)
    return {"message": "Social job started", "dry_run": dry_run}


# ── Scheduler ─────────────────────────────────────────────────────────────

def _start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(
        lambda: _run_job("jira", dry_run=False),
        trigger="cron",
        hour=config.JIRA_SCHEDULE_HOUR,
        minute=config.JIRA_SCHEDULE_MINUTE,
        id="jira_daily",
    )
    scheduler.add_job(
        lambda: _run_job("social", dry_run=False),
        trigger="cron",
        hour=config.SOCIAL_SCHEDULE_HOUR,
        minute=config.SOCIAL_SCHEDULE_MINUTE,
        id="social_daily",
    )
    scheduler.start()
    return scheduler


@app.on_event("startup")
def startup():
    app.state.scheduler = _start_scheduler()
    print(
        f"[scheduler] Jira daily at {config.JIRA_SCHEDULE_HOUR:02d}:{config.JIRA_SCHEDULE_MINUTE:02d} ICT | "
        f"Social daily at {config.SOCIAL_SCHEDULE_HOUR:02d}:{config.SOCIAL_SCHEDULE_MINUTE:02d} ICT"
    )


@app.on_event("shutdown")
def shutdown():
    app.state.scheduler.shutdown(wait=False)


# ── Dev entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("local_api:app", host=config.HOST, port=config.PORT, reload=True)
