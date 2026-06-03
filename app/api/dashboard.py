import datetime
import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, case
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

    # Daily backup stats for last 30 days
    thirty_days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
    daily_rows = db.query(
        func.date(BackupLog.created_at).label('date'),
        func.count(BackupLog.id).label('total'),
        func.sum(case((BackupLog.status.in_(["completed", "uploaded"]), 1), else_=0)).label('success'),
        func.sum(case((BackupLog.status == "failed", 1), else_=0)).label('failed'),
    ).filter(
        BackupLog.created_at >= thirty_days_ago
    ).group_by(
        func.date(BackupLog.created_at)
    ).order_by(
        func.date(BackupLog.created_at)
    ).all()

    daily_stats_dict = {}
    for row in daily_rows:
        daily_stats_dict[str(row.date)] = {
            "total": row.total or 0,
            "success": row.success or 0,
            "failed": row.failed or 0,
        }

    daily_stats = []
    for i in range(30):
        date = (datetime.datetime.utcnow() - datetime.timedelta(days=29 - i)).strftime("%Y-%m-%d")
        stats = daily_stats_dict.get(date, {"total": 0, "success": 0, "failed": 0})
        daily_stats.append({"date": date, **stats})

    # Storage per connection
    storage_rows = db.query(
        PGConnection.name,
        func.coalesce(func.sum(BackupLog.file_size_bytes), 0).label('total_size'),
        func.count(BackupLog.id).label('count'),
    ).outerjoin(
        BackupLog, BackupLog.connection_id == PGConnection.id
    ).group_by(
        PGConnection.id, PGConnection.name
    ).having(
        func.sum(BackupLog.file_size_bytes) > 0
    ).all()

    storage_per_connection = [
        {
            "name": row.name,
            "total_size": row.total_size,
            "total_size_mb": round(row.total_size / (1024 * 1024), 2),
            "count": row.count,
        }
        for row in storage_rows
    ]

    # Schedule type distribution
    schedule_rows = db.query(
        BackupSchedule.schedule_type,
        func.count(BackupSchedule.id).label('count'),
    ).filter(
        BackupSchedule.is_active == True,
    ).group_by(
        BackupSchedule.schedule_type
    ).all()

    schedule_types = [
        {"type": row.schedule_type, "count": row.count}
        for row in schedule_rows
    ]

    active_schedules_count = db.query(BackupSchedule).filter(
        BackupSchedule.is_active == True,
        BackupSchedule.is_paused == False,
    ).count()

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
            "success_rate": round((successful_backups / total_backups * 100)) if total_backups > 0 else 0,
            "active_schedules": active_schedules_count,
        },
        "daily_stats": daily_stats,
        "storage_per_connection": storage_per_connection,
        "schedule_types": schedule_types,
        "recent_backups": recent_backups,
        "schedules": schedules,
    })
