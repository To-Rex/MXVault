import os
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
LOG_DIR = DATA_DIR / "logs"


class Settings(BaseSettings):
    app_name: str = "MXVault"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    secret_key: str = "change-me-to-a-random-secret-key"
    encryption_key: str = "change-me-to-a-32-byte-hex-key"
    session_ttl: int = 86400

    database_url: str = f"sqlite:///{DATA_DIR / 'mxvault.db'}"
    database_echo: bool = False

    backup_dir: str = str(BACKUP_DIR)
    log_dir: str = str(LOG_DIR)
    default_retention_days: int = 30
    max_backup_size_mb: int = 10240
    backup_timeout_minutes: int = 60

    pg_dump_path: str = "pg_dump"
    pg_restore_path: str = "pg_restore"
    psql_path: str = "psql"

    google_drive_enabled: bool = False
    yandex_disk_enabled: bool = False
    telegram_enabled: bool = False

    host: str = "0.0.0.0"
    port: int = 8004

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
