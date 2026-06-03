from abc import ABC, abstractmethod

from sqlalchemy.orm import Session


class BaseStorageProvider(ABC):
    def __init__(self, db: Session):
        self.db = db

    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def upload(self, filepath: str, filename: str) -> dict: ...

    @abstractmethod
    def delete(self, path: str) -> bool: ...

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[dict]: ...

    @abstractmethod
    def download(self, path: str, dest_path: str) -> bool:
        """Download a file from remote storage to a local path. Returns True on success."""
        ...

    @abstractmethod
    def verify(self, path: str) -> bool: ...


def get_storage_provider(provider_type: str, db: Session) -> BaseStorageProvider | None:
    if provider_type == "local":
        from app.services.storage.local import LocalStorageProvider
        return LocalStorageProvider(db)
    elif provider_type == "google_drive":
        from app.services.storage.googledrive import GoogleDriveStorageProvider
        return GoogleDriveStorageProvider(db)
    elif provider_type == "yandex":
        from app.services.storage.yandex import YandexDiskStorageProvider
        return YandexDiskStorageProvider(db)
    return None
