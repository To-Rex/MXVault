from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BackupCreate(BaseModel):
    connection_id: str = Field(..., min_length=1)
    storage_provider: str = Field(default="local")
    retention_days: Optional[int] = Field(default=30, ge=1)


class BackupResponse(BaseModel):
    id: str
    connection_id: str
    connection_name: Optional[str] = None
    database_name: str
    filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    duration_seconds: Optional[float] = None
    destination: Optional[str] = None
    destination_path: Optional[str] = None
    log_output: Optional[str] = None
    error_message: Optional[str] = None
    schedule_id: Optional[str] = None
    triggered_by: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BackupListResponse(BaseModel):
    items: list[BackupResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
