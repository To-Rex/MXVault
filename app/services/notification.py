import json
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.backup import BackupLog
from app.models.settings import AppSetting

logger = logging.getLogger("mxvault.notification")


def get_telegram_config(db: Session) -> dict:
    bot_token = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
    chat_id = db.query(AppSetting).filter(AppSetting.key == "telegram_chat_id").first()
    enabled = db.query(AppSetting).filter(AppSetting.key == "telegram_enabled").first()
    return {
        "bot_token": bot_token.value if bot_token else "",
        "chat_id": chat_id.value if chat_id else "",
        "enabled": (enabled.value if enabled else "false").lower() == "true",
    }


def save_telegram_config(db: Session, bot_token: str, chat_id: str, enabled: bool):
    for key, value in [
        ("telegram_bot_token", bot_token),
        ("telegram_chat_id", chat_id),
        ("telegram_enabled", str(enabled).lower()),
    ]:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSetting(id=str(uuid4()), key=key, value=value)
            db.add(setting)
    db.commit()


def send_telegram_message(db: Session, message: str) -> bool:
    config = get_telegram_config(db)
    if not config["enabled"] or not config["bot_token"] or not config["chat_id"]:
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": config["chat_id"],
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        return response.status_code == 200
    except ImportError:
        logger.warning("requests library not installed, cannot send Telegram message")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def notify_backup_started(db: Session, backup: BackupLog):
    message = (
        f"🔄 <b>Backup Started</b>\n"
        f"Database: {backup.database_name}\n"
        f"Connection: {backup.connection_name}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Destination: {backup.destination}"
    )
    send_telegram_message(db, message)


def notify_backup_completed(db: Session, backup: BackupLog):
    size_mb = backup.file_size_bytes / (1024 * 1024) if backup.file_size_bytes else 0
    message = (
        f"✅ <b>Backup Completed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Size: {size_mb:.2f} MB\n"
        f"Duration: {backup.duration_seconds:.1f}s\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Status: Success"
    )
    send_telegram_message(db, message)


def notify_backup_failed(db: Session, backup: BackupLog):
    message = (
        f"❌ <b>Backup Failed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Connection: {backup.connection_name}\n"
        f"Error: {backup.error_message or 'Unknown'}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)


def notify_upload_completed(db: Session, backup: BackupLog, provider: str):
    size_mb = backup.file_size_bytes / (1024 * 1024) if backup.file_size_bytes else 0
    message = (
        f"📤 <b>Upload Completed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Size: {size_mb:.2f} MB\n"
        f"Destination: {provider}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)


def notify_upload_failed(db: Session, backup: BackupLog, provider: str):
    message = (
        f"⚠️ <b>Upload Failed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Destination: {provider}\n"
        f"Error: {backup.error_message or 'Unknown'}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
