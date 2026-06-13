"""
ZaloPay Complaint Analytics API — FastAPI server + Database History & Lock.

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
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from apscheduler.schedulers.background import BackgroundScheduler

import config
from jobs import jira_job, social_job

# ── Database Setup ─────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

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

# ── FastAPI App Setup ──────────────────────────────────────────────────────
app = FastAPI(
    title="ZaloPay Complaint Analytics",
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

# ── Concurrency Lock Worker ────────────────────────────────────────────────
def _run_job(name: str, dry_run: bool, triggered_by: str = "manual") -> None:
    """Worker executed in background thread. Updates database in-place."""
    runner = jira_job.run if name == "jira" else social_job.run
    
    db = SessionLocal()
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
            raise HTTPException(status_code=400, detail="Hệ thống bận. Tiến trình cào dữ liệu khác đang hoạt động.")
        
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
