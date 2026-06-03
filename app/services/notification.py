import json
import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.backup import BackupLog
from app.models.settings import AppSetting
from app.utils.crypto import decrypt_password, encrypt_password

logger = logging.getLogger("mxvault.notification")


def get_telegram_config(db: Session) -> dict:
    bot_token = db.query(AppSetting).filter(AppSetting.key == "telegram_bot_token").first()
    chat_id = db.query(AppSetting).filter(AppSetting.key == "telegram_chat_id").first()
    enabled = db.query(AppSetting).filter(AppSetting.key == "telegram_enabled").first()
    send_file = db.query(AppSetting).filter(AppSetting.key == "telegram_send_file").first()
    return {
        "bot_token": bot_token.value if bot_token else "",
        "chat_id": chat_id.value if chat_id else "",
        "enabled": (enabled.value if enabled else "false").lower() == "true",
        "send_file": (send_file.value.lower() == "true") if send_file else True,
    }


def save_telegram_config(db: Session, bot_token: str, chat_id: str, enabled: bool, send_file: bool = True):
    for key, value in [
        ("telegram_bot_token", bot_token),
        ("telegram_chat_id", chat_id),
        ("telegram_enabled", str(enabled).lower()),
        ("telegram_send_file", str(send_file).lower()),
    ]:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSetting(id=str(uuid4()), key=key, value=value)
            db.add(setting)
    db.commit()


def _default_email_accounts() -> list[dict]:
    return [{
        "id": str(uuid4()),
        "name": "Default",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "torex.amaki@gmail.com",
        "encrypted_pass": encrypt_password("wlaq qmwv rojp xmie"),
        "from_addr": "torex.amaki@gmail.com",
        "to_addresses": ["dev.dilshodjon@gmail.com"],
        "use_tls": True,
        "enabled": True,
        "send_file": True,
    }]


def get_email_config(db: Session) -> dict:
    setting = db.query(AppSetting).filter(AppSetting.key == "email_accounts").first()
    if not setting or not setting.value:
        accounts = _default_email_accounts()
        setting = AppSetting(id=str(uuid4()), key="email_accounts", value=json.dumps(accounts))
        db.add(setting)
        db.commit()
        return {"accounts": accounts}
    try:
        accounts = json.loads(setting.value)
        return {"accounts": accounts}
    except (json.JSONDecodeError, TypeError):
        return {"accounts": []}


def save_email_account(
    db: Session,
    account_id: str | None,
    name: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_pass: str,
    from_addr: str,
    to_addresses: str,
    enabled: bool,
    use_tls: bool = True,
    send_file: bool = True,
):
    config = get_email_config(db)
    accounts = config["accounts"]

    to_list = [a.strip() for a in to_addresses.replace(",", "\n").split("\n") if a.strip()]

    if account_id:
        for acc in accounts:
            if acc["id"] == account_id:
                acc["name"] = name
                acc["smtp_host"] = smtp_host
                acc["smtp_port"] = smtp_port
                acc["smtp_user"] = smtp_user
                if smtp_pass:
                    acc["encrypted_pass"] = encrypt_password(smtp_pass)
                acc["from_addr"] = from_addr or smtp_user
                acc["to_addresses"] = to_list
                acc["enabled"] = enabled
                acc["use_tls"] = use_tls
                acc["send_file"] = send_file
                break
    else:
        accounts.append({
            "id": str(uuid4()),
            "name": name,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
            "encrypted_pass": encrypt_password(smtp_pass) if smtp_pass else "",
            "from_addr": from_addr or smtp_user,
            "to_addresses": to_list,
            "use_tls": use_tls,
            "enabled": enabled,
            "send_file": send_file,
        })

    setting = db.query(AppSetting).filter(AppSetting.key == "email_accounts").first()
    setting.value = json.dumps(accounts)
    db.commit()


def delete_email_account(db: Session, account_id: str):
    config = get_email_config(db)
    accounts = [a for a in config["accounts"] if a["id"] != account_id]
    setting = db.query(AppSetting).filter(AppSetting.key == "email_accounts").first()
    if setting:
        setting.value = json.dumps(accounts)
        db.commit()


