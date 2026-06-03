import datetime
import os
import re
import subprocess
import time
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.models.backup import BackupLog
from app.models.connection import PGConnection
from app.utils.crypto import decrypt_password


def run_backup(
    db: Session,
    connection: PGConnection,
    storage_provider: str = "local",
    retention_days: int = 30,
    triggered_by: str = "manual",
    schedule_id: str | None = None,
) -> BackupLog:
    password = decrypt_password(connection.encrypted_password)
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")
    filename = f"{connection.database}_{timestamp}.dump"
    backup_dir = os.path.join(settings.backup_dir, connection.id)
    os.makedirs(backup_dir, exist_ok=True)
    filepath = os.path.join(backup_dir, filename)

    backup_log = BackupLog(
        id=str(uuid4()),
        connection_id=connection.id,
        connection_name=connection.name,
        database_name=connection.database,
        filename=filename,
        status="running",
        destination=storage_provider,
        destination_path=filepath,
        triggered_by=triggered_by,
        schedule_id=schedule_id,
    )
    db.add(backup_log)
    db.commit()

    start_time = time.time()
    log_lines = []

    try:
        clean_host = re.sub(r'^https?://', '', connection.host).rstrip('/')
        pg_dump_cmd = [
            settings.pg_dump_path,
            "-Fc",
            "-h", clean_host,
            "-p", str(connection.port),
            "-U", connection.username,
            "-d", connection.database,
            "--no-owner",
            "--no-acl",
            "-f", filepath,
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = password
        if connection.ssl_mode != "disable":
            env["PGSSLMODE"] = connection.ssl_mode

        log_lines.append(f"Starting backup of {connection.database} at {datetime.datetime.now().isoformat()}")
        log_lines.append(f"Command: {' '.join(pg_dump_cmd)}")

        result = subprocess.run(
            pg_dump_cmd,
            capture_output=True,
            text=True,
            timeout=int(settings.backup_timeout_minutes * 60),
            env=env,
        )

        duration = time.time() - start_time

        if result.returncode == 0:
            file_size = os.path.getsize(filepath)
            log_lines.append(f"Backup completed successfully")
            log_lines.append(f"Duration: {duration:.2f}s")
            log_lines.append(f"Size: {file_size} bytes")
            if result.stderr:
                log_lines.append(f"pg_dump warnings: {result.stderr.strip()}")

            backup_log.status = "completed"
            backup_log.file_size_bytes = file_size
            backup_log.duration_seconds = round(duration, 2)
            backup_log.log_output = "\n".join(log_lines)
            backup_log.completed_at = datetime.datetime.now()
            connection.last_backup_at = datetime.datetime.now()

            if storage_provider != "local":
                _upload_to_provider(db, backup_log, connection, storage_provider, filepath)
        else:
            error_msg = result.stderr.strip() or "Unknown error"
            log_lines.append(f"Backup failed: {error_msg}")
            backup_log.status = "failed"
            backup_log.error_message = error_msg
            backup_log.log_output = "\n".join(log_lines)
            backup_log.completed_at = datetime.datetime.now()
            if os.path.exists(filepath):
                os.remove(filepath)

        db.commit()
        db.refresh(backup_log)
        _cleanup_old_backups(db, connection.id, retention_days, backup_dir)

    except Exception as e:
        duration = time.time() - start_time
        backup_log.status = "failed"
        backup_log.error_message = str(e)
        backup_log.log_output = "\n".join(log_lines + [f"Exception: {str(e)}"])
        backup_log.completed_at = datetime.datetime.now()
        backup_log.duration_seconds = round(duration, 2)
        db.commit()
        if os.path.exists(filepath):
            os.remove(filepath)

    return backup_log


def _upload_to_provider(db: Session, backup_log: BackupLog, connection: PGConnection, provider: str, filepath: str):
    from app.services.storage.base import get_storage_provider

    try:
        storage = get_storage_provider(provider, db)
        if storage and storage.is_configured():
            result = storage.upload(filepath, backup_log.filename)
            if result["success"]:
                backup_log.destination_path = result.get("path", filepath)
                backup_log.status = "uploaded"
            else:
                backup_log.status = "upload_failed"
                backup_log.error_message = result.get("error", "Upload failed")
    except Exception as e:
        backup_log.status = "upload_failed"
        backup_log.error_message = str(e)


def _cleanup_old_backups(db: Session, connection_id: str, retention_days: int, backup_dir: str):
    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    old_backups = db.query(BackupLog).filter(
        BackupLog.connection_id == connection_id,
        BackupLog.created_at < cutoff,
        BackupLog.status.in_(["completed", "uploaded"]),
    ).all()

    for backup in old_backups:
        if backup.destination_path and os.path.exists(backup.destination_path):
            try:
                os.remove(backup.destination_path)
            except OSError:
                pass

    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            fpath = os.path.join(backup_dir, f)
            if os.path.isfile(fpath):
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fpath))
                if mtime < cutoff:
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass


def get_backup_logs(
    db: Session,
    connection_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[BackupLog], int]:
    query = db.query(BackupLog)
    if connection_id:
        query = query.filter(BackupLog.connection_id == connection_id)
    if status:
        query = query.filter(BackupLog.status == status)
    if search:
        query = query.filter(
            BackupLog.database_name.contains(search) | BackupLog.connection_name.contains(search)
        )
    total = query.count()
    items = query.order_by(BackupLog.created_at.desc()).offset(offset).limit(limit).all()
    return items, total
