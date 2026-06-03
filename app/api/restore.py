import datetime
import os
import subprocess
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.connection import PGConnection
from app.models.user import User
from app.services.audit import log_audit
from app.utils.crypto import decrypt_password
from app.templates import templates

router = APIRouter(prefix="/restore", tags=["restore"])


@router.get("")
def restore_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    connections = db.query(PGConnection).filter(PGConnection.is_active == True).all()
    local_backups = db.query(BackupLog).filter(
        BackupLog.status.in_(["completed", "uploaded"]),
        BackupLog.filename.isnot(None),
    ).order_by(BackupLog.created_at.desc()).limit(50).all()

    return templates.TemplateResponse(request, "restore/index.html", {
        "request": request,
        "user": user,
        "connections": connections,
        "backups": local_backups,
    })


@router.post("/run")
def run_restore(
    request: Request,
    backup_id: str = Form(...),
    target_connection_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    connection = db.query(PGConnection).filter(PGConnection.id == target_connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Target connection not found")

    if not backup.destination_path or not os.path.exists(backup.destination_path):
        raise HTTPException(status_code=404, detail="Backup file not found on disk")

    password = decrypt_password(connection.encrypted_password)
    log_output = []
    start_time = time.time()

    try:
        log_output.append(f"Starting restore of {backup.filename} to {connection.database} at {datetime.datetime.now().isoformat()}")

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
            backup.destination_path,
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
                      resource_type="restore", details=f"Restored {backup.filename} to {connection.name}")
            from fastapi.templating import Jinja2Templates
            templates = Jinja2Templates(directory="app/templates")
            return templates.TemplateResponse(request, "restore/result.html", {
                "request": request, "user": user, "success": True,
                "log": "\n".join(log_output), "duration": round(duration, 2),
            })
        else:
            log_output.append(f"Restore failed: {result.stderr}")
            log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                      resource_type="restore", status="failed", details=result.stderr)
            from fastapi.templating import Jinja2Templates
            templates = Jinja2Templates(directory="app/templates")
            return templates.TemplateResponse(request, "restore/result.html", {
                "request": request, "user": user, "success": False,
                "log": "\n".join(log_output), "error": result.stderr,
            })

    except subprocess.TimeoutExpired:
        log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                  resource_type="restore", status="failed", details="Restore timed out")
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="app/templates")
        return templates.TemplateResponse(request, "restore/result.html", {
            "request": request, "user": user, "success": False,
            "log": "\n".join(log_output), "error": "Restore timed out",
        })
    except Exception as e:
        log_audit(db, action="restore_failed", user_id=user.id, username=user.username,
                  resource_type="restore", status="failed", details=str(e))
        from fastapi.templating import Jinja2Templates
        templates = Jinja2Templates(directory="app/templates")
        return templates.TemplateResponse(request, "restore/result.html", {
            "request": request, "user": user, "success": False,
            "log": "\n".join(log_output), "error": str(e),
        })
