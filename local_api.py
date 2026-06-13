"""
Zalopay Complaint Analytics API — FastAPI server + Database History & Lock.

Endpoints:
  GET  /health          — liveness check
  GET  /status          — last run result for each job (queries DB)
  POST /run/jira        — trigger Jira job now
  POST /run/social      — trigger Social job now
  POST /invocations     — AgentBase standard invocations endpoint
  GET  /api/history     — returns execution history list
  GET  /api/reports/latest — returns latest AI generated report
  
Static Files:
  GET  /                 — serves frontend/index.html
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from apscheduler.schedulers.background import BackgroundScheduler
import httpx

import config
from jobs import jira_job, social_job

# ── Database Setup ─────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

try:
    if DATABASE_URL.startswith("sqlite"):
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    else:
        engine = create_engine(DATABASE_URL)
    # Test connection
    with engine.connect() as conn:
        pass
    print(f"[database] Successfully connected to database: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL}")
except Exception as e:
    print(f"[database] WARNING: Failed to connect to {DATABASE_URL}. Error: {e}")
    print("[database] Falling back to local SQLite: sqlite:///data.db")
    DATABASE_URL = "sqlite:///data.db"
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── Database Models ────────────────────────────────────────────────────────
class CrawlHistory(Base):
    __tablename__ = "crawl_history"
    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50), nullable=False)  # 'jira', 'social', 'all'
    status = Column(String(50), nullable=False)    # 'running', 'done', 'error'
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    
    reports = relationship("AIReport", back_populates="crawl", cascade="all, delete-orphan")

class AIReport(Base):
    __tablename__ = "ai_reports"
    id = Column(Integer, primary_key=True, index=True)
    crawl_id = Column(Integer, ForeignKey("crawl_history.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    report_type = Column(String(50), nullable=False)  # 'jira_report', 'social_report', 'unified'
    content = Column(Text, nullable=False)
    
    crawl = relationship("CrawlHistory", back_populates="reports")

class RawPost(Base):
    __tablename__ = "raw_posts"
    post_hash_id = Column(String(100), primary_key=True, index=True)
    platform = Column(String(50), nullable=False)
    matched_keyword = Column(String(200), nullable=True)
    author = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    posted_at = Column(String(50), nullable=True)
    crawled_at = Column(String(50), nullable=True)
    post_url = Column(String(500), nullable=True)
    images_base64 = Column(JSON, nullable=True)


# ── FastAPI App Setup ──────────────────────────────────────────────────────
app = FastAPI(
    title="Zalopay Complaint Analytics",
    description="FastAPI harness for the Jira and Social Media pipelines with DB storage.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prevent Caching Middleware (for reliable local frontend updates) ──────
@app.middleware("http")
async def disable_cache_middleware(request, call_next):
    response = await call_next(request)
    # Set headers to prevent caching for frontend assets
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ── Concurrency Lock Worker ────────────────────────────────────────────────
def _run_job(name: str, dry_run: bool, triggered_by: str = "manual", crawl_id: int | None = None) -> None:
    """Worker executed in background thread. Updates database in-place."""
    runner = jira_job.run if name == "jira" else social_job.run
    
    db = SessionLocal()
    crawl = None
    if crawl_id is not None:
        crawl = db.query(CrawlHistory).filter(CrawlHistory.id == crawl_id).first()
        if crawl:
            crawl.status = "running"
            db.commit()
            
    if crawl is None:
        crawl = CrawlHistory(
            job_type=name,
            status="running",
            started_at=datetime.utcnow(),
            triggered_by=triggered_by
        )
        db.add(crawl)
        db.commit()
        db.refresh(crawl)
    
    try:
        print(f"[crawler] Starting job '{name}' (dry_run={dry_run})...")
        result = runner(dry_run=dry_run)
        
        # Read the report content if report_path exists
        report_content = ""
        report_path = result.get("report_path")
        if report_path and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read()
        
        crawl.status = "done"
        crawl.finished_at = datetime.utcnow()
        
        if report_content:
            ai_report = AIReport(
                crawl_id=crawl.id,
                created_at=datetime.utcnow(),
                report_type=f"{name}_report",
                content=report_content
            )
            db.add(ai_report)
            print(f"[crawler] Job '{name}' finished and AI report saved to database.")
        else:
            print(f"[crawler] Job '{name}' finished, no report path found.")
            
        db.commit()
    except Exception as exc:
        print(f"[crawler] Job '{name}' failed with error: {exc}")
        db.rollback()
        crawl.status = "error"
        crawl.finished_at = datetime.utcnow()
        crawl.error_message = str(exc)
        db.commit()
    finally:
        db.close()

# ── REST API Endpoints ─────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/status", tags=["ops"])
def status():
    db = SessionLocal()
    try:
        jira_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "jira").order_by(CrawlHistory.id.desc()).first()
        social_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "social").order_by(CrawlHistory.id.desc()).first()
        
        res = {
            "jira": {
                "status": jira_latest.status if jira_latest else "idle",
                "started_at": jira_latest.started_at.isoformat() + "Z" if jira_latest and jira_latest.started_at else None,
                "finished_at": jira_latest.finished_at.isoformat() + "Z" if jira_latest and jira_latest.finished_at else None,
                "triggered_by": jira_latest.triggered_by if jira_latest else None,
                "error": jira_latest.error_message if jira_latest else None
            },
            "social": {
                "status": social_latest.status if social_latest else "idle",
                "started_at": social_latest.started_at.isoformat() + "Z" if social_latest and social_latest.started_at else None,
                "finished_at": social_latest.finished_at.isoformat() + "Z" if social_latest and social_latest.finished_at else None,
                "triggered_by": social_latest.triggered_by if social_latest else None,
                "error": social_latest.error_message if social_latest else None
            }
        }
        return res
    finally:
        db.close()


def trigger_github_workflow() -> bool:
    pat = os.getenv("GITHUB_PAT")
    repo = os.getenv("GITHUB_REPO")
    workflow = os.getenv("GITHUB_WORKFLOW", "daily_crawl.yml")
    if not pat or not repo:
        return False
    
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Zalopay-Complaint-Analytics-Agent"
    }
    data = {
        "ref": os.getenv("GITHUB_BRANCH", "main")
    }
    try:
        print(f"[github] Triggering workflow dispatch: {url}")
        with httpx.Client() as client:
            r = client.post(url, json=data, headers=headers, timeout=10)
        if r.status_code == 204:
            print("[github] Workflow dispatch triggered successfully.")
            return True
        else:
            print(f"[github] Failed to trigger workflow: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"[github] Error triggering workflow: {e}")
        return False


@app.post("/api/ingest/social", tags=["ingest"])
def ingest_social(payload: list[dict]):
    db = SessionLocal()
    try:
        new_count = 0
        for item in payload:
            post_id = item.get("id") or item.get("post_hash_id")
            if not post_id:
                continue
            # Check if exists
            exists = db.query(RawPost).filter(RawPost.post_hash_id == post_id).first()
            if not exists:
                raw_post = RawPost(
                    post_hash_id=post_id,
                    platform=item.get("platform", "Threads"),
                    matched_keyword=item.get("matched_keyword"),
                    author=item.get("author"),
                    content=item.get("text") or item.get("content"),
                    posted_at=item.get("timestamp") or item.get("posted_at"),
                    crawled_at=item.get("crawled_at") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    post_url=item.get("url") or item.get("post_url"),
                    images_base64=item.get("images") or item.get("images_base64", [])
                )
                db.add(raw_post)
                new_count += 1
        db.commit()
        return {"message": f"Successfully ingested {len(payload)} posts. New: {new_count}.", "status": "ok"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
    finally:
        db.close()


@app.post("/api/crawl/fail", tags=["ops"])
def crawl_fail(payload: dict):
    job_type = payload.get("job_type", "social")
    error_msg = payload.get("error", "GitHub Actions workflow run failed.")
    db = SessionLocal()
    try:
        active = db.query(CrawlHistory).filter(
            CrawlHistory.job_type == job_type,
            CrawlHistory.status == "running"
        ).order_by(CrawlHistory.id.desc()).first()
        if active:
            active.status = "error"
            active.finished_at = datetime.utcnow()
            active.error_message = error_msg
            db.commit()
            print(f"[crawler] Marked active job {active.id} as failed via callback.")
            return {"status": "ok", "message": "Job status updated to error."}
        return {"status": "ok", "message": "No active running job found to fail."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.post("/run/jira", tags=["jobs"])
def run_jira(background_tasks: BackgroundTasks, dry_run: bool = True, triggered_by: str = "manual_left_btn"):
    db = SessionLocal()
    try:
        active = db.query(CrawlHistory).filter(CrawlHistory.status == "running").first()
        if active:
            raise HTTPException(status_code=400, detail="Hệ thống bận. Tiến trình cào dữ liệu khác đang hoạt động.")
        
        background_tasks.add_task(_run_job, "jira", dry_run, triggered_by)
        return {"message": "Kích hoạt cào Jira thành công.", "status": "started"}
    finally:
        db.close()


@app.post("/run/social", tags=["jobs"])
def run_social(background_tasks: BackgroundTasks, dry_run: bool = True, triggered_by: str = "manual_right_btn"):
    db = SessionLocal()
    try:
        active = db.query(CrawlHistory).filter(CrawlHistory.status == "running").first()
        if active:
            # If the request comes from the github workflow callback and matches our manually triggered running run, re-use it!
            if triggered_by == "github_workflow" and active.job_type == "social" and active.triggered_by == "manual_right_btn":
                background_tasks.add_task(_run_job, "social", dry_run, triggered_by, crawl_id=active.id)
                return {"message": "Bắt đầu xử lý dữ liệu cào từ GitHub Actions.", "status": "started"}
                
            raise HTTPException(status_code=400, detail="Hệ thống bận. Tiến trình cào dữ liệu khác đang hoạt động.")
        
        # Trigger GitHub workflow if GITHUB_PAT and GITHUB_REPO are set, dry_run is False,
        # and this trigger did not come from the github workflow itself.
        if not dry_run and triggered_by != "github_workflow" and os.getenv("GITHUB_PAT") and os.getenv("GITHUB_REPO"):
            triggered = trigger_github_workflow()
            if triggered:
                # Create a run record immediately to lock the UI
                crawl = CrawlHistory(
                    job_type="social",
                    status="running",
                    started_at=datetime.utcnow(),
                    triggered_by=triggered_by
                )
                db.add(crawl)
                db.commit()
                return {
                    "message": "Kích hoạt cào dữ liệu sống thành công qua GitHub Actions. Tiến trình xử lý sẽ tự động bắt đầu sau khi hoàn thành cào.",
                    "status": "github_triggered"
                }
            else:
                print("[run_social] Failed to trigger GitHub Action, falling back to local run on current DB data.")
        
        background_tasks.add_task(_run_job, "social", dry_run, triggered_by)
        return {"message": "Kích hoạt cào Social thành công.", "status": "started"}
    finally:
        db.close()


@app.post("/invocations", tags=["jobs"])
def invocations(payload: dict, background_tasks: BackgroundTasks):
    """GreenNode AgentBase standard entrypoint payload routing."""
    action = str(payload.get("action", "run")).lower()
    job = str(payload.get("job", "all")).lower()
    dry_run = bool(payload.get("dry_run", False))
    
    if action == "run":
        db = SessionLocal()
        try:
            active = db.query(CrawlHistory).filter(CrawlHistory.status == "running").first()
            if active:
                return {"status": "error", "message": "Hệ thống bận. Tiến trình khác đang hoạt động."}
            
            if job == "all":
                background_tasks.add_task(_run_job, "jira", dry_run, "github_cron")
                background_tasks.add_task(_run_job, "social", dry_run, "github_cron")
            elif job in ("jira", "social"):
                background_tasks.add_task(_run_job, job, dry_run, "github_cron")
            else:
                return {"status": "error", "message": f"Job '{job}' không hợp lệ. Chọn jira|social|all."}
                
            return {"status": "ok", "message": f"Kích hoạt cào {job} thành công qua /invocations."}
        finally:
            db.close()
            
    return {"status": "error", "message": f"Hành động '{action}' không được hỗ trợ qua /invocations."}


@app.get("/api/history", tags=["api"])
def get_history():
    db = SessionLocal()
    try:
        history_list = db.query(CrawlHistory).order_by(CrawlHistory.id.desc()).limit(20).all()
        return [
            {
                "id": h.id,
                "job_type": h.job_type,
                "status": h.status,
                "started_at": h.started_at.isoformat() + "Z" if h.started_at else None,
                "finished_at": h.finished_at.isoformat() + "Z" if h.finished_at else None,
                "triggered_by": h.triggered_by,
                "error_message": h.error_message
            }
            for h in history_list
        ]
    finally:
        db.close()


@app.get("/api/reports/latest", tags=["api"])
def get_latest_report():
    db = SessionLocal()
    try:
        report = db.query(AIReport).order_by(AIReport.id.desc()).first()
        if not report:
            return {"report": None}
        return {
            "report": {
                "id": report.id,
                "crawl_id": report.crawl_id,
                "created_at": report.created_at.isoformat() + "Z" if report.created_at else None,
                "report_type": report.report_type,
                "content": report.content
            }
        }
    finally:
        db.close()

# ── Local Scheduler (Only for local development, fallback) ──────────────────
def _start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(
        lambda: _run_job("jira", dry_run=False, triggered_by="local_cron"),
        trigger="cron",
        hour=config.JIRA_SCHEDULE_HOUR,
        minute=config.JIRA_SCHEDULE_MINUTE,
        id="jira_daily",
    )
    scheduler.add_job(
        lambda: _run_job("social", dry_run=False, triggered_by="local_cron"),
        trigger="cron",
        hour=config.SOCIAL_SCHEDULE_HOUR,
        minute=config.SOCIAL_SCHEDULE_MINUTE,
        id="social_daily",
    )
    scheduler.start()
    return scheduler

# ── App Lifetime Events ─────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    # Automatically initialize SQLite or PostgreSQL schemas
    Base.metadata.create_all(bind=engine)
    print("[database] Database tables verified/created successfully.")
    
    # Recover orphaned running jobs on startup
    db = SessionLocal()
    try:
        orphaned = db.query(CrawlHistory).filter(CrawlHistory.status == "running").all()
        for crawl in orphaned:
            print(f"[database] Recovering orphaned job run ID {crawl.id} (status: running -> error)")
            crawl.status = "error"
            crawl.finished_at = datetime.utcnow()
            crawl.error_message = "Tiến trình bị gián đoạn do máy chủ khởi động lại."
        db.commit()
    except Exception as e:
        print(f"[database] Failed to recover orphaned jobs: {e}")
    finally:
        db.close()
    
    # Start the local scheduler (fallback)
    app.state.scheduler = _start_scheduler()
    print(
        f"[scheduler] Local fallback scheduler active: Jira daily at {config.JIRA_SCHEDULE_HOUR:02d}:{config.JIRA_SCHEDULE_MINUTE:02d} | "
        f"Social daily at {config.SOCIAL_SCHEDULE_HOUR:02d}:{config.SOCIAL_SCHEDULE_MINUTE:02d} ICT"
    )

@app.on_event("shutdown")
def shutdown():
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.shutdown(wait=False)

# ── Serve Frontend Static Files ─────────────────────────────────────────────
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    print(f"[frontend] Serving frontend files from: {frontend_dir}")
else:
    print("[frontend] WARNING: Thư mục 'frontend' không tồn tại. Chỉ phục vụ API.")

# ── Dev Entrypoint ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("local_api:app", host=config.HOST, port=config.PORT, reload=True)
