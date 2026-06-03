from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_admin_user, get_current_user
from app.models.user import User
from app.services.audit import log_audit
from app.services.notification import (
    delete_email_account,
    get_email_config,
    get_telegram_config,
    save_email_account,
    save_telegram_config,
)
from app.templates import templates

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def settings_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.settings import AppSetting
    from app.services.storage.local import LocalStorageProvider
    from app.models.storage import StorageProvider

    telegram_config = get_telegram_config(db)
    email_config = get_email_config(db)
    # Decrypt passwords for display
    from app.utils.crypto import decrypt_password
    for acc in email_config.get("accounts", []):
        try:
            acc["smtp_pass"] = decrypt_password(acc.get("encrypted_pass", ""))
        except Exception:
            acc["smtp_pass"] = ""

    local_provider = LocalStorageProvider(db)
    local_config = local_provider.get_config()

    gdrive_provider_db = db.query(StorageProvider).filter(
        StorageProvider.provider_type == "google_drive"
    ).first()
    gdrive_config = {}
    if gdrive_provider_db and gdrive_provider_db.config_json:
        import json
        gdrive_config = json.loads(gdrive_provider_db.config_json)

    yandex_provider_db = db.query(StorageProvider).filter(
        StorageProvider.provider_type == "yandex"
    ).first()
    yandex_config = {}
    if yandex_provider_db and yandex_provider_db.config_json:
        import json
        yandex_config = json.loads(yandex_provider_db.config_json)

    users = db.query(User).all() if user.is_admin else []

    return templates.TemplateResponse(request, "settings/index.html", {
        "request": request,
        "user": user,
        "telegram": telegram_config,
        "email": email_config,
        "local_config": local_config,
        "gdrive_config": gdrive_config,
        "yandex_config": yandex_config,
        "users": users,
    })


@router.post("/telegram")
def update_telegram(
    bot_token: str = Form(""),
    chat_id: str = Form(""),
    enabled: bool = Form(False),
    send_file: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    save_telegram_config(db, bot_token, chat_id, enabled, send_file)
    log_audit(db, action="settings_telegram_updated", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/email/add")
def add_email_account(
    name: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    from_addr: str = Form(""),
    to_addresses: str = Form(""),
    enabled: bool = Form(False),
    use_tls: bool = Form(True),
    send_file: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    save_email_account(db, None, name, smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, to_addresses, enabled, use_tls, send_file)
    log_audit(db, action="settings_email_added", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/email/update")
def update_email_account(
    account_id: str = Form(...),
    name: str = Form(""),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    from_addr: str = Form(""),
    to_addresses: str = Form(""),
    enabled: bool = Form(False),
    use_tls: bool = Form(True),
    send_file: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    save_email_account(db, account_id, name, smtp_host, smtp_port, smtp_user, smtp_pass, from_addr, to_addresses, enabled, use_tls, send_file)
    log_audit(db, action="settings_email_updated", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/email/delete")
def delete_email_account_route(
    account_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delete_email_account(db, account_id)
    log_audit(db, action="settings_email_deleted", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/local-storage")
def update_local_storage(
    backup_dir: str = Form(...),
    retention_days: int = Form(30),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.storage.local import LocalStorageProvider
    provider = LocalStorageProvider(db)
    provider.save_config({"backup_dir": backup_dir, "retention_days": retention_days})
    log_audit(db, action="settings_local_storage_updated", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/google-drive")
def update_google_drive(
    access_token: str = Form(""),
    refresh_token: str = Form(""),
    folder_id: str = Form("root"),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.storage.googledrive import GoogleDriveStorageProvider
    provider = GoogleDriveStorageProvider(db)
    provider.save_config({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "folder_id": folder_id,
        "enabled": enabled,
    })
    log_audit(db, action="settings_google_drive_updated", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)


@router.post("/yandex")
def update_yandex(
    access_token: str = Form(""),
    folder: str = Form("mxvault-backups"),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.storage.yandex import YandexDiskStorageProvider
    provider = YandexDiskStorageProvider(db)
    provider.save_config({
        "access_token": access_token,
        "folder": folder,
        "enabled": enabled,
    })
    log_audit(db, action="settings_yandex_updated", user_id=user.id, username=user.username)
    return RedirectResponse(url="/settings", status_code=302)
