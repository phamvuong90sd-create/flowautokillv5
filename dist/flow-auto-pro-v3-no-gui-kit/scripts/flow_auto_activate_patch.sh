#!/usr/bin/env bash
set -euo pipefail

# Flow Auto Video Pro - OpenClaw Ready Patch (NO ACTIVATE)
# Purpose: prepare runtime so customer can use tool immediately on OpenClaw,
# assuming license was already activated during installer.

WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
INBOUND="${FLOW_INBOUND_DIR:-$HOME/.openclaw/media/inbound}"
CHECK_ONLY=0

usage() {
  cat <<'EOF'
Usage:
  bash scripts/flow_auto_activate_patch.sh [options]

Options:
  --workspace <path>    Workspace path (default: ~/.openclaw/workspace)
  --inbound <path>      Inbound path (default: ~/.openclaw/media/inbound)
  --check-only          Only run environment checks (do not modify anything)

This patch does NOT run license activation.
It prepares OpenClaw runtime + worker + menu autorules, then validates READY/NOT_READY.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WS="$2"; shift 2 ;;
    --inbound) INBOUND="$2"; shift 2 ;;
    --check-only) CHECK_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[error] Unknown arg: $1"; usage; exit 2 ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "[error] python3 not found"
  exit 4
fi
PY="$(command -v python3)"

runtime_prepare() {
  mkdir -p "$WS/keys" "$INBOUND" "$WS/flow-auto"

  if [ ! -f "$WS/scripts/flow_queue_worker.py" ]; then
    echo "[error] Missing script: $WS/scripts/flow_queue_worker.py"
    echo "        Install Flow Auto Tool first, then run this patch."
    exit 5
  fi

  echo "[1/4] Inject Flow menu autorules into AGENTS.md"
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

  echo "[2/4] Ensure runtime folders"
  mkdir -p "$WS/flow-auto/processing" "$WS/flow-auto/done" "$WS/flow-auto/failed" "$WS/flow-auto/job-state"

  echo "[3/4] Restart/ensure worker"
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

  echo "[4/4] Optional license check (no activate)"
  if [ -f "$WS/scripts/flow_license_online_check.py" ]; then
    FLOW_WORKSPACE="$WS" FLOW_LICENSE_STRICT_ONLINE=1 "$PY" "$WS/scripts/flow_license_online_check.py" --check || true
  fi
}

run_full_check() {
  local fail=0
  local msg=""

  check_ok() { printf "[check] ✅ %s\n" "$1"; }
  check_no() { printf "[check] ❌ %s\n" "$1"; fail=1; }

  [ -d "$WS" ] && check_ok "Workspace exists: $WS" || check_no "Workspace missing: $WS"
  [ -d "$INBOUND" ] && check_ok "Inbound exists: $INBOUND" || check_no "Inbound missing: $INBOUND"

  [ -f "$WS/scripts/flow_queue_worker.py" ] && check_ok "flow_queue_worker.py present" || check_no "flow_queue_worker.py missing"
  [ -f "$WS/scripts/flow_batch_runner.py" ] && check_ok "flow_batch_runner.py present" || check_no "flow_batch_runner.py missing"
  [ -f "$WS/scripts/flow_switch_mode.py" ] && check_ok "flow_switch_mode.py present" || check_no "flow_switch_mode.py missing"

  [ -f "$WS/keys/license-online.json" ] && check_ok "license-online.json present" || check_no "license-online.json missing"

  if [ -f "$WS/scripts/flow_license_online_check.py" ]; then
    if FLOW_WORKSPACE="$WS" FLOW_LICENSE_STRICT_ONLINE=1 "$PY" "$WS/scripts/flow_license_online_check.py" --check >/tmp/flow_patch_check.log 2>&1; then
      check_ok "License check passed"
    else
      check_no "License check failed (see /tmp/flow_patch_check.log)"
    fi
  else
    check_no "flow_license_online_check.py missing"
  fi

  if [ -f "$WS/AGENTS.md" ] && grep -q "FLOW_MENU_AUTORULES_BEGIN" "$WS/AGENTS.md"; then
    check_ok "Flow menu autorules present"
  else
    check_no "Flow menu autorules missing in AGENTS.md"
  fi

  if pgrep -af "flow_queue_worker.py" >/dev/null 2>&1; then
    check_ok "Worker process is running"
  else
    check_no "Worker process is NOT running"
  fi

  [ -w "$WS/flow-auto" ] && check_ok "flow-auto dir writable" || check_no "flow-auto dir not writable"

  if [ "$fail" -eq 0 ]; then
    echo "READY"
    return 0
  fi

  echo "NOT_READY"
  return 1
}

if [ "$CHECK_ONLY" = "1" ]; then
  echo "[mode] check-only"
  run_full_check
  exit $?
fi

runtime_prepare

echo "[DONE] OpenClaw ready patch applied (no activation)"
echo "workspace=$WS"
echo "inbound=$INBOUND"
echo "worker_log=$WS/flow-auto/worker.log"

echo "[verify] Running full environment check..."
run_full_check
