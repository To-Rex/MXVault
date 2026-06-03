import datetime
import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.connection import PGConnection
from app.models.schedule import BackupSchedule
from app.models.user import User
from app.templates import templates

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    total_databases = db.query(PGConnection).count()
    total_backups = db.query(BackupLog).count()
    successful_backups = db.query(BackupLog).filter(BackupLog.status.in_(["completed", "uploaded"])).count()
    failed_backups = db.query(BackupLog).filter(BackupLog.status == "failed").count()
    running_backups = db.query(BackupLog).filter(BackupLog.status == "running").count()

    total_backup_size = db.query(BackupLog.file_size_bytes).filter(
        BackupLog.file_size_bytes.isnot(None)
    ).all()
    storage_usage = sum(b[0] for b in total_backup_size if b[0])

    last_backup = db.query(BackupLog).filter(
        BackupLog.status.in_(["completed", "uploaded"])
    ).order_by(BackupLog.created_at.desc()).first()

    next_schedule = db.query(BackupSchedule).filter(
        BackupSchedule.is_active == True,
        BackupSchedule.is_paused == False,
    ).order_by(BackupSchedule.next_run_at.asc()).first()

    recent_backups = db.query(BackupLog).order_by(BackupLog.created_at.desc()).limit(5).all()

    schedules = db.query(BackupSchedule).filter(
        BackupSchedule.is_active == True,
        BackupSchedule.is_paused == False,
    ).all()

    return templates.TemplateResponse(request, "dashboard/index.html", {
        "request": request,
        "user": user,
        "stats": {
            "total_databases": total_databases,
            "total_backups": total_backups,
            "successful_backups": successful_backups,
            "failed_backups": failed_backups,
            "running_backups": running_backups,
            "storage_usage": storage_usage,
            "storage_usage_mb": round(storage_usage / (1024 * 1024), 2),
            "storage_usage_gb": round(storage_usage / (1024 * 1024 * 1024), 2),
            "last_backup": last_backup.created_at.isoformat() if last_backup else None,
            "last_backup_name": last_backup.database_name if last_backup else None,
            "next_schedule": next_schedule.next_run_at.isoformat() if next_schedule and next_schedule.next_run_at else None,
            "next_schedule_name": next_schedule.name if next_schedule else None,
        },
        "recent_backups": recent_backups,
        "schedules": schedules,
    })
