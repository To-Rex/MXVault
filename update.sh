#!/usr/bin/env bash
set -euo pipefail

MXDIR="/opt/mxvault"
BACKUP_DIR="${MXDIR}/backups_before_update"

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root" >&2
    exit 1
fi

echo "================================================"
echo "  MXVault Update Script"
echo "================================================"
echo ""

if [ ! -d "$MXDIR" ]; then
    echo "Error: MXVault not found at $MXDIR" >&2
    exit 1
fi

echo "[1/4] Backing up current installation..."
mkdir -p "$BACKUP_DIR"
cp "$MXDIR/.env" "$BACKUP_DIR/.env.bak"
cp -r "$MXDIR/data" "$BACKUP_DIR/data.bak" 2>/dev/null || true
echo "  Backup saved to $BACKUP_DIR"

echo "[2/4] Updating application files..."
cd "$MXDIR"
git pull origin main 2>/dev/null || {
    echo "  Git not configured. Please manually copy the new files to $MXDIR"
    exit 1
}

echo "[3/4] Updating dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies updated."

echo "[4/4] Restarting service..."
systemctl restart mxvault.service
sleep 2
systemctl status mxvault.service --no-pager

echo ""
echo "Update complete! MXVault has been restarted."
echo "If something went wrong, restore from backup:"
echo "  cp $BACKUP_DIR/.env.bak $MXDIR/.env"
echo "  cp -r $BACKUP_DIR/data.bak/* $MXDIR/data/"
