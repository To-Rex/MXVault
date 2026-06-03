# Changelog

## 1.0.0 (2026-06-03)

### Initial Release

- PostgreSQL connection management with encrypted password storage
- Full backup engine using native pg_dump with gzip compression
- Background backup execution with progress tracking
- Flexible scheduling with APScheduler (interval, hourly, daily, weekly, monthly)
- Local storage provider with configurable backup directory and retention
- Google Drive integration for cloud backups
- Yandex Disk integration for cloud backups
- Telegram notifications for backup events
- Backup history with pagination, search, and filters
- Restore management from local backups
- Secure authentication with session management
- Modern dark/light mode UI with TailwindCSS, Alpine.js, and HTMX
- Audit logging for all operations
- Settings management for all integrations
- RESTful API with FastAPI
- SQLite (default) and PostgreSQL database support
- systemd service integration
- One-command installation script
- Comprehensive logging
