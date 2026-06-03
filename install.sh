#!/usr/bin/env bash
set -euo pipefail

MXVERSION="1.0.0"
MXDIR="/opt/mxvault"
MXUSER="mxvault"

echo "================================================"
echo "  MXVault v${MXVERSION} Installation"
echo "  PostgreSQL Backup Management Platform"
echo "================================================"
echo ""

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root" >&2
    exit 1
fi

echo "[1/6] Checking prerequisites..."
for cmd in python3 pip3 git; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: $cmd is required but not installed." >&2
        exit 1
    fi
done

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "  Python version: $PYTHON_VERSION"

if ! command -v pg_dump &>/dev/null; then
    echo "  Warning: pg_dump not found. Install postgresql-client for backup functionality."
fi

echo "[2/6] Creating system user..."
if ! id -u "$MXUSER" &>/dev/null; then
    useradd --system --user-group --home-dir "$MXDIR" --shell /sbin/nologin "$MXUSER"
    echo "  User '$MXUSER' created."
else
    echo "  User '$MXUSER' already exists."
fi

echo "[3/6] Installing application..."
if [ -d "$MXDIR" ]; then
    echo "  Directory $MXDIR already exists. Updating..."
    cp -r . "$MXDIR" 2>/dev/null || true
else
    mkdir -p "$MXDIR"
    cp -r . "$MXDIR"
fi

cd "$MXDIR"

echo "[4/6] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed."

echo "[5/6] Configuring application..."
if [ ! -f .env ]; then
    cp .env.example .env
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    ENC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    sed -i "s/change-me-to-a-random-secret-key/$SECRET/" .env
    sed -i "s/change-me-to-a-32-byte-hex-key/$ENC_KEY/" .env
    echo "  .env file created with secure keys."
else
    echo "  .env file already exists. Keeping existing configuration."
fi

echo "[6/6] Setting up systemd service..."
cp mxvault.service /etc/systemd/system/mxvault.service
chown -R "$MXUSER:$MXUSER" "$MXDIR"
chmod -R 750 "$MXDIR"
systemctl daemon-reload
systemctl enable mxvault.service
systemctl start mxvault.service

echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "  Default credentials:"
echo "    Username: admin"
echo "    Password: admin123"
echo ""
echo "  Access the web interface at:"
echo "    http://YOUR_SERVER_IP:8000"
echo ""
echo "  Manage service with:"
echo "    systemctl status mxvault"
echo "    systemctl restart mxvault"
echo "    systemctl stop mxvault"
echo ""
echo "  Logs:"
echo "    journalctl -u mxvault -f"
echo ""
echo "  IMPORTANT: Change the default password after first login!"
echo "================================================"
