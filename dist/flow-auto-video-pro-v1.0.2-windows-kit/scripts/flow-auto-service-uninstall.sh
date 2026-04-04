#!/usr/bin/env bash
set -euo pipefail

SERVICE=flow-auto-worker.service
systemctl --user disable --now "$SERVICE" || true
rm -f "$HOME/.config/systemd/user/$SERVICE"
systemctl --user daemon-reload

echo "[done] uninstalled $SERVICE"
