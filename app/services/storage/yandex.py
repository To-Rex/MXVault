import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.storage import StorageProvider
from app.services.storage.base import BaseStorageProvider


class YandexDiskStorageProvider(BaseStorageProvider):
    def name(self) -> str:
        return "yandex"

    def _get_client(self):
        import yadisk

        config = self.get_config()
        token = config.get("access_token", "")
        if not token:
            return None
        return yadisk.YaDisk(token=token)

    def get_config(self) -> dict:
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "yandex"
        ).first()
        if provider and provider.config_json:
            return json.loads(provider.config_json)
        return {}

    def save_config(self, config: dict):
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "yandex"
        ).first()
        if not provider:
            provider = StorageProvider(
                id=str(uuid4()),
                name="Yandex Disk",
                provider_type="yandex",
                config_json=json.dumps(config),
                is_configured=bool(config.get("access_token")),
            )
            self.db.add(provider)
        else:
            provider.config_json = json.dumps(config)
            provider.is_configured = bool(config.get("access_token"))
        self.db.commit()

    def is_configured(self) -> bool:
        config = self.get_config()
        return bool(config.get("access_token"))

    def upload(self, filepath: str, filename: str) -> dict:
        config = self.get_config()
        if not config.get("access_token"):
            return {"success": False, "error": "Yandex Disk not configured"}

        try:
            client = self._get_client()
            if not client:
                return {"success": False, "error": "Failed to create Yandex Disk client"}

            folder = config.get("folder", "mxvault-backups")
            remote_path = f"/{folder}/{filename}"

            client.upload(filepath, remote_path, overwrite=True)

            return {"success": True, "path": f"yandex://{remote_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete(self, path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            client = self._get_client()
            if not client:
                return False
            remote_path = path.replace("yandex://", "")
            client.remove(remote_path, permanently=True)
            return True
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> list[dict]:
        config = self.get_config()
        if not config.get("access_token"):
            return []
        try:
            client = self._get_client()
            if not client:
                return []

            folder = config.get("folder", "mxvault-backups")
            folder_path = f"/{folder}"

            result = []
            for item in client.listdir(folder_path):
                if item.type == "file" and item.name.endswith(".dump"):
                    result.append({
                        "name": item.name,
                        "path": f"yandex://{item.path}",
                        "size_bytes": item.size or 0,
                        "modified_at": item.modified or "",
                    })
            return result
        except Exception:
            return []

    def download(self, path: str, dest_path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            client = self._get_client()
            if not client:
                return False
            remote_path = path.replace("yandex://", "")
            client.download(remote_path, dest_path)
            return os.path.exists(dest_path)
        except Exception:
            return False

    def verify(self, path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            client = self._get_client()
            if not client:
                return False
            remote_path = path.replace("yandex://", "")
            client.get_meta(remote_path)
            return True
        except Exception:
            return False
