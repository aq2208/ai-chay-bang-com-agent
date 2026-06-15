"""
AgentBase Custom Agent entrypoint — Zalopay Issue Analytics Agent.

Deployed on VNG AgentBase as a request/response Custom Agent. The platform invokes
`handler` via POST /invocations (port 8080) and calls `health` for liveness.

It also hosts a FastAPI application as a sub-app to serve the frontend dashboard,
handle ingestion callbacks from GitHub Actions, and provide database history/lock.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import httpx

import config

load_dotenv(override=True)

_VALID_JOBS = ("jira", "social", "all")


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


class AIReport(Base):
    __tablename__ = "ai_reports"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    report_type = Column(String(50), nullable=False)  # 'jira_report', 'social_report', 'unified'
    content = Column(Text, nullable=False)
    start_data_time = Column(DateTime, nullable=True)
    end_data_time = Column(DateTime, nullable=True)


class RawPost(Base):
    __tablename__ = "raw_posts"
    post_hash_id = Column(String(100), primary_key=True, index=True)


class Post(Base):
    __tablename__ = "posts"
    post_hash_id = Column(String(100), primary_key=True, index=True)
    platform = Column(String(50), nullable=False)
    matched_keyword = Column(String(200), nullable=True)
    author = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    posted_at = Column(DateTime, nullable=True)
    crawled_at = Column(DateTime, nullable=True)
    post_url = Column(String(500), nullable=True)
    images_base64 = Column(JSON, nullable=True)


# ── FastAPI App Setup ──────────────────────────────────────────────────────
api_app = FastAPI(
    title="Zalopay Complaint Analytics API",
    description="FastAPI endpoints for DB, ingestion, and UI dashboard.",
    version="1.0.0",
)

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@api_app.middleware("http")
async def disable_cache_middleware(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── WebSockets Connection Manager ──────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[ws] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[ws] Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()
main_loop = None

def broadcast_status_sync():
    """Helper đồng bộ để lấy trạng thái mới nhất từ DB và gửi tới các WS client"""
    global main_loop
    db = SessionLocal()
    try:
        jira_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "jira").order_by(CrawlHistory.id.desc()).first()
        social_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "social").order_by(CrawlHistory.id.desc()).first()
        
        status_data = {
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
        
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({"type": "status", "data": status_data}),
                main_loop
            )
    except Exception as e:
        print(f"[ws error] Lỗi khi broadcast trạng thái production: {e}")
    finally:
        db.close()

@api_app.websocket("/ws/status")
async def websocket_status_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    db = SessionLocal()
    try:
        jira_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "jira").order_by(CrawlHistory.id.desc()).first()
        social_latest = db.query(CrawlHistory).filter(CrawlHistory.job_type == "social").order_by(CrawlHistory.id.desc()).first()
        
        initial_status = {
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
        await websocket.send_json({"type": "status", "data": initial_status})
    except Exception as e:
        print(f"[ws] Lỗi gửi trạng thái ban đầu: {e}")
    finally:
        db.close()

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Concurrency Lock Worker ────────────────────────────────────────────────
def _run_job(name: str, dry_run: bool, triggered_by: str = "manual", crawl_id: int | None = None, raw_posts: list[dict] | None = None) -> None:
    """Worker executed in background thread. Updates database in-place."""
    # Lazily import to prevent heavy ML costs at startup
    from jobs import jira_job, social_job
    
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
    
    broadcast_status_sync()
    
    try:
        print(f"[crawler] Starting job '{name}' (dry_run={dry_run})...")
        if name == "social":
            result = social_job.run(dry_run=dry_run, raw_posts=raw_posts)
        else:
            result = jira_job.run(dry_run=dry_run)
        
        crawl.status = "done"
        crawl.finished_at = datetime.utcnow()
        if result and result.get("issues") == 0:
            crawl.error_message = "no post at current"
        print(f"[crawler] Job '{name}' finished. Posts saved to DB, report generation skipped.")
            
        db.commit()
        broadcast_status_sync()
    except Exception as exc:
        print(f"[crawler] Job '{name}' failed with error: {exc}")
        db.rollback()
        crawl.status = "error"
        crawl.finished_at = datetime.utcnow()
        crawl.error_message = str(exc)
        db.commit()
        broadcast_status_sync()
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


# ── REST API Endpoints ─────────────────────────────────────────────────────

@api_app.get("/status", tags=["ops"])
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



@api_app.post("/api/crawl/fail", tags=["ops"])
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


@api_app.post("/run/jira", tags=["jobs"])
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


@api_app.post("/run/social", tags=["jobs"])
def run_social(background_tasks: BackgroundTasks, dry_run: bool = True, triggered_by: str = "destroy_social_button"):
    db = SessionLocal()
    try:
        active = db.query(CrawlHistory).filter(CrawlHistory.status == "running").first()
        if active:
            raise HTTPException(status_code=400, detail="Hệ thống bận. Tiến trình cào dữ liệu khác đang hoạt động.")
        
        if not dry_run:
            if os.getenv("GITHUB_PAT") and os.getenv("GITHUB_REPO"):
                triggered = trigger_github_workflow()
                if triggered:
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
                    raise HTTPException(
                        status_code=500,
                        detail="Kích hoạt GitHub Actions thất bại. Không thể thực hiện cào dữ liệu trên agent runtime."
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Thiếu cấu hình GITHUB_PAT hoặc GITHUB_REPO để kích hoạt cào dữ liệu qua GitHub Actions."
                )
        
        background_tasks.add_task(_run_job, "social", dry_run, triggered_by)
        return {"message": "Kích hoạt cào Social thành công.", "status": "started"}
    finally:
        db.close()


@api_app.post("/run/social/callback", tags=["jobs"])
def run_social_callback(
    background_tasks: BackgroundTasks,
    payload: list[dict] = Body(...),
    dry_run: bool = False
):
    db = SessionLocal()
    try:
        # Find the active social crawl running record triggered by FE (destroy_social_button)
        active = db.query(CrawlHistory).filter(
            CrawlHistory.job_type == "social",
            CrawlHistory.status == "running",
            CrawlHistory.triggered_by == "destroy_social_button"
        ).order_by(CrawlHistory.id.desc()).first()
        
        # If not found, look for any active social running record
        if not active:
            active = db.query(CrawlHistory).filter(
                CrawlHistory.job_type == "social",
                CrawlHistory.status == "running"
            ).order_by(CrawlHistory.id.desc()).first()
            
        # If still not found, create a new history record
        if not active:
            active = CrawlHistory(
                job_type="social",
                status="running",
                started_at=datetime.utcnow(),
                triggered_by="github_workflow"
            )
            db.add(active)
            db.commit()
            db.refresh(active)

        # Deduplicate the incoming raw posts
        non_duplicates = []
        for item in payload:
            post_id = item.get("id") or item.get("post_hash_id")
            if not post_id:
                continue
            exists = db.query(RawPost).filter(RawPost.post_hash_id == post_id).first()
            if not exists:
                # Save hash ID to deduplication table raw_posts
                raw_post = RawPost(post_hash_id=post_id)
                db.add(raw_post)
                non_duplicates.append(item)
        db.commit()

        background_tasks.add_task(
            _run_job,
            "social",
            dry_run,
            "github_workflow",
            crawl_id=active.id,
            raw_posts=non_duplicates
        )
        return {"message": "Bắt đầu xử lý dữ liệu cào từ GitHub Actions.", "status": "started"}
    finally:
        db.close()


@api_app.get("/api/history", tags=["api"])
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


@api_app.get("/api/reports/latest", tags=["api"])
def get_latest_report():
    db = SessionLocal()
    try:
        report = db.query(AIReport).order_by(AIReport.id.desc()).first()
        if not report:
            return {"report": None}
        return {
            "report": {
                "id": report.id,
                "created_at": report.created_at.isoformat() + "Z" if report.created_at else None,
                "report_type": report.report_type,
                "content": report.content,
                "start_data_time": report.start_data_time.isoformat() + "Z" if report.start_data_time else None,
                "end_data_time": report.end_data_time.isoformat() + "Z" if report.end_data_time else None,
            }
        }
    finally:
        db.close()


@api_app.post("/api/reports/generate", tags=["api"])
def generate_report_from_db(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...)
):
    """
    Generate a new AI report from posts stored in DB within a given time range.
    Accepts: { "start_data_time": "2026-06-01T00:00:00", "end_data_time": "2026-06-15T23:59:59" }
    """
    start_str = payload.get("start_data_time")
    end_str = payload.get("end_data_time")

    if not start_str or not end_str:
        raise HTTPException(status_code=400, detail="Thiếu start_data_time hoặc end_data_time.")

    try:
        start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Định dạng thời gian không hợp lệ: {e}")

    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="start_data_time phải trước end_data_time.")

    db = SessionLocal()
    try:
        posts = db.query(Post).filter(
            Post.crawled_at >= start_dt,
            Post.crawled_at <= end_dt
        ).all()

        if not posts:
            return {"message": "Không có bài đăng nào trong khoảng thời gian này.", "count": 0}

        raw_posts = [
            {
                "id": p.post_hash_id,
                "post_hash_id": p.post_hash_id,
                "platform": p.platform,
                "matched_keyword": p.matched_keyword,
                "author": p.author,
                "content": p.content,
                "posted_at": p.posted_at.isoformat() if p.posted_at else None,
                "crawled_at": p.crawled_at.isoformat() if p.crawled_at else None,
                "post_url": p.post_url,
                "images_base64": p.images_base64 or [],
            }
            for p in posts
        ]
    finally:
        db.close()

    background_tasks.add_task(
        _run_report_from_posts,
        raw_posts=raw_posts,
        start_data_time=start_dt,
        end_data_time=end_dt,
    )
    return {
        "message": f"Bắt đầu tạo báo cáo từ {len(raw_posts)} bài đăng trong khoảng thời gian đã chọn.",
        "count": len(raw_posts),
        "status": "started"
    }


def _run_report_from_posts(
    raw_posts: list[dict],
    start_data_time: datetime,
    end_data_time: datetime,
) -> None:
    """Background worker: runs the report-generation pipeline on pre-fetched posts and saves to DB."""
    from jobs.social_job import run_report_only

    db = SessionLocal()
    try:
        print(f"[report] Generating report from {len(raw_posts)} posts ({start_data_time} → {end_data_time})...")
        result = run_report_only(raw_posts=raw_posts)
        report_content = ""
        report_path = result.get("report_path")
        if report_path and os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                report_content = f.read()

        if report_content:
            ai_report = AIReport(
                created_at=datetime.utcnow(),
                report_type="social_report",
                content=report_content,
                start_data_time=start_data_time,
                end_data_time=end_data_time,
            )
            db.add(ai_report)
            db.commit()
            print(f"[report] Report saved to database (id={ai_report.id}).")
        else:
            print("[report] No report content generated.")
    except Exception as exc:
        db.rollback()
        print(f"[report] Report generation failed: {exc}")
    finally:
        db.close()


# Serve Frontend Static Files
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    api_app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    print(f"[frontend] Serving frontend files from: {frontend_dir}")
else:
    print("[frontend] WARNING: 'frontend' directory not found. API only mode.")


# ── Payload Handler logic (GreenNode Custom Agent format) ──────────────────

def handle_payload(payload: dict) -> dict:
    """
    Core dispatch — pure function, importable/testable without the AgentBase SDK.
    """
    if not isinstance(payload, dict):
        return {"status": "error", "message": "Payload must be a JSON object."}

    action = str(payload.get("action") or "run").lower()

    if action == "run":
        return _run(payload)
    if action == "query":
        return _query(payload)
    return {
        "status": "error",
        "message": f"Unknown action '{action}'. Use 'run' or 'query'.",
    }


def _run(payload: dict) -> dict:
    job = str(payload.get("job") or "all").lower()
    if job not in _VALID_JOBS:
        return {"status": "error", "message": f"Invalid job '{job}'. Use one of {_VALID_JOBS}."}

    dry_run = bool(payload.get("dry_run", False))

    from jobs import jira_job, social_job

    runners = {"jira": jira_job.run, "social": social_job.run}
    selected = ["jira", "social"] if job == "all" else [job]

    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for name in selected:
        try:
            results[name] = runners[name](dry_run=dry_run)
        except Exception as exc:
            errors[name] = str(exc)

    out = {"status": "ok" if not errors else "partial", "dry_run": dry_run, "results": results}
    if errors:
        out["errors"] = errors
    return out


def _query(payload: dict) -> dict:
    question = str(payload.get("question") or "").strip()
    if not question:
        return {"status": "error", "message": "Provide a 'question' to query."}

    from knowledge_base.issues_store import answer_question

    answer = answer_question(question)
    return {"status": "ok", "question": question, "answer": answer}


# ── AgentBase wiring ────────────────────────────────────────────────────────
def _migrate_posts_datetime():
    """One-time idempotent migration: convert posts.posted_at and posts.crawled_at
    from VARCHAR to TIMESTAMP (DateTime). Safe to run on every startup."""
    from sqlalchemy import text, inspect as sa_inspect
    inspector = sa_inspect(engine)
    try:
        cols = {c["name"]: c for c in inspector.get_columns("posts")}
    except Exception:
        return  # table doesn't exist yet — create_all will handle it

    if DATABASE_URL.startswith("sqlite"):
        # SQLite doesn't support ALTER COLUMN — migrate via new column + copy + rename
        for col in ("posted_at", "crawled_at"):
            col_info = cols.get(col)
            if col_info is None:
                continue
            # Check if already a DATETIME type (SQLAlchemy reports it as 'DATETIME')
            col_type = str(col_info["type"]).upper()
            if "DATETIME" in col_type or "TIMESTAMP" in col_type:
                continue  # already migrated
            print(f"[migrate] Converting posts.{col} from VARCHAR to DATETIME (SQLite)...")
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE posts ADD COLUMN {col}_dt DATETIME"))
                # Copy: try parsing 'YYYY-MM-DD HH:MM:SS' strings; NULL-ify anything unparseable
                conn.execute(text(
                    f"UPDATE posts SET {col}_dt = "
                    f"CASE WHEN {col} IS NULL OR LOWER({col}) = 'unknown' OR {col} = '' THEN NULL "
                    f"ELSE DATETIME({col}) END"
                ))
                # SQLite can't drop columns before 3.35 — just leave old col, rename new one
                # We work around by recreating the table
                # Instead: drop old col if supported, else keep both (SQLAlchemy reads the new one)
                try:
                    conn.execute(text(f"ALTER TABLE posts DROP COLUMN {col}"))
                    conn.execute(text(f"ALTER TABLE posts RENAME COLUMN {col}_dt TO {col}"))
                    print(f"[migrate] posts.{col} migrated successfully (with DROP COLUMN).")
                except Exception:
                    # SQLite < 3.35 — keep _dt col; rename model col below won't work,
                    # so we need the full table-rebuild approach
                    print(f"[migrate] SQLite < 3.35 detected for posts.{col}; rebuilding table...")
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS posts_new (
                            post_hash_id VARCHAR(100) PRIMARY KEY,
                            platform VARCHAR(50) NOT NULL,
                            matched_keyword VARCHAR(200),
                            author VARCHAR(200),
                            content TEXT,
                            posted_at DATETIME,
                            crawled_at DATETIME,
                            post_url VARCHAR(500),
                            images_base64 JSON
                        )
                    """))
                    conn.execute(text("""
                        INSERT INTO posts_new
                        SELECT post_hash_id, platform, matched_keyword, author, content,
                               CASE WHEN posted_at IS NULL OR LOWER(posted_at)='unknown' OR posted_at='' THEN NULL
                                    ELSE DATETIME(posted_at) END,
                               CASE WHEN crawled_at IS NULL OR LOWER(crawled_at)='unknown' OR crawled_at='' THEN NULL
                                    ELSE DATETIME(crawled_at) END,
                               post_url, images_base64
                        FROM posts
                    """))
                    conn.execute(text("DROP TABLE posts"))
                    conn.execute(text("ALTER TABLE posts_new RENAME TO posts"))
                    print("[migrate] posts table rebuilt with DATETIME columns.")
                    break  # rebuilt whole table, no need to loop more cols
    else:
        # PostgreSQL: ALTER COLUMN ... USING
        for col in ("posted_at", "crawled_at"):
            col_info = cols.get(col)
            if col_info is None:
                continue
            col_type = str(col_info["type"]).upper()
            if "TIMESTAMP" in col_type or "DATETIME" in col_type:
                continue
            print(f"[migrate] Converting posts.{col} from VARCHAR to TIMESTAMP (PostgreSQL)...")
            with engine.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE posts ALTER COLUMN {col} TYPE TIMESTAMP "
                    f"USING CASE WHEN {col} IS NULL OR LOWER({col}) = 'unknown' OR {col} = '' "
                    f"THEN NULL ELSE {col}::TIMESTAMP END"
                ))
                print(f"[migrate] posts.{col} migrated successfully.")

