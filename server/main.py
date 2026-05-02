from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from server.api.health import router as health_router
from server.api.recordings import router as recordings_router
from server.config import load_server_config
from server.database import get_db, init_db
from server import crud

_TEMPLATES_DIR = Path(__file__).parent / "templates"
logger = logging.getLogger(__name__)

async def _stale_upload_watcher(timeout_seconds: int) -> None:
    # Check at 1/3 of the timeout interval so we catch stale uploads promptly
    # without hammering the DB. Minimum 5 s to avoid a tight loop.
    check_interval = max(5, timeout_seconds // 3)
    while True:
        await asyncio.sleep(check_interval)
        db_gen = get_db()
        db = next(db_gen)
        try:
            count = crud.mark_stale_uploads_interrupted(db, timeout_seconds)
            if count:
                logger.warning("Marked %d stale upload(s) as interrupted", count)
        except Exception:
            logger.exception("Error in stale upload watcher")
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_server_config()
    init_db(cfg.db_path)
    check_interval = max(5, cfg.upload_stale_timeout_seconds // 3)
    task = asyncio.create_task(
        _stale_upload_watcher(cfg.upload_stale_timeout_seconds)
    )
    logger.info(
        "Stale upload watcher started (timeout=%ds, check every %ds)",
        cfg.upload_stale_timeout_seconds,
        check_interval,
    )
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Liftboy Server", version="0.1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app.include_router(recordings_router, prefix="/recordings", tags=["recordings"])
app.include_router(health_router, tags=["health"])


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    robot: str | None = None,
    status: str | None = None,
):
    db_gen = get_db()
    db = next(db_gen)
    try:
        recordings = crud.list_recordings(db, robot_name=robot, status=status, exclude_completed=(status == "!completed"))
        robots = sorted({r.robot_name for r in crud.list_recordings(db)})
        statuses = ["pending", "uploading", "completed", "failed", "interrupted"]
        client_summaries = crud.get_client_summaries(db)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "recordings": recordings,
                "robots": robots,
                "statuses": statuses,
                "filter_robot": robot or "",
                "filter_status": status or "",
                "client_summaries": client_summaries,
            },
        )
    finally:
        try:
            next(db_gen)
        except StopIteration:
            pass


def run() -> None:
    cfg = load_server_config()
    uvicorn.run(
        "server.main:app",
        host=cfg.host,
        port=cfg.port,
        log_level=cfg.log_level,
        reload=False,
    )


if __name__ == "__main__":
    run()
