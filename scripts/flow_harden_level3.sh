#!/usr/bin/env bash
set -euo pipefail

# Level-3 hardening for Flow Auto Pro
# - build integrity manifest
# - enforce verify check in systemd worker
# - lock critical scripts immutable (optional)

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
SERVICE_DROPIN_DIR="$HOME/.config/systemd/user/flow-auto-worker.service.d"
SERVICE_DROPIN_FILE="$SERVICE_DROPIN_DIR/harden-level3.conf"
PY="${FLOW_PY:-$WORKSPACE/.venv-flow/bin/python}"

if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi

if [ -z "$PY" ]; then
  echo "[error] python not found"
  exit 1
fi

echo "[L3] build integrity manifest"
"$PY" "$WORKSPACE/scripts/flow_integrity_build_manifest.py" --workspace "$WORKSPACE" --version "3.4.5"

echo "[L3] write systemd hardening drop-in"
mkdir -p "$SERVICE_DROPIN_DIR"
cat > "$SERVICE_DROPIN_FILE" <<EOF
[Service]
Environment=FLOW_INTEGRITY_ENFORCE=1
Environment=FLOW_INTEGRITY_CHECK_CMD=$PY $WORKSPACE/scripts/flow_integrity_verify.py --workspace $WORKSPACE
EOF

systemctl --user daemon-reload

# Insert integrity precheck into worker service if missing
SERVICE_PATH="$HOME/.config/systemd/user/flow-auto-worker.service"
if [ -f "$SERVICE_PATH" ] && ! grep -q "FLOW_INTEGRITY_CHECK_CMD" "$SERVICE_PATH"; then
  cp "$SERVICE_PATH" "$SERVICE_PATH.bak.$(date +%s)"
  awk '
    BEGIN{inserted=0}
    /^RestartSec=/ && inserted==0 {
      print $0
      print "ExecStartPre=/bin/bash -lc \"if [ \\\"${FLOW_INTEGRITY_ENFORCE:-0}\\\" = 1 ] && [ -n \\\"${FLOW_INTEGRITY_CHECK_CMD:-}\\\" ]; then ${FLOW_INTEGRITY_CHECK_CMD}; fi\""
      inserted=1
      next
    }
    {print $0}
  ' "$SERVICE_PATH" > "$SERVICE_PATH.tmp"
  mv "$SERVICE_PATH.tmp" "$SERVICE_PATH"
  systemctl --user daemon-reload
fi

echo "[L3] optional immutable lock on critical scripts"
if command -v chattr >/dev/null 2>&1; then
  for f in \
    "$WORKSPACE/scripts/flow_batch_runner.py" \
    "$WORKSPACE/scripts/flow_queue_worker.py" \
    "$WORKSPACE/scripts/flow_license_online_check.py" \
    "$WORKSPACE/scripts/flow_integrity_verify.py" \
    "$WORKSPACE/keys/flow-integrity-manifest.json"
  do
    [ -f "$f" ] || continue
    chattr +i "$f" 2>/dev/null || true
  done
fi

echo "[L3] restart worker"
systemctl --user restart flow-auto-worker.service || true
systemctl --user status flow-auto-worker.service --no-pager -n 30 || true

echo "[done] level-3 hardening applied"
