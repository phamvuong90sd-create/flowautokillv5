#!/usr/bin/env bash
set -euo pipefail

echo "[check] flow-auto-worker service"
systemctl --user is-active flow-auto-worker.service && echo "  active: ok" || echo "  active: fail"

echo "[check] openclaw gateway"
openclaw gateway status | sed -n '1,20p'

echo "[check] browser status"
openclaw gateway status >/dev/null 2>&1 || true

echo "[hint] live worker logs: journalctl --user -u flow-auto-worker.service -f"