def _send_email_via_account(account: dict, subject: str, body: str, filepath: str | None = None) -> bool:
    if not account.get("enabled") or not account.get("to_addresses"):
        return False

    try:
        import smtplib
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        if filepath:
            import os as _os
            if not _os.path.exists(filepath):
                return False
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "html", "utf-8"))
            with open(filepath, "rb") as f:
                attachment = MIMEApplication(f.read(), _subtype="octet-stream")
                attachment.add_header("Content-Disposition", "attachment", filename=_os.path.basename(filepath))
                msg.attach(attachment)
        else:
            msg = MIMEText(body, "html", "utf-8")

        msg["Subject"] = subject
        msg["From"] = account.get("from_addr") or account["smtp_user"]
        msg["To"] = ", ".join(account["to_addresses"])

        if account.get("use_tls", True):
            server = smtplib.SMTP(account["smtp_host"], account["smtp_port"], timeout=30 if filepath else 15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(account["smtp_host"], account["smtp_port"], timeout=30 if filepath else 15)

        password = decrypt_password(account["encrypted_pass"])
        if account["smtp_user"] and password:
            server.login(account["smtp_user"], password)

        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send email via {account.get('name', 'unknown')}: {e}")
        return False


def send_email_message(db: Session, subject: str, body: str) -> bool:
    config = get_email_config(db)
    any_sent = False
    for account in config.get("accounts", []):
        if _send_email_via_account(account, subject, body):
            any_sent = True
    return any_sent


def send_email_with_attachment(db: Session, subject: str, body: str, filepath: str) -> bool:
    config = get_email_config(db)
    any_sent = False
    for account in config.get("accounts", []):
        if _send_email_via_account(account, subject, body, filepath):
            any_sent = True
    return any_sent


def send_email_with_attachment_for_accounts(db: Session, subject: str, body: str, filepath: str) -> bool:
    config = get_email_config(db)
    any_sent = False
    for account in config.get("accounts", []):
        if account.get("send_file", True):
            if _send_email_via_account(account, subject, body, filepath):
                any_sent = True
    return any_sent


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


def send_telegram_document(db: Session, filepath: str, caption: str = "") -> bool:
    import os as _os

    if not _os.path.exists(filepath):
        return False

    file_size_mb = _os.path.getsize(filepath) / (1024 * 1024)
    if file_size_mb > 50:
        logger.warning(f"Backup file too large for Telegram ({file_size_mb:.1f} MB), skipping upload")
        return False

    config = get_telegram_config(db)
    if not config["enabled"] or not config["bot_token"] or not config["chat_id"]:
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{config['bot_token']}/sendDocument"
        with open(filepath, "rb") as f:
            response = requests.post(
                url,
                data={"chat_id": config["chat_id"], "caption": caption, "parse_mode": "HTML"},
                files={"document": (_os.path.basename(filepath), f)},
                timeout=120,
            )
        return response.status_code == 200
    except ImportError:
        logger.warning("requests library not installed, cannot send Telegram document")
        return False
    except Exception as e:
        logger.error(f"Failed to send Telegram document: {e}")
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
    send_email_message(db, "MXVault: Backup Started", message.replace("\n", "<br>"))


def notify_backup_completed(db: Session, backup: BackupLog, local_filepath: str | None = None):
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
    send_email_message(db, "MXVault: Backup Completed", message.replace("\n", "<br>"))

    tg_config = get_telegram_config(db)
    filepath = local_filepath or backup.destination_path
    if filepath:
        if tg_config["send_file"]:
            send_telegram_document(
                db,
                filepath,
                caption=f"💾 {backup.database_name} — {size_mb:.2f} MB",
            )

        email_config = get_email_config(db)
        any_send_file = any(a.get("send_file", True) for a in email_config.get("accounts", []))
        if any_send_file:
            send_email_with_attachment_for_accounts(
                db,
                "MXVault: Backup File",
                f"Backup of <b>{backup.database_name}</b> — {size_mb:.2f} MB<br>Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                filepath,
            )


def notify_backup_failed(db: Session, backup: BackupLog):
    message = (
        f"❌ <b>Backup Failed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Connection: {backup.connection_name}\n"
        f"Error: {backup.error_message or 'Unknown'}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
    send_email_message(db, "MXVault: Backup Failed", message.replace("\n", "<br>"))


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
    send_email_message(db, "MXVault: Upload Completed", message.replace("\n", "<br>"))


def notify_upload_failed(db: Session, backup: BackupLog, provider: str):
    message = (
        f"⚠️ <b>Upload Failed</b>\n"
        f"Database: {backup.database_name}\n"
        f"Destination: {provider}\n"
        f"Error: {backup.error_message or 'Unknown'}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
    send_email_message(db, "MXVault: Upload Failed", message.replace("\n", "<br>"))


def notify_connection_down(db: Session, name: str, host: str, port: int, database: str, error: str):
    message = (
        f"🔴 <b>Connection Lost</b>\n"
        f"Connection: {name}\n"
        f"Host: {host}:{port}\n"
        f"Database: {database}\n"
        f"Error: {error}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
    send_email_message(db, "MXVault: Connection Lost", message.replace("\n", "<br>"))


def notify_connection_restored(db: Session, name: str, host: str, port: int, database: str):
    message = (
        f"🟢 <b>Connection Restored</b>\n"
        f"Connection: {name}\n"
        f"Host: {host}:{port}\n"
        f"Database: {database}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
    send_email_message(db, "MXVault: Connection Restored", message.replace("\n", "<br>"))


def notify_app_started(db: Session, version: str, host: str, port: int):
    message = (
        f"🚀 <b>MXVault Started</b>\n"
        f"Version: {version}\n"
        f"Host: {host}:{port}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(db, message)
    send_email_message(db, "MXVault: Application Started", message.replace("\n", "<br>"))
