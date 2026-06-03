import json
import os
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.storage import StorageProvider
from app.services.storage.base import BaseStorageProvider


class YandexDiskStorageProvider(BaseStorageProvider):
    def name(self) -> str:
        return "yandex"

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
            import requests

            access_token = config["access_token"]
            folder = config.get("folder", "mxvault-backups")
            api_base = "https://cloud-api.yandex.net/v1/disk"

            headers = {"Authorization": f"OAuth {access_token}"}

            remote_path = f"/{folder}/{filename}"
            os.makedirs(f"/{folder}", exist_ok=True)

            url_response = requests.get(
                f"{api_base}/resources/upload",
                headers=headers,
                params={"path": remote_path, "overwrite": "true"},
            )

            if url_response.status_code != 200:
                return {"success": False, "error": f"Failed to get upload URL: {url_response.text}"}

            upload_url = url_response.json().get("href", "")
            if not upload_url:
                return {"success": False, "error": "No upload URL received"}

            with open(filepath, "rb") as f:
                upload_response = requests.put(upload_url, data=f)

            if upload_response.status_code in (200, 201):
                return {"success": True, "path": f"yandex://{remote_path}"}
            else:
                return {"success": False, "error": f"Upload failed: {upload_response.text}"}

        except ImportError:
            return {"success": False, "error": "requests library not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete(self, path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            import requests

            remote_path = path.replace("yandex://", "")
            headers = {"Authorization": f"OAuth {config['access_token']}"}
            response = requests.delete(
                "https://cloud-api.yandex.net/v1/disk/resources",
                headers=headers,
                params={"path": remote_path, "permanently": "true"},
            )
            return response.status_code == 204
        except Exception:
            return False

    def list_files(self, prefix: str = "") -> list[dict]:
        config = self.get_config()
        if not config.get("access_token"):
            return []
        try:
            import requests

            headers = {"Authorization": f"OAuth {config['access_token']}"}
            response = requests.get(
                "https://cloud-api.yandex.net/v1/disk/resources",
                headers=headers,
                params={"path": f"/{config.get('folder', 'mxvault-backups')}", "limit": 100},
            )

            if response.status_code == 200:
                items = response.json().get("_embedded", {}).get("items", [])
                return [
                    {
                        "name": item["name"],
                        "path": f"yandex://{item['path']}",
                        "size_bytes": item.get("size", 0),
                        "modified_at": item.get("modified", ""),
                    }
                    for item in items
                    if item["type"] == "file" and item["name"].endswith(".dump")
                ]
            return []
        except Exception:
            return []

    def verify(self, path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            import requests

            remote_path = path.replace("yandex://", "")
            headers = {"Authorization": f"OAuth {config['access_token']}"}
            response = requests.get(
                "https://cloud-api.yandex.net/v1/disk/resources",
                headers=headers,
                params={"path": remote_path},
            )
            return response.status_code == 200
        except Exception:
            return False
