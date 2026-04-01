#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./gen_code_rsa.sh <machine_id> <YYYY-MM-DD> [plan]

MACHINE_ID="${1:-}"
EXPIRE_DATE="${2:-}"
PLAN="${3:-monthly}"

if [ -z "$MACHINE_ID" ] || [ -z "$EXPIRE_DATE" ]; then
  echo "Usage: $0 <machine_id> <YYYY-MM-DD> [plan]"
  exit 1
fi

PRIVATE_KEY="${FLOW_AUTHOR_PRIVATE_KEY:-$HOME/.openclaw/workspace/keys/flow_author_private.pem}"
if [ ! -f "$PRIVATE_KEY" ]; then
  echo "[error] missing private key: $PRIVATE_KEY"
  exit 2
fi

PRODUCT="${FLOW_PRODUCT:-flow-auto}"
GRACE="${FLOW_LICENSE_GRACE_DAYS:-3}"
EXPIRES_AT="${EXPIRE_DATE}T23:59:59+07:00"
ISSUED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

PAYLOAD_JSON="$(cat <<EOF
{"product":"$PRODUCT","machine_id":"$MACHINE_ID","expires_at":"$EXPIRES_AT","plan":"$PLAN","grace_days":$GRACE,"issued_at":"$ISSUED_AT"}
EOF
)"

PAYLOAD_B64="$(printf '%s' "$PAYLOAD_JSON" | openssl base64 -A | tr '+/' '-_' | tr -d '=')"
SIG_B64="$(printf '%s' "$PAYLOAD_B64" | openssl dgst -sha256 -sign "$PRIVATE_KEY" -binary | openssl base64 -A | tr '+/' '-_' | tr -d '=')"

printf '%s.%s\n' "$PAYLOAD_B64" "$SIG_B64"
