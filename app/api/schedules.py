from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.connection import PGConnection
from app.models.schedule import BackupSchedule
from app.models.user import User
from app.services.audit import log_audit
from app.services.scheduler import add_schedule_job, pause_schedule_job, remove_schedule_job, resume_schedule_job
from app.templates import templates

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("")
def list_schedules(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import datetime as dt

    from app.services.scheduler import scheduler

    schedules = db.query(BackupSchedule).order_by(BackupSchedule.created_at.desc()).all()
    connections = {c.id: c.name for c in db.query(PGConnection).all()}

    now = dt.datetime.now()

    for s in schedules:
        if s.is_active and not s.is_paused:
            job = scheduler.get_job(f"backup_{s.id}")
            if job and job.next_run_time:
                s.next_run_at = job.next_run_time
            elif not s.next_run_at:
                if s.schedule_type == "interval" and s.interval_minutes:
                    base = s.last_run_at or s.created_at or now
                    s.next_run_at = base + dt.timedelta(minutes=s.interval_minutes)
                    while s.next_run_at <= now:
                        s.next_run_at += dt.timedelta(minutes=s.interval_minutes)

    db.commit()

    return templates.TemplateResponse(request, "schedules/list.html", {
        "request": request,
        "user": user,
        "schedules": schedules,
        "connections": connections,
    })


@router.get("/new")
def new_schedule(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
    return templates.TemplateResponse(request, "schedules/form.html", {"request": request, "user": user, "connections": connections})


@router.post("/new")
def create_schedule(
    request: Request,
    name: str = Form(...),
    connection_id: str = Form(...),
    schedule_type: str = Form(...),
    interval_minutes: int = Form(None),
    cron_expression: str = Form(None),
    retention_days: int = Form(30),
    storage_local: str = Form("local"),
    storage_gdrive: str = Form(""),
    storage_yandex: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from uuid import uuid4
    import datetime

    if schedule_type == "interval" and not interval_minutes:
        connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
        return templates.TemplateResponse(request, "schedules/form.html", {
            "request": request, "user": user, "connections": connections,
            "error": "Interval minutes is required for interval schedule"
        })

    cron_map = {
        "hourly": "0 * * * *",
        "daily": "0 0 * * *",
        "weekly": "0 0 * * 0",
        "monthly": "0 0 1 * *",
    }

    if schedule_type != "interval" and not cron_expression:
        cron_expression = cron_map.get(schedule_type)

    providers = []
    if storage_local: providers.append("local")
    if storage_gdrive: providers.append("google_drive")
    if storage_yandex: providers.append("yandex")
    storage_provider = ",".join(providers) if providers else "local"

    schedule = BackupSchedule(
        id=str(uuid4()),
        name=name,
        connection_id=connection_id,
        schedule_type=schedule_type,
        interval_minutes=interval_minutes,
        cron_expression=cron_expression,
        retention_days=retention_days,
        storage_provider=storage_provider,
    )
    db.add(schedule)
    db.commit()

    if schedule.is_active and not schedule.is_paused:
        add_schedule_job(schedule)

    log_audit(db, action="schedule_created", user_id=user.id, username=user.username,
              resource_type="schedule", resource_id=schedule.id)

    return RedirectResponse(url="/schedules", status_code=302)


@router.get("/{schedule_id}/edit")
def edit_schedule(schedule_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
    return templates.TemplateResponse(request, "schedules/form.html", {
        "request": request,
        "user": user,
        "schedule": schedule,
        "connections": connections,
    })


@router.post("/{schedule_id}/edit")
def update_schedule(
    schedule_id: str,
    request: Request,
    name: str = Form(...),
    connection_id: str = Form(...),
    schedule_type: str = Form(...),
    interval_minutes: int = Form(None),
    cron_expression: str = Form(None),
    retention_days: int = Form(30),
    storage_local: str = Form("local"),
    storage_gdrive: str = Form(""),
    storage_yandex: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    if schedule_type == "interval" and not interval_minutes:
        connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
        return templates.TemplateResponse(request, "schedules/form.html", {
            "request": request, "user": user, "schedule": schedule, "connections": connections,
            "error": "Interval minutes is required for interval schedule"
        })

    cron_map = {
        "hourly": "0 * * * *",
        "daily": "0 0 * * *",
        "weekly": "0 0 * * 0",
        "monthly": "0 0 1 * *",
    }

    if schedule_type != "interval" and not cron_expression:
        cron_expression = cron_map.get(schedule_type)

    providers = []
    if storage_local: providers.append("local")
    if storage_gdrive: providers.append("google_drive")
    if storage_yandex: providers.append("yandex")
    storage_provider = ",".join(providers) if providers else "local"

    old_active = schedule.is_active and not schedule.is_paused

    schedule.name = name
    schedule.connection_id = connection_id
    schedule.schedule_type = schedule_type
    schedule.interval_minutes = interval_minutes
    schedule.cron_expression = cron_expression
    schedule.retention_days = retention_days
    schedule.storage_provider = storage_provider
    db.commit()

    remove_schedule_job(schedule.id)
    if schedule.is_active and not schedule.is_paused:
        add_schedule_job(schedule)

    log_audit(db, action="schedule_updated", user_id=user.id, username=user.username,
              resource_type="schedule", resource_id=schedule.id)

    return RedirectResponse(url="/schedules", status_code=302)


@router.post("/{schedule_id}/pause")
def pause_schedule(schedule_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.is_paused = True
    db.commit()
    pause_schedule_job(schedule_id)
    log_audit(db, action="schedule_paused", user_id=user.id, username=user.username, resource_type="schedule", resource_id=schedule_id)
    return RedirectResponse(url="/schedules", status_code=302)


@router.post("/{schedule_id}/resume")
def resume_schedule(schedule_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    schedule.is_paused = False
    db.commit()
    resume_schedule_job(schedule_id)
    log_audit(db, action="schedule_resumed", user_id=user.id, username=user.username, resource_type="schedule", resource_id=schedule_id)
    return RedirectResponse(url="/schedules", status_code=302)


@router.post("/{schedule_id}/delete")
def delete_schedule(schedule_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    remove_schedule_job(schedule_id)
    db.delete(schedule)
    db.commit()
    log_audit(db, action="schedule_deleted", user_id=user.id, username=user.username, resource_type="schedule", resource_id=schedule_id)
    return RedirectResponse(url="/schedules", status_code=302)
