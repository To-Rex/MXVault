import os
import shutil
import subprocess
import tempfile

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.backup import BackupLog
from app.models.user import User
from app.templates import templates

router = APIRouter(prefix="/inspect", tags=["inspect"])


def _build_context(db, user, **extra):
    backups = db.query(BackupLog).filter(
        BackupLog.status.in_(["completed", "uploaded"]),
        BackupLog.filename.isnot(None),
    ).order_by(BackupLog.created_at.desc()).limit(100).all()
    return {"request": extra.pop("request", None), "user": user, "backups": backups, **extra}


def _parse_pg_restore_list(output: str) -> list[dict]:
    tables = []
    data_entries = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        parts = line.split(";", 1)
        if len(parts) < 2:
            continue
        body = parts[1].strip().split()
        if len(body) < 5:
            continue

        desc = body[2:]

        if desc[0].upper() == "TABLE" and len(desc) > 1 and desc[1].upper() == "DATA":
            if len(desc) >= 4:
                schema = desc[2]
                name = desc[3]
                data_entries.add(f"{schema}.{name}")
        elif desc[0].upper() == "TABLE":
            if len(desc) >= 3:
                schema = desc[1]
                name = desc[2]
                tables.append({
                    "name": name,
                    "schema": schema,
                    "full_name": f"{schema}.{name}" if schema != "public" else name,
                    "has_data": False,
                })

    for t in tables:
        t["has_data"] = t["full_name"] in data_entries or f"{t['schema']}.{t['name']}" in data_entries

    return tables


def _run_pg_restore_list(filepath: str) -> dict:
    if not shutil.which(settings.pg_restore_path):
        return {"ok": False, "error": f"pg_restore ('{settings.pg_restore_path}') not found. Install PostgreSQL client tools."}
    try:
        result = subprocess.run(
            [settings.pg_restore_path, "-l", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            err = result.stderr.strip() or "Unknown error"
            return {"ok": False, "error": f"pg_restore failed: {err}", "raw": result.stdout}
        return {"ok": True, "output": result.stdout}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _run_pg_restore_data(filepath: str, table_name: str) -> dict:
    if not shutil.which(settings.pg_restore_path):
        return {"error": "pg_restore not found. Install PostgreSQL client tools."}
    try:
        result = subprocess.run(
            [settings.pg_restore_path, "--data-only", "--table=" + table_name, "-f", "-", filepath],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or "Error reading data"}

        raw = result.stdout[:500000]
        parsed = _parse_copy_output(raw)
        return {"raw": raw, **parsed}
    except Exception as e:
        return {"error": str(e)}


def _parse_copy_output(sql: str) -> dict:
    import re

    lines = sql.splitlines()
    columns = []
    rows = []

    in_copy = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("COPY ") and "FROM stdin" in stripped:
            m = re.search(r"COPY\s+\S+\s*\(([^)]+)\)", stripped)
            if m:
                columns = [c.strip().strip('"') for c in m.group(1).split(",")]
            in_copy = True
            continue
        if in_copy and stripped == "\\.":
            in_copy = False
            continue
        if in_copy and stripped:
            vals = stripped.split("\t")
            vals = ["" if v == "\\N" else v for v in vals]
            rows.append(vals)

    return {
        "columns": columns,
        "rows": rows[:1000],
        "total_rows": len(rows),
    }


@router.get("")
def inspect_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ctx = _build_context(db, user, request=request)
    return templates.TemplateResponse(request, "inspect/index.html", ctx)


@router.post("/analyze")
async def analyze_dump(
    request: Request,
    upload_file: UploadFile | None = File(None),
    backup_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filepath = None
    is_temp = False
    filename = "unknown"

    if upload_file and upload_file.filename:
        tmp = tempfile.mktemp(suffix=".dump")
        try:
            contents = await upload_file.read()
            with open(tmp, "wb") as f:
                f.write(contents)
            filepath = tmp
            filename = upload_file.filename
            is_temp = True
        except Exception as e:
            if os.path.exists(tmp):
                os.remove(tmp)
            ctx = _build_context(db, user, request=request, error=f"Failed to read uploaded file: {e}")
            return templates.TemplateResponse(request, "inspect/index.html", ctx)
    elif backup_id:
        backup = db.query(BackupLog).filter(BackupLog.id == backup_id).first()
        if not backup:
            ctx = _build_context(db, user, request=request, error="Backup not found.")
            return templates.TemplateResponse(request, "inspect/index.html", ctx)
        filepath = _resolve_backup_file(backup, db)
        if not filepath:
            ctx = _build_context(db, user, request=request, error=f"Backup file not found: {backup.destination_path or backup.filename}")
            return templates.TemplateResponse(request, "inspect/index.html", ctx)
        filename = backup.filename or "unknown"
        is_temp = filepath != (backup.destination_path or "")
    else:
        ctx = _build_context(db, user, request=request, error="Please upload a file or select a backup from history.")
        return templates.TemplateResponse(request, "inspect/index.html", ctx)

    result = _run_pg_restore_list(filepath)

    if not result["ok"]:
        ctx = _build_context(db, user, request=request,
                            filepath=filepath, filename=filename, is_temp=is_temp,
                            error=result["error"], raw_output=result.get("raw", ""))
        return templates.TemplateResponse(request, "inspect/index.html", ctx)

    tables = _parse_pg_restore_list(result["output"])
    ctx = _build_context(db, user, request=request,
                        tables=tables,
                        filepath=filepath, filename=filename, is_temp=is_temp,
                        raw_output=result["output"] if not tables else "")
    return templates.TemplateResponse(request, "inspect/index.html", ctx)


@router.post("/preview")
async def preview_table_data(
    request: Request,
    table_name: str = Form(...),
    filepath: str = Form(...),
    is_temp: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not os.path.exists(filepath):
        ctx = _build_context(db, user, request=request, preview_table=table_name, error="Temporary file expired. Please re-upload.")
        return templates.TemplateResponse(request, "inspect/index.html", ctx)

    sql_data = _run_pg_restore_data(filepath, table_name)
    result = _run_pg_restore_list(filepath)
    tables = _parse_pg_restore_list(result["output"]) if result["ok"] else []
    ctx = _build_context(db, user, request=request, preview_table=table_name,
                         preview_data=sql_data, tables=tables,
                         filepath=filepath, filename=os.path.basename(filepath), is_temp=is_temp)
    return templates.TemplateResponse(request, "inspect/index.html", ctx)


def _resolve_backup_file(backup: BackupLog, db: Session) -> str | None:
    path = (backup.destination_path or "").strip()
    if path and os.path.exists(path):
        return path

    if path and "yandex://" in path:
        from app.services.storage.base import get_storage_provider
        provider = get_storage_provider("yandex", db)
        if provider and provider.is_configured():
            tmp = tempfile.mktemp(suffix=".dump")
            if provider.download(path, tmp):
                return tmp

    if path and "google_drive://" in path:
        from app.services.storage.base import get_storage_provider
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
