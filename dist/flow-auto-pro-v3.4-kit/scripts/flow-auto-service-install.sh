#!/usr/bin/env bash
set -euo pipefail

SERVICE_PATH="$HOME/.config/systemd/user/flow-auto-worker.service"
WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
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
Environment=FLOW_WORKSPACE=$WORKSPACE
Environment=FLOW_INBOUND_DIR=$HOME/.openclaw/media/inbound
Environment=FLOW_QUEUE_DIR=$WORKSPACE/flow-auto
Environment=FLOW_POLL_SEC=8
# Default browser: Chrome for Testing
Environment=FLOW_BROWSER_BIN=$HOME/chrome-for-testing/chrome-linux64/chrome
Environment=FLOW_CHROME_USER_DATA=$HOME/.config/google-chrome-flow-testing
Environment=FLOW_CDP=http://127.0.0.1:18800
Environment=FLOW_START_URL=https://labs.google/fx/tools/flow
Environment=FLOW_GOOGLE_LOGIN_FIRST=1
Environment=FLOW_GOOGLE_LOGIN_URL=https://accounts.google.com
Environment="FLOW_NOTIFY_CMD=$WORKSPACE/.venv-flow/bin/python $WORKSPACE/scripts/flow-telegram-notify.py"
Environment="FLOW_LICENSE_CHECK_CMD=$WORKSPACE/scripts/bin/flow_license_verify"
Environment=FLOW_LICENSE_POLL_SEC=300
Environment=FLOW_LICENSE_FAIL_ACTION=exit
Environment=FLOW_LICENSE_ENFORCE=1
Environment=FLOW_LICENSE_GRACE_DAYS=0
Environment=FLOW_PRODUCT=flow-auto
Environment=FLOW_LICENSE_MODE=server
Environment=FLOW_LICENSE_STRICT_ONLINE=1
# Server-key licensing only (no AUTHOR_CODE)
Environment=FLOW_LICENSE_SERVER=
Environment=FLOW_LICENSE_KEY=

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now flow-auto-worker.service

echo "[done] installed and started: flow-auto-worker.service"
systemctl --user status flow-auto-worker.service --no-pager -n 20 || true
