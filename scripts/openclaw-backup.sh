#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-$HOME/openclaw-backups}"
DATE_TAG="$(date +%F-%H%M%S)"
OUT_DIR="$BACKUP_ROOT/openclaw-backup-$DATE_TAG"
ARCHIVE_PATH="$BACKUP_ROOT/openclaw-backup-$DATE_TAG.tar.gz"

mkdir -p "$OUT_DIR"
mkdir -p "$BACKUP_ROOT"

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
  else
    echo "[skip] not found: $src"
  fi
}

echo "[info] backup root: $BACKUP_ROOT"

echo "[step] copying core OpenClaw config..."
copy_if_exists "$HOME/.openclaw/openclaw.json" "$OUT_DIR/home/.openclaw/openclaw.json"
copy_if_exists "$HOME/.openclaw/extensions" "$OUT_DIR/home/.openclaw/extensions"
copy_if_exists "$HOME/.openclaw/credentials" "$OUT_DIR/home/.openclaw/credentials"
copy_if_exists "$HOME/.openclaw/cron" "$OUT_DIR/home/.openclaw/cron"

echo "[step] copying workspace..."
copy_if_exists "/home/davis/.openclaw/workspace" "$OUT_DIR/home/davis/.openclaw/workspace"

echo "[step] copying systemd user service..."
copy_if_exists "$HOME/.config/systemd/user/openclaw-gateway.service" "$OUT_DIR/home/.config/systemd/user/openclaw-gateway.service"

echo "[step] writing manifest..."
cat > "$OUT_DIR/MANIFEST.txt" <<EOF
Created: $(date -Is)
Host: $(hostname)
User: $(id -un)
Includes:
- ~/.openclaw/openclaw.json
- ~/.openclaw/extensions/
- ~/.openclaw/credentials/
- ~/.openclaw/cron/
- /home/davis/.openclaw/workspace/
- ~/.config/systemd/user/openclaw-gateway.service
EOF

echo "[step] creating archive..."
tar -czf "$ARCHIVE_PATH" -C "$OUT_DIR" .

echo "[done] backup created: $ARCHIVE_PATH"
echo "$ARCHIVE_PATH"
