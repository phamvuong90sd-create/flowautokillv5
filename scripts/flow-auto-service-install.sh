#!/usr/bin/env bash
set -euo pipefail

SERVICE_PATH="$HOME/.config/systemd/user/flow-auto-worker.service"
WORKSPACE="/home/davis/.openclaw/workspace"
PY="$WORKSPACE/.venv-flow/bin/python"
WORKER="$WORKSPACE/scripts/flow_queue_worker.py"

mkdir -p "$HOME/.config/systemd/user"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Flow Auto Queue Worker
After=default.target

[Service]
Type=simple
WorkingDirectory=$WORKSPACE
ExecStart=$PY $WORKER
Restart=always
RestartSec=3
Environment=FLOW_INBOUND_DIR=/home/davis/.openclaw/media/inbound
Environment=FLOW_QUEUE_DIR=/home/davis/.openclaw/workspace/flow-auto

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now flow-auto-worker.service

echo "[done] installed and started: flow-auto-worker.service"
systemctl --user status flow-auto-worker.service --no-pager -n 20 || true
