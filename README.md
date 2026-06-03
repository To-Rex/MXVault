<div align="center">
  <br>
  <div>
    <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-teal.svg" alt="FastAPI">
    <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
    <img src="https://img.shields.io/badge/Status-Active-brightgreen.svg" alt="Status">
  </div>
  <br>

  # MXVault

  ### Open Source PostgreSQL Backup Management Platform

  **Simple · Fast · Reliable · Lightweight**

  <br>
</div>

## Overview

MXVault is a self-hosted PostgreSQL backup management platform with a modern web interface. It provides automated backups, scheduling, cloud storage integration (Google Drive, Yandex Disk), and Telegram notifications — all in a single lightweight Python application.

## Features

- **Connection Management** — Manage multiple PostgreSQL connections with encrypted password storage
- **Automated Backups** — Full database backups using native `pg_dump` with gzip compression
- **Flexible Scheduling** — Interval, hourly, daily, weekly, monthly options via APScheduler
- **Local Storage** — Configurable backup directory with retention policies
- **Cloud Integration** — Google Drive and Yandex Disk support
- **Telegram Notifications** — Real-time alerts for backup events
- **Restore Management** — Restore from any local backup with confirmation
- **Modern UI** — Dark/light mode, responsive design, HTMX-powered interactions
- **Audit Logging** — Complete audit trail for all operations
- **Secure** — Password hashing, encryption, session management, CSRF protection

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL client (`pg_dump`, `pg_restore`, `psql`)
- Linux VPS or Dedicated Server

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/mxvault.git
cd mxvault

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the application
python run.py
```

The application will be available at `http://localhost:8000`.

Default credentials: `admin` / `admin123`

### Automated Installation

```bash
# Run as root on your VPS
sudo bash install.sh
```

## Deployment

### systemd Service

A systemd service file is included:

```bash
sudo cp mxvault.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mxvault
sudo systemctl start mxvault
```

### Configuration

Copy `.env.example` to `.env` and configure:

```env
SECRET_KEY=your-random-secret-key
DATABASE_URL=sqlite:///data/mxvault.db
ENCRYPTION_KEY=your-32-byte-hex-key
LOG_LEVEL=INFO
```

## Architecture

```
mxvault/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── database.py          # Database setup
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # Business logic
│   │   └── storage/         # Storage providers
│   ├── api/                 # Route handlers
│   ├── templates/           # Jinja2 templates
│   ├── static/              # Static assets
│   └── utils/               # Utilities
├── migrations/              # Alembic migrations
├── run.py                   # Entry point
└── requirements.txt         # Dependencies
```

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12+, FastAPI |
| Database | SQLAlchemy 2.0 + SQLite / PostgreSQL |
| Frontend | Jinja2, HTMX, Alpine.js, TailwindCSS |
| Scheduler | APScheduler |
| Auth | Session-based with password hashing |
| Storage | Local, Google Drive, Yandex Disk |

## Screenshots

*Screenshots coming soon*

## Roadmap

Future versions will add support for:

- MySQL & MariaDB
- MongoDB
- MinIO & S3
- Cloudflare R2
- Multi-user & multi-tenant
- Backup encryption
- Monitoring & alerts
- Docker deployment

## License

[MIT](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

<div align="center">
  <p>Built with ❤️ for the open source community</p>
</div>
