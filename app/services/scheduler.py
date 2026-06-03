import datetime
import logging
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.connection import PGConnection
from app.models.schedule import BackupSchedule
from app.services.backup import run_backup
from app.services.notification import notify_backup_completed, notify_backup_failed, notify_backup_started

logger = logging.getLogger("mxvault.scheduler")

scheduler = BackgroundScheduler()
_scheduled_jobs: dict[str, str] = {}


def get_cron_trigger(schedule_type: str) -> str:
    triggers = {
        "hourly": "0 * * * *",
        "daily": "0 0 * * *",
        "weekly": "0 0 * * 0",
        "monthly": "0 0 1 * *",
    }
    return triggers.get(schedule_type, "0 0 * * *")


def add_schedule_job(schedule: BackupSchedule):
    job_id = f"backup_{schedule.id}"

    if schedule.schedule_type == "interval" and schedule.interval_minutes:
        trigger = IntervalTrigger(minutes=schedule.interval_minutes)
    else:
        cron = schedule.cron_expression or get_cron_trigger(schedule.schedule_type)
        trigger = CronTrigger.from_crontab(cron)

    scheduler.add_job(
        func=execute_scheduled_backup,
        trigger=trigger,
        id=job_id,
        args=[schedule.id],
        name=schedule.name,
        replace_existing=True,
    )
    _scheduled_jobs[schedule.id] = job_id
    logger.info(f"Scheduled job '{schedule.name}' with trigger {trigger}")


def remove_schedule_job(schedule_id: str):
    job_id = _scheduled_jobs.pop(schedule_id, None)
    if job_id:
        scheduler.remove_job(job_id)
        logger.info(f"Removed scheduled job {job_id}")


def pause_schedule_job(schedule_id: str):
    job_id = _scheduled_jobs.get(schedule_id)
    if job_id:
        scheduler.pause_job(job_id)


def resume_schedule_job(schedule_id: str):
    job_id = _scheduled_jobs.get(schedule_id)
    if job_id:
        scheduler.resume_job(job_id)


def execute_scheduled_backup(schedule_id: str):
    db = SessionLocal()
    try:
        schedule = db.query(BackupSchedule).filter(BackupSchedule.id == schedule_id).first()
        if not schedule or not schedule.is_active or schedule.is_paused:
            return

        connection = db.query(PGConnection).filter(PGConnection.id == schedule.connection_id).first()
        if not connection or not connection.is_active:
            logger.warning(f"Connection not found or inactive for schedule {schedule.name}")
            return

        logger.info(f"Executing scheduled backup: {schedule.name}")
        schedule.last_run_at = datetime.datetime.now()
        schedule.total_runs += 1

        backup = run_backup(
            db=db,
            connection=connection,
            storage_provider=schedule.storage_provider,
            retention_days=schedule.retention_days,
            triggered_by="schedule",
            schedule_id=schedule.id,
        )

        if backup.status == "completed" or backup.status == "uploaded":
            schedule.successful_runs += 1
            notify_backup_completed(db, backup)
        else:
            schedule.failed_runs += 1
            notify_backup_failed(db, backup)

        db.commit()
    except Exception as e:
        logger.error(f"Scheduled backup failed: {e}")
    finally:
        db.close()


def load_schedules():
    db = SessionLocal()
    try:
        schedules = db.query(BackupSchedule).filter(
            BackupSchedule.is_active == True,
            BackupSchedule.is_paused == False,
        ).all()
        for schedule in schedules:
            add_schedule_job(schedule)
        logger.info(f"Loaded {len(schedules)} schedules")
    finally:
        db.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        load_schedules()
        logger.info("Scheduler started")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
