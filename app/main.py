import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.auth import get_session_user
from app.services.scheduler import shutdown_scheduler, start_scheduler
from app.templates import templates
from app.utils.psql_installer import ensure_psql_installed

logger = logging.getLogger("mxvault")


def init_db():
    Base.metadata.create_all(bind=engine)
    from app.services.auth import create_default_admin, get_default_admin

    db = SessionLocal()
    try:
        admin = get_default_admin(db)
        if not admin:
            logger.info("Creating default admin user (admin/admin123)")
            create_default_admin(db)
            logger.info("Default admin user created")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    ensure_psql_installed()
    init_db()
    start_scheduler()

    db = SessionLocal()
    try:
        from app.services.notification import notify_app_started
        notify_app_started(db, settings.app_version, settings.host, settings.port)
    finally:
        db.close()

    yield
    shutdown_scheduler()
    logger.info("Application shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/favicon.ico")
def favicon():
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient></defs>
  <rect width="64" height="64" rx="14" fill="url(#g)"/>
  <path d="M20 28v16a4 4 0 004 4h16a4 4 0 004-4V28M20 28a4 4 0 014-4h16a4 4 0 014 4M20 28l-4-8h32l-4 8M32 24v20" stroke="#fff" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M26 32l4 4 8-8" stroke="#a5b4fc" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/robots.txt")
def robots():
    return Response(
        content="User-agent: *\nDisallow: /\n",
        media_type="text/plain",
    )


@app.get("/")
def root(request: Request):
    user = None
    db = SessionLocal()
    try:
        token = request.cookies.get("session_token")
        if token:
            user = get_session_user(token, db)
    finally:
        db.close()
    return templates.TemplateResponse(request, "landing.html", {"request": request, "user": user})


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}


from app.api import auth, backups, connections, dashboard, inspect, restore, schedules, settings as settings_api, storage

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(connections.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(settings_api.router)
app.include_router(storage.router)
app.include_router(restore.router)
app.include_router(inspect.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse(url="/auth/login", status_code=302)
    return templates.TemplateResponse(
        request, "error.html",
        {"request": request, "error": exc.detail, "code": exc.status_code},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return templates.TemplateResponse(
        request, "error.html",
        {"request": request, "error": "Internal server error", "code": 500},
        status_code=500,
    )
