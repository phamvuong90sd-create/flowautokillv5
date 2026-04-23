#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
PY="$WORKSPACE/.venv-flow/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
LIC_BIN="$WORKSPACE/scripts/bin/flow_license_verify"
LIC_PY="$WORKSPACE/scripts/flow_license_verify.py"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <AUTHOR_CODE>"
  exit 1
fi

AUTHOR_CODE="$1"
if [ -x "$LIC_BIN" ]; then
  "$LIC_BIN" --activate "$AUTHOR_CODE"
  FLOW_LICENSE_ENFORCE=1 FLOW_LICENSE_MODE=author-rsa "$LIC_BIN" --json
else
  "$PY" "$LIC_PY" --activate "$AUTHOR_CODE"
  FLOW_LICENSE_ENFORCE=1 FLOW_LICENSE_MODE=author-rsa "$PY" "$LIC_PY" --json
fi

echo "[ok] activation stored + verified"
