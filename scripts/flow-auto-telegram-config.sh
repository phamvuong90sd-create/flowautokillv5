#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <TELEGRAM_BOT_TOKEN> <TELEGRAM_CHAT_ID>"
  exit 1
fi

TOKEN="$1"
CHAT_ID="$2"
WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
OVERRIDE_DIR="$HOME/.config/systemd/user/flow-auto-worker.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"

mkdir -p "$OVERRIDE_DIR"
cat > "$OVERRIDE_FILE" <<EOF
[Service]
Environment=TELEGRAM_BOT_TOKEN=$TOKEN
Environment=TELEGRAM_CHAT_ID=$CHAT_ID
EOF

systemctl --user daemon-reload
systemctl --user restart flow-auto-worker.service

echo "[done] Telegram notify configured and service restarted"
