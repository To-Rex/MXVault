import datetime
import json
import os
import threading
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.connection import PGConnection
from app.models.user import User
from app.services.audit import log_audit
from app.services.backup import get_backup_logs, get_database_size_estimate, run_backup_async
from app.services.notification import notify_backup_started
from app.templates import templates

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("")
def list_backups(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    connection_id: str = Query(None),
    status: str = Query(None),
    search: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    items, total = get_backup_logs(db, connection_id=connection_id, status=status, search=search, limit=per_page, offset=offset)
    total_pages = max(1, (total + per_page - 1) // per_page)
    connections = db.query(PGConnection).order_by(PGConnection.name).all()

    return templates.TemplateResponse(request, "backups/list.html", {
        "request": request,
        "user": user,
        "backups": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "connections": connections,
        "filter_connection_id": connection_id,
        "filter_status": status,
        "filter_search": search,
    })

@router.post("/bulk-delete")
def bulk_delete_backups(backup_ids: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = [id.strip() for id in backup_ids.split(",") if id.strip()]
    deleted = 0
    for bid in ids:
        backup = db.query(BackupLog).filter(BackupLog.id == bid).first()
        if not backup:
            continue
        if backup.destination_path and os.path.exists(backup.destination_path):
            try:
                os.remove(backup.destination_path)
            except OSError:
                pass
        db.delete(backup)
        log_audit(db, action="backup_deleted", user_id=user.id, username=user.username,
                  resource_type="backup", resource_id=bid)
        deleted += 1
    db.commit()
    return RedirectResponse(url="/backups", status_code=302)


@router.post("/delete-all")
def delete_all_backups(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    connection_id: str = Form(default=""),
    status_filter: str = Form(default=""),
):
    query = db.query(BackupLog)
    if connection_id:
        query = query.filter(BackupLog.connection_id == connection_id)
    if status_filter:
        query = query.filter(BackupLog.status == status_filter)
    backups = query.all()
    count = 0
    for backup in backups:
        if backup.destination_path and os.path.exists(backup.destination_path):
            try:
                os.remove(backup.destination_path)
            except OSError:
                pass
        db.delete(backup)
        log_audit(db, action="backup_deleted", user_id=user.id, username=user.username,
                  resource_type="backup", resource_id=backup.id)
        count += 1
    db.commit()
    return RedirectResponse(url="/backups", status_code=302)


@router.post("/{backup_id}/delete")
def delete_backup(backup_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.destination_path and os.path.exists(backup.destination_path):
        try:
            os.remove(backup.destination_path)
        except OSError:
            pass

    db.delete(backup)
    db.commit()
    log_audit(db, action="backup_deleted", user_id=user.id, username=user.username,
              resource_type="backup", resource_id=backup_id)
    return RedirectResponse(url="/backups", status_code=302)


@router.post("/run")
def run_backup_route(
    request: Request,
    connection_id: str = Form(...),
    storage_provider: str = Form("local,google_drive,yandex"),
    retention_days: int = Form(30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    connection = db.query(PGConnection).filter(PGConnection.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

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
        triggered_by="manual",
    )
    db.add(backup_log)
    db.commit()

    notify_backup_started(db, backup_log)

    log_audit(db, action="backup_run", user_id=user.id, username=user.username,
              resource_type="backup", resource_id=backup_log.id,
              details=f"Backup of '{connection.name}' - status: started")

    estimated_size = get_database_size_estimate(connection)

    connection.last_backup_at = datetime.datetime.now()
    db.commit()

    threading.Thread(
        target=run_backup_async,
        args=(backup_log.id, connection.id, storage_provider, retention_days),
        daemon=True,
    ).start()

    return JSONResponse({
        "backup_id": backup_log.id,
        "status": "running",
        "estimated_size_bytes": estimated_size,
    })


@router.get("/status/{backup_id}")
def get_backup_status(backup_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    current_size = 0
    if backup.destination_path and os.path.exists(backup.destination_path):
        current_size = os.path.getsize(backup.destination_path)

    return {
        "backup_id": backup.id,
        "status": backup.status,
        "file_size_bytes": current_size,
        "duration_seconds": backup.duration_seconds,
        "error_message": backup.error_message,
        "completed_at": backup.completed_at.isoformat() if backup.completed_at else None,
    }


@router.get("/{backup_id}")
def view_backup(backup_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    return templates.TemplateResponse(request, "backups/view.html", {"request": request, "user": user, "backup": backup})
