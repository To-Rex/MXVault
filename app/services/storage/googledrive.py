import json
import os
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.storage import StorageProvider
from app.services.storage.base import BaseStorageProvider


class GoogleDriveStorageProvider(BaseStorageProvider):
    def name(self) -> str:
        return "google_drive"

    def get_config(self) -> dict:
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "google_drive"
        ).first()
        if provider and provider.config_json:
            return json.loads(provider.config_json)
        return {}

    def save_config(self, config: dict):
        provider = self.db.query(StorageProvider).filter(
            StorageProvider.provider_type == "google_drive"
        ).first()
        if not provider:
            provider = StorageProvider(
                id=str(uuid4()),
                name="Google Drive",
                provider_type="google_drive",
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
            return {"success": False, "error": "Google Drive not configured"}

        try:
            import requests

            access_token = config["access_token"]
            folder_id = config.get("folder_id", "root")

            headers = {"Authorization": f"Bearer {access_token}"}

            metadata = {
                "name": filename,
                "parents": [folder_id] if folder_id != "root" else [],
            }

            files = {
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file": (filename, open(filepath, "rb"), "application/gzip"),
            }

            response = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers=headers,
                files=files,
            )

            if response.status_code in (200, 201):
                file_id = response.json().get("id", "")
                return {"success": True, "path": f"google_drive://{file_id}/{filename}"}
            else:
                return {"success": False, "error": f"Upload failed: {response.text}"}

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

            file_id = path.replace("google_drive://", "").split("/")[0]
            headers = {"Authorization": f"Bearer {config['access_token']}"}
            response = requests.delete(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
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

            headers = {"Authorization": f"Bearer {config['access_token']}"}
            folder_id = config.get("folder_id", "root")
            query = f"'{folder_id}' in parents and name contains '.dump'"

            response = requests.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={"q": query, "orderBy": "modifiedTime desc"},
            )

            if response.status_code == 200:
                files = response.json().get("files", [])
                return [
                    {
                        "name": f["name"],
                        "path": f"google_drive://{f['id']}/{f['name']}",
                        "size_bytes": int(f.get("size", 0)),
                        "modified_at": f.get("modifiedTime", ""),
                        "file_id": f["id"],
                    }
                    for f in files
                ]
            return []
        except Exception:
            return []

    def download(self, path: str, dest_path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            import requests

            file_id = path.replace("google_drive://", "").split("/")[0]
            headers = {"Authorization": f"Bearer {config['access_token']}"}
            response = requests.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
                headers=headers,
                stream=True,
            )
            if response.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return os.path.exists(dest_path)
            return False
        except Exception:
            return False

    def verify(self, path: str) -> bool:
        config = self.get_config()
        if not config.get("access_token"):
            return False
        try:
            import requests

            file_id = path.replace("google_drive://", "").split("/")[0]
            headers = {"Authorization": f"Bearer {config['access_token']}"}
            response = requests.head(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
            )
            return response.status_code == 200
        except Exception:
            return False
