import json
import os
import shutil
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.storage import StorageProvider
from app.services.storage.base import BaseStorageProvider


class LocalStorageProvider(BaseStorageProvider):
    def name(self) -> str:
        return "local"

    def get_config(self) -> dict:
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "local"
        ).first()
        if provider and provider.config_json:
            return json.loads(provider.config_json)
        return {"backup_dir": settings.backup_dir, "retention_days": settings.default_retention_days}

    def save_config(self, config: dict):
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "local"
        ).first()
        if not provider:
            from uuid import uuid4
            provider = StorageProvider(
                id=str(uuid4()),
                name="Local Storage",
                provider_type="local",
                config_json=json.dumps(config),
                is_configured=True,
            )
            self.db.add(provider)
        else:
            provider.config_json = json.dumps(config)
            provider.is_configured = True
        self.db.commit()

    def is_configured(self) -> bool:
        return True

    def upload(self, filepath: str, filename: str) -> dict:
        if os.path.exists(filepath):
            return {"success": True, "path": filepath}
        return {"success": False, "error": "File not found"}

    def delete(self, path: str) -> bool:
        try:
            if os.path.exists(path):
                os.remove(path)
                return True
            return False
        except OSError:
            return False

    def list_files(self, prefix: str = "") -> list[dict]:
        config = self.get_config()
        backup_dir = config.get("backup_dir", settings.backup_dir)
        files = []
        if os.path.exists(backup_dir):
            for root, dirs, filenames in os.walk(backup_dir):
                for f in filenames:
                    if f.endswith(".dump"):
                        fpath = os.path.join(root, f)
                        stat = os.stat(fpath)
                        files.append({
                            "name": f,
                            "path": fpath,
                            "size_bytes": stat.st_size,
                            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "connection_id": os.path.basename(root),
                        })
        return sorted(files, key=lambda x: x["modified_at"], reverse=True)

    def verify(self, path: str) -> bool:
        return os.path.exists(path)
