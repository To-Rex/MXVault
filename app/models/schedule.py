import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BackupSchedule(Base):
    __tablename__ = "backup_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    schedule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=True)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    storage_provider: Mapped[str] = mapped_column(String(50), default="local")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    last_run_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, default=0)
    successful_runs: Mapped[int] = mapped_column(Integer, default=0)
    failed_runs: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
