import datetime
import os
import subprocess
import tempfile
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.connection import PGConnection
from app.models.user import User
from app.services.audit import log_audit
from app.services.storage.base import get_storage_provider
from app.utils.crypto import decrypt_password
from app.templates import templates

router = APIRouter(prefix="/restore", tags=["restore"])


def _resolve_backup_file(backup: BackupLog, db: Session) -> str | None:
    path = (backup.destination_path or "").strip()

    if path and os.path.exists(path):
        return path

    if path and "yandex://" in path:
        provider = get_storage_provider("yandex", db)
        if provider and provider.is_configured():
            tmp = tempfile.mktemp(suffix=".dump")
            if provider.download(path, tmp):
                return tmp

    if path and "google_drive://" in path:
        provider = get_storage_provider("google_drive", db)
        if provider and provider.is_configured():
            tmp = tempfile.mktemp(suffix=".dump")
            if provider.download(path, tmp):
                return tmp

    local_dir = os.path.join(settings.backup_dir, backup.connection_id)
    if backup.filename:
        local_path = os.path.join(local_dir, backup.filename)
        if os.path.exists(local_path):
            return local_path

    return None


def _do_restore(db: Session, user: User, local_path: str, is_temp: bool, filename: str, connection: PGConnection, conn_name: str) -> dict:
    password = decrypt_password(connection.encrypted_password)
    log_output = []
    start_time = time.time()

    log_output.append(f"Starting restore of {filename} to {connection.database} at {datetime.datetime.now().isoformat()}")
    if is_temp:
        log_output.append("Using temporary file for restore")

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    pg_restore_cmd = [
        settings.pg_restore_path,
        "-h", connection.host,
        "-p", str(connection.port),
        "-U", connection.username,
        "-d", connection.database,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        local_path,
    ]

    log_output.append(f"Running: {' '.join(pg_restore_cmd)}")

    result = subprocess.run(
        pg_restore_cmd,
        capture_output=True,
        text=True,
        timeout=int(settings.backup_timeout_minutes * 60),
        env=env,
    )

    duration = time.time() - start_time

    if result.returncode == 0:
        log_output.append(f"Restore completed successfully in {duration:.2f}s")
        log_audit(db, action="restore_completed", user_id=user.id, username=user.username,
                  resource_type="restore", details=f"Restored {filename} to {conn_name}")
        return {"success": True, "log": "\n".join(log_output), "duration": round(duration, 2)}
    else:
        log_output.append(f"Restore failed: {result.stderr}")
        log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                  resource_type="restore", status="failed", details=result.stderr)
        return {"success": False, "log": "\n".join(log_output), "error": result.stderr}


@router.get("")
def restore_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
    local_backups = db.query(BackupLog).filter(
        BackupLog.status.in_(["completed", "uploaded"]),
        BackupLog.filename.isnot(None),
    ).order_by(BackupLog.created_at.desc()).limit(100).all()

    return templates.TemplateResponse(request, "restore/index.html", {
        "request": request,
        "user": user,
        "connections": connections,
        "backups": local_backups,
    })


@router.post("/run")
async def run_restore(
    request: Request,
    backup_id: str = Form(""),
    upload_file: UploadFile | None = File(None),
    target_connection_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    connection = db.query(PGConnection).filter(PGConnection.id == target_connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Target connection not found")

    is_temp = False
    local_path = None
    filename = "unknown"

    if upload_file and upload_file.filename:
        tmp = tempfile.mktemp(suffix=".dump")
        try:
            contents = await upload_file.read()
            with open(tmp, "wb") as f:
                f.write(contents)
            local_path = tmp
            filename = upload_file.filename
            is_temp = True
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise HTTPException(status_code=400, detail="Failed to read uploaded file")
    elif backup_id:
        backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
        if not backup:
            raise HTTPException(status_code=404, detail="Backup not found")
        filename = backup.filename or "unknown"
        local_path = _resolve_backup_file(backup, db)
        if not local_path:
            raise HTTPException(
                status_code=404,
                detail=f"Backup file not found. Expected at: {backup.destination_path or backup.filename or 'unknown'}."
            )
        is_temp = local_path != backup.destination_path
    else:
        raise HTTPException(status_code=400, detail="Please select a backup from history or upload a file.")

    try:
        result = _do_restore(db, user, local_path, is_temp, filename, connection, connection.name)
    except subprocess.TimeoutExpired:
        log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                  resource_type="restore", status="failed", details="Restore timed out")
        return templates.TemplateResponse(request, "restore/result.html", {
            "request": request, "user": user, "success": False,
            "log": "", "error": "Restore timed out",
        })
    except Exception as e:
        log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                  resource_type="restore", status="failed", details=str(e))
        return templates.TemplateResponse(request, "restore/result.html", {
            "request": request, "user": user, "success": False,
            "log": "", "error": str(e),
        })
    finally:
        if is_temp and local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                pass

    return templates.TemplateResponse(request, "restore/result.html", {
        "request": request, "user": user,
        "success": result["success"],
        "log": result.get("log", ""),
        "error": result.get("error"),
        "duration": result.get("duration"),
    })
