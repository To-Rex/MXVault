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
from app.services.connection import test_connection
from app.services.notification import (
    notify_connection_down,
    notify_connection_restored,
)

logger = logging.getLogger("mxvault.scheduler")

scheduler = BackgroundScheduler()
_scheduled_jobs: dict[str, str] = {}
_connection_states: dict[str, bool] = {}
_HEALTH_CHECK_INTERVAL_MINUTES = 5


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
        else:
            schedule.failed_runs += 1

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


def check_connections_health():
    global _connection_states

    db = SessionLocal()
    try:
        connections = db.query(PGConnection).all()
        for conn in connections:
            result = test_connection(conn)
            alive = result.get("success", False)
            conn.last_tested_at = datetime.datetime.now()

            prev_state = _connection_states.get(conn.id)

            if prev_state is None:
                _connection_states[conn.id] = alive
            elif alive and not prev_state:
                logger.info(f"Connection restored: {conn.name}")
                conn.is_active = True
                _connection_states[conn.id] = True
                notify_connection_restored(db, conn.name, conn.host, conn.port, conn.database)
            elif not alive and prev_state:
                logger.warning(f"Connection lost: {conn.name}")
                conn.is_active = False
                _connection_states[conn.id] = False
                notify_connection_down(db, conn.name, conn.host, conn.port, conn.database, result.get("message", "Unknown error"))
            else:
                conn.is_active = alive
                _connection_states[conn.id] = alive

        db.commit()
    except Exception as e:
        logger.error(f"Connection health check failed: {e}")
    finally:
        db.close()


def start_connection_health_check():
    job_id = "connection_health_check"
    if scheduler.get_job(job_id):
        return
    scheduler.add_job(
        func=check_connections_health,
        trigger=IntervalTrigger(minutes=_HEALTH_CHECK_INTERVAL_MINUTES),
        id=job_id,
        name="Connection Health Check",
        replace_existing=True,
    )
    logger.info(f"Connection health check started (every {_HEALTH_CHECK_INTERVAL_MINUTES} min)")


def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        load_schedules()
        start_connection_health_check()
        logger.info("Scheduler started")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
