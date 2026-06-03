from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PGConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1)
    ssl_mode: str = Field(default="prefer")


class PGConnectionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    host: Optional[str] = Field(None, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    database: Optional[str] = Field(None, max_length=255)
    username: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=1)
    ssl_mode: Optional[str] = None
    is_active: Optional[bool] = None


class PGConnectionResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    database: str
    username: str
    ssl_mode: str
    is_active: bool
    last_tested_at: Optional[datetime] = None
    last_backup_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PGConnectionTestResult(BaseModel):
    success: bool
    message: str
    server_version: Optional[str] = None
    latency_ms: Optional[float] = None
