import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BackupLog(Base):
    __tablename__ = "backup_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    connection_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    connection_name: Mapped[str] = mapped_column(String(255), nullable=True)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    destination: Mapped[str] = mapped_column(String(100), nullable=True)
    destination_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    log_output: Mapped[str] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    schedule_id: Mapped[str] = mapped_column(String(36), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
