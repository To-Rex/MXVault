from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    connection_id: str = Field(..., min_length=1)
    schedule_type: str = Field(..., pattern=r"^(interval|hourly|daily|weekly|monthly)$")
    interval_minutes: Optional[int] = Field(None, ge=1)
    cron_expression: Optional[str] = None
    retention_days: int = Field(default=30, ge=1)
    storage_provider: str = Field(default="local")

    @field_validator("interval_minutes")
    @classmethod
    def interval_required(cls, v, info):
        if info.data.get("schedule_type") == "interval" and v is None:
            raise ValueError("interval_minutes is required for interval schedule")
        return v

    @field_validator("cron_expression")
    @classmethod
    def cron_required(cls, v, info):
        st = info.data.get("schedule_type")
        if st in ("hourly", "daily", "weekly", "monthly") and v is None:
            if st == "hourly":
                return "0 * * * *"
            elif st == "daily":
                return "0 0 * * *"
            elif st == "weekly":
                return "0 0 * * 0"
            elif st == "monthly":
                return "0 0 1 * *"
        return v


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    schedule_type: Optional[str] = Field(None, pattern=r"^(interval|hourly|daily|weekly|monthly)$")
    interval_minutes: Optional[int] = Field(None, ge=1)
    cron_expression: Optional[str] = None
    retention_days: Optional[int] = Field(None, ge=1)
    storage_provider: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduleResponse(BaseModel):
    id: str
    name: str
    connection_id: str
    schedule_type: str
    interval_minutes: Optional[int] = None
    cron_expression: Optional[str] = None
    retention_days: int
    storage_provider: str
    is_active: bool
    is_paused: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    total_runs: int
    successful_runs: int
    failed_runs: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
