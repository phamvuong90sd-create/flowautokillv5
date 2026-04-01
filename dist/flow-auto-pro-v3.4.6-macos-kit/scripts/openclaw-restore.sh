#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup-archive.tar.gz>"
  exit 1
fi

ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
  echo "Archive not found: $ARCHIVE"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "[step] extracting archive..."
tar -xzf "$ARCHIVE" -C "$TMP_DIR"

copy_back() {
  local src="$1"
  local dst="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    echo "[ok] restored: $dst"
  else
    echo "[skip] missing in backup: $src"
  fi
}

echo "[step] restoring files..."
copy_back "$TMP_DIR/home/.openclaw/openclaw.json" "$HOME/.openclaw/openclaw.json"
copy_back "$TMP_DIR/home/.openclaw/extensions" "$HOME/.openclaw/extensions"
copy_back "$TMP_DIR/home/.openclaw/credentials" "$HOME/.openclaw/credentials"
copy_back "$TMP_DIR/home/.openclaw/cron" "$HOME/.openclaw/cron"
copy_back "$TMP_DIR/home/.openclaw/workspace" "$HOME/.openclaw/workspace"
copy_back "$TMP_DIR/home/.config/systemd/user/openclaw-gateway.service" "$HOME/.config/systemd/user/openclaw-gateway.service"

echo "[step] reloading systemd user daemon..."
systemctl --user daemon-reload || true

if [ -f "$HOME/.config/systemd/user/openclaw-gateway.service" ]; then
  echo "[step] enabling gateway service..."
  systemctl --user enable --now openclaw-gateway.service || true
fi

echo "[done] restore complete"
echo "[next] recommend run: openclaw gateway restart"
