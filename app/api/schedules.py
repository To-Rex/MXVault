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
    schedules = db.query(BackupSchedule).order_by(BackupSchedule.created_at.desc()).all()
    connections = {c.id: c.name for c in db.query(PGConnection).all()}
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
    storage_provider: str = Form("local"),
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
