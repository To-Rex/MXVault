import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.scheduler import shutdown_scheduler, start_scheduler
from app.templates import templates

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
    init_db()
    start_scheduler()
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


@app.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version}


from app.api import auth, backups, connections, dashboard, restore, schedules, settings as settings_api, storage

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(connections.router)
app.include_router(backups.router)
app.include_router(schedules.router)
app.include_router(settings_api.router)
app.include_router(storage.router)
app.include_router(restore.router)


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
