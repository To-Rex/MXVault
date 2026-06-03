import os

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.user import User
from app.templates import templates

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/local")
def local_storage(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.storage.local import LocalStorageProvider
    provider = LocalStorageProvider(db)
    config = provider.get_config()
    files = provider.list_files()

    return templates.TemplateResponse(request, "storage/local.html", {
        "request": request,
        "user": user,
        "config": config,
        "files": files,
    })


@router.get("/local/download/{backup_id}")
def download_backup(backup_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup or not backup.destination_path:
        raise HTTPException(status_code=404, detail="Backup not found")
    if not os.path.exists(backup.destination_path):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(
        backup.destination_path,
        filename=backup.filename or f"{backup.database_name}.dump",
        media_type="application/octet-stream",
    )


@router.get("/local/file")
def download_file_by_path(filepath: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    filename = os.path.basename(filepath)
    return FileResponse(filepath, filename=filename, media_type="application/gzip")


@router.post("/local/file/delete")
def delete_file_by_path(filepath: str = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.audit import log_audit
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        log_audit(db, action="storage_file_deleted", user_id=user.id, username=user.username,
                  resource_type="file", details=f"Deleted file: {filepath}")
        return RedirectResponse(url="/storage/local", status_code=302)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")


@router.post("/local/delete/{backup_id}")
def delete_backup_file(backup_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.audit import log_audit

    backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if backup.destination_path and os.path.exists(backup.destination_path):
        try:
            os.remove(backup.destination_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")

    db.delete(backup)
    db.commit()
    log_audit(db, action="storage_file_deleted", user_id=user.id, username=user.username,
              resource_type="backup", resource_id=backup_id)
    return RedirectResponse(url="/storage/local", status_code=302)
