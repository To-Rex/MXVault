"""Initial migration

Revision ID: 001
Revises:
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_admin", sa.Boolean, default=False),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token", sa.String(512), unique=True, nullable=False, index=True),
        sa.Column("user_id", sa.String(36), nullable=False, index=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("last_accessed_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "pg_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, default=5432),
        sa.Column("database", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_password", sa.Text, nullable=False),
        sa.Column("ssl_mode", sa.String(50), default="prefer"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("last_tested_at", sa.DateTime, nullable=True),
        sa.Column("last_backup_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "backup_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False, index=True),
        sa.Column("connection_name", sa.String(255), nullable=True),
        sa.Column("database_name", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(512), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("destination", sa.String(100), nullable=True),
        sa.Column("destination_path", sa.String(1024), nullable=True),
        sa.Column("log_output", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("schedule_id", sa.String(36), nullable=True),
        sa.Column("triggered_by", sa.String(50), default="manual"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "backup_schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("connection_id", sa.String(36), nullable=False, index=True),
        sa.Column("schedule_type", sa.String(50), nullable=False),
        sa.Column("interval_minutes", sa.Integer, nullable=True),
        sa.Column("cron_expression", sa.String(100), nullable=True),
        sa.Column("retention_days", sa.Integer, default=30),
        sa.Column("storage_provider", sa.String(50), default="local"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("is_paused", sa.Boolean, default=False),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("next_run_at", sa.DateTime, nullable=True),
        sa.Column("total_runs", sa.Integer, default=0),
        sa.Column("successful_runs", sa.Integer, default=0),
        sa.Column("failed_runs", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "storage_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("is_configured", sa.Boolean, default=False),
        sa.Column("is_enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("action", sa.String(255), nullable=False, index=True),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(36), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), default="success"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("app_settings")
    op.drop_table("storage_providers")
    op.drop_table("backup_schedules")
    op.drop_table("backup_logs")
    op.drop_table("pg_connections")
    op.drop_table("sessions")
    op.drop_table("users")