try:
    from contextlib import asynccontextmanager
    from greennode_agentbase import GreenNodeAgentBaseApp, RequestContext, PingStatus

    @asynccontextmanager
    async def lifespan(app):
        # Automatically initialize SQLite or PostgreSQL schemas
        Base.metadata.create_all(bind=engine)
        print("[database] Database tables verified/created successfully.")

        # Migrate posts datetime columns from VARCHAR → DATETIME if needed
        try:
            _migrate_posts_datetime()
        except Exception as e:
            print(f"[database] WARNING: datetime migration failed: {e}")
        
        # Store event loop reference
        global main_loop
        main_loop = asyncio.get_running_loop()
        
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

        print("=" * 75)
        print(f"🚀 Zalopay Complaint Analytics Server is up and running!")
        print(f"👉 Control Center Dashboard UI: http://localhost:{config.PORT}")
        print("=" * 75)
        yield

    app = GreenNodeAgentBaseApp(lifespan=lifespan)
    
    # Mount the FastAPI sub-app to handle database/frontend/ingestion endpoints
    app.mount("/", api_app)

    @app.entrypoint
    def handler(payload: dict, context: "RequestContext") -> dict:
        return handle_payload(payload)

    @app.ping
    def health() -> "PingStatus":
        return PingStatus.HEALTHY

    if __name__ == "__main__":
        app.run(port=8080, host="0.0.0.0")

except (ImportError, TypeError):
    app = None

    if __name__ == "__main__":
        raise SystemExit(
            "greennode-agentbase is not installed (needs Python 3.10+).\n"
            "Install it to run the AgentBase server, or test the dispatch logic with:\n"
            "    from main import handle_payload"
        )
