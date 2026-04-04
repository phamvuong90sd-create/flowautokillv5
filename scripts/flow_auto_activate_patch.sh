#!/usr/bin/env bash
set -euo pipefail

# Flow Auto Video Pro - Auto Activate Patch (OpenClaw)
# Purpose: one-command activation/setup for already-installed workspace.
# NOTE: This does NOT bypass license. A valid LICENSE_KEY is still required.

WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
INBOUND="${FLOW_INBOUND_DIR:-$HOME/.openclaw/media/inbound}"
ENV_FILE="${FLOW_PATCH_ENV_FILE:-}"
API_BASE="${PRESET_LICENSE_API_BASE:-${FLOW_LICENSE_API_BASE_DEFAULT:-}}"
LICENSE_KEY="${PRESET_LICENSE_KEY:-${FLOW_LICENSE_KEY_DEFAULT:-}}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/flow_auto_activate_patch.sh [options]

Options:
  --workspace <path>       Workspace path (default: ~/.openclaw/workspace)
  --inbound <path>         Inbound path (default: ~/.openclaw/media/inbound)
  --env-file <path>        Optional env file containing PRESET_LICENSE_API_BASE/PRESET_LICENSE_KEY
  --api-base <url>         License API base
  --license-key <key>      License key

Examples:
  PRESET_LICENSE_API_BASE=https://server-auto-tool.vercel.app/api/license \
  PRESET_LICENSE_KEY=LIC-XXXX bash scripts/flow_auto_activate_patch.sh

  bash scripts/flow_auto_activate_patch.sh \
    --env-file ./config/customer-license.env \
    --workspace ~/.openclaw/workspace
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WS="$2"; shift 2 ;;
    --inbound) INBOUND="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --api-base) API_BASE="$2"; shift 2 ;;
    --license-key) LICENSE_KEY="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[error] Unknown arg: $1"; usage; exit 2 ;;
  esac
done

if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  API_BASE="${PRESET_LICENSE_API_BASE:-${API_BASE}}"
  LICENSE_KEY="${PRESET_LICENSE_KEY:-${LICENSE_KEY}}"
fi

if [ -z "$API_BASE" ] || [ -z "$LICENSE_KEY" ]; then
  echo "[error] Missing API_BASE or LICENSE_KEY"
  echo "        Provide via --api-base/--license-key or --env-file"
  exit 3
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 not found"
  exit 4
fi
PY="$(command -v python3)"

mkdir -p "$WS/keys" "$INBOUND"

if [ ! -f "$WS/scripts/flow_license_online_check.py" ]; then
  echo "[error] Missing script: $WS/scripts/flow_license_online_check.py"
  echo "        Install Flow Auto Tool first, then run this patch."
  exit 5
fi

MACHINE_ID=""
if [ -x "$WS/scripts/bin/flow_license_verify" ]; then
  MACHINE_ID="$($WS/scripts/bin/flow_license_verify --machine-id || true)"
fi
if [ -z "$MACHINE_ID" ]; then
  MACHINE_ID="$(hostname | tr '[:upper:]' '[:lower:]')"
fi

echo "[1/5] Setup online license config"
FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --setup \
  --api-base "$API_BASE" --license-key "$LICENSE_KEY" --machine-id "$MACHINE_ID"

echo "[2/5] Activate online"
FLOW_WORKSPACE="$WS" FLOW_LICENSE_STRICT_ONLINE=1 "$PY" "$WS/scripts/flow_license_online_check.py" --activate

echo "[3/5] Inject Flow menu autorules into AGENTS.md"
AGENTS_FILE="$WS/AGENTS.md"
[ -f "$AGENTS_FILE" ] || cat > "$AGENTS_FILE" <<'EOM'
# AGENTS.md
EOM
if ! grep -q "FLOW_MENU_AUTORULES_BEGIN" "$AGENTS_FILE" 2>/dev/null; then
  cat >> "$AGENTS_FILE" <<'EOM'

<!-- FLOW_MENU_AUTORULES_BEGIN -->
## Flow Auto Pro Menu Autorules (Customer)
When user sends any of these commands:
- "Hiển thị menu"
- "/hiển thị menu"
- "menu flow"
- "show menu"
- "show_menu_options"

Assistant should immediately display Flow Auto Pro menu with action buttons:
- set_text_prompt
- set_image_prompt
- set_image_path
- run_quick_start
- run_start
- run_stop
- download_all_completed
- check_license_remaining
- show_menu_options
- clear_browser_cache
- repair_chrome_reinstall
- google_login_auto_check

Behavior requirements:
1) No extra explanation before menu.
2) Keep Vietnamese concise.
3) After customer installation, menu behavior should match owner machine.
<!-- FLOW_MENU_AUTORULES_END -->
EOM
fi

echo "[4/5] Ensure worker is running"
if systemctl --user status >/dev/null 2>&1; then
  systemctl --user daemon-reload || true
  systemctl --user restart flow-auto-worker.service || true
else
  if pgrep -af "flow_queue_worker.py" >/dev/null 2>&1; then
    pkill -f "flow_queue_worker.py" || true
    sleep 1
  fi
  NOHUP_PY="$WS/.venv-flow/bin/python"
  [ -x "$NOHUP_PY" ] || NOHUP_PY="$PY"
  nohup "$NOHUP_PY" "$WS/scripts/flow_queue_worker.py" > "$WS/flow-auto/worker.log" 2>&1 &
fi

echo "[5/5] Verify"
FLOW_WORKSPACE="$WS" FLOW_LICENSE_STRICT_ONLINE=1 "$PY" "$WS/scripts/flow_license_online_check.py" --check

echo "[DONE] Auto activate patch applied"
echo "workspace=$WS"
echo "inbound=$INBOUND"
echo "machine_id=$MACHINE_ID"
echo "api_base=$API_BASE"
echo "license_config=$WS/keys/license-online.json"
