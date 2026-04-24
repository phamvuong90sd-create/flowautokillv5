#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./gen_code.sh <machine_id> <YYYY-MM-DD> [plan]
# Example:
#   ./gen_code.sh abc123 2026-04-30 monthly

MACHINE_ID="${1:-}"
EXPIRE_DATE="${2:-}"
PLAN="${3:-monthly}"

if [ -z "$MACHINE_ID" ] || [ -z "$EXPIRE_DATE" ]; then
  echo "Usage: $0 <machine_id> <YYYY-MM-DD> [plan]"
  exit 1
fi

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
PY="$WORKSPACE/.venv-flow/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
LIC_PY="$WORKSPACE/scripts/flow_license.py"

if [ ! -f "$LIC_PY" ]; then
  echo "[error] missing: $LIC_PY"
  exit 2
fi

# Default shared secret for v1.0.9 flow (change in production)
SECRET="${FLOW_AUTHOR_SECRET:-FLOWAUTO_AUTHOR_V1_CHANGE_ME}"
EXPIRES_AT="${EXPIRE_DATE}T23:59:59+07:00"

FLOW_AUTHOR_SECRET="$SECRET" \
"$PY" "$LIC_PY" \
  --gen-author \
  --for-machine "$MACHINE_ID" \
  --expires-at "$EXPIRES_AT" \
  --plan "$PLAN"
