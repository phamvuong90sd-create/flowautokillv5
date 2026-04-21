#!/usr/bin/env bash
set -euo pipefail

if [ "${SUDO_USER:-}" != "" ] || [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "[error] Đừng chạy bằng sudo/root. Hãy chạy bằng user thường: bash install.sh"
  exit 1
fi

WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
INBOUND="${FLOW_INBOUND_DIR:-$HOME/.openclaw/media/inbound}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Optional preseed file for customer package (no interactive online setup)
# Expected vars: PRESET_LICENSE_API_BASE, PRESET_LICENSE_KEY
if [ -f "$ROOT_DIR/config/customer-license.env" ]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/config/customer-license.env"
fi

PRESET_LICENSE_API_BASE="${PRESET_LICENSE_API_BASE:-${FLOW_LICENSE_API_BASE_DEFAULT:-}}"
PRESET_LICENSE_KEY="${PRESET_LICENSE_KEY:-${FLOW_LICENSE_KEY_DEFAULT:-}}"

mkdir -p "$WS/scripts/bin" "$WS/flow-auto/processing" "$WS/flow-auto/done" "$WS/flow-auto/failed" "$WS/flow-auto/job-state" "$INBOUND"
cp -f "$ROOT_DIR/scripts"/* "$WS/scripts/" 2>/dev/null || true
cp -f "$ROOT_DIR/scripts/bin/flow_license_verify" "$WS/scripts/bin/flow_license_verify"
# Fix CRLF + executable bits for macOS compatibility
find "$WS/scripts" -type f -name "*.sh" -exec sed -i '' $'s/\r$//' {} \; 2>/dev/null || true
chmod +x "$WS/scripts"/*.sh "$WS/scripts"/*.py "$WS/scripts/bin/flow_license_verify" || true

# Ship v2 GUI payload (optional mode)
mkdir -p "$WS/apps/flow_auto_v2"
cp -fR "$ROOT_DIR/gui_v2/"* "$WS/apps/flow_auto_v2/" 2>/dev/null || true

PY="$(command -v python3)"

echo "[1/8] Preflight môi trường..."
AUTO_FIX=1 FLOW_WORKSPACE="$WS" FLOW_INBOUND_DIR="$INBOUND" bash "$WS/scripts/flow-preflight.sh"

echo "[2/6] Machine ID của máy này:"
MACHINE_ID="$($WS/scripts/bin/flow_license_verify --machine-id)"
echo "----------------------------------------"
echo "$MACHINE_ID"
echo "----------------------------------------"

echo "[3/6] Cấu hình bắt buộc để kiểm tra license online"
LICENSE_API_BASE="${PRESET_LICENSE_API_BASE}"
LICENSE_KEY="${PRESET_LICENSE_KEY}"

if [ -z "${LICENSE_API_BASE}" ]; then
  read -r -p "Nhập LICENSE_API_BASE (vd: https://your-app.vercel.app/api/license): " LICENSE_API_BASE
fi
if [ -z "${LICENSE_KEY}" ]; then
  read -r -p "Nhập LICENSE_KEY cho máy này: " LICENSE_KEY
fi

if [ -z "${LICENSE_API_BASE}" ] || [ -z "${LICENSE_KEY}" ]; then
  echo "[error] Thiếu LICENSE_API_BASE hoặc LICENSE_KEY. Dừng cài đặt."
  exit 3
fi

mkdir -p "$WS/keys"
FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --setup \
  --api-base "$LICENSE_API_BASE" --license-key "$LICENSE_KEY" --machine-id "$MACHINE_ID"

echo "[4/6] Kích hoạt online với server (bắt buộc)"
if FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --activate; then
  ONLINE_OK=1
else
  ONLINE_OK=0
  echo "[error] activate online thất bại. Dừng cài đặt."
  exit 4
fi

echo "[5/6] Setup runtime..."
FLOW_WORKSPACE="$WS" FLOW_INBOUND_DIR="$INBOUND" bash "$WS/scripts/setup-flow-automation.sh"

echo "[5.5/6] Cài GUI desktop mode (optional)"
INSTALL_GUI="${INSTALL_GUI:-}"
if [ -z "$INSTALL_GUI" ]; then
  read -r -p "Cài thêm GUI desktop mode? (y/N): " INSTALL_GUI
fi
if [[ "${INSTALL_GUI,,}" == "y" || "${INSTALL_GUI,,}" == "yes" ]]; then
  cat > "$WS/scripts/flow_auto_v2_server.sh" <<'EOV2S'
#!/usr/bin/env bash
exec python3 "$HOME/.openclaw/workspace/apps/flow_auto_v2/core/service.py"
EOV2S
  cat > "$WS/scripts/flow_auto_v2_gui.sh" <<'EOV2G'
#!/usr/bin/env bash
exec python3 "$HOME/.openclaw/workspace/apps/flow_auto_v2/core/desktop_gui.py"
EOV2G
  chmod +x "$WS/scripts/flow_auto_v2_server.sh" "$WS/scripts/flow_auto_v2_gui.sh"

  # macOS desktop launcher (.command)
  if [ -d "$HOME/Desktop" ]; then
    cat > "$HOME/Desktop/Flow Auto Pro GUI.command" <<EOC
#!/usr/bin/env bash
exec "$WS/scripts/flow_auto_v2_gui.sh"
EOC
    chmod +x "$HOME/Desktop/Flow Auto Pro GUI.command" || true
  fi

  GUI_MODE="installed"
else
  GUI_MODE="skip"
fi

echo "[6/6] Kích hoạt worker..."
if systemctl --user status >/dev/null 2>&1; then
  FLOW_WORKSPACE="$WS" "$WS/scripts/flow-auto-service-install.sh"
  mkdir -p "$HOME/.config/systemd/user/flow-auto-worker.service.d"
  cat > "$HOME/.config/systemd/user/flow-auto-worker.service.d/license-enforce.conf" <<EOC
[Service]
Environment=FLOW_LICENSE_ENFORCE=1
Environment=FLOW_LICENSE_MODE=server
Environment=FLOW_LICENSE_FAIL_ACTION=exit
Environment=FLOW_LICENSE_CHECK_CMD=$PY $WS/scripts/flow_license_online_check.py
Environment=FLOW_LICENSE_POLL_SEC=300
Environment=FLOW_LICENSE_STRICT_ONLINE=1
EOC
  systemctl --user daemon-reload
  systemctl --user restart flow-auto-worker.service
  MODE="systemd-user"
else
  FLOW_LICENSE_ENFORCE=1 FLOW_LICENSE_MODE=server FLOW_LICENSE_FAIL_ACTION=exit \
  FLOW_LICENSE_CHECK_CMD="$PY $WS/scripts/flow_license_online_check.py" FLOW_LICENSE_POLL_SEC=300 FLOW_LICENSE_STRICT_ONLINE=1 \
    nohup "$WS/.venv-flow/bin/python" "$WS/scripts/flow_queue_worker.py" > "$WS/flow-auto/worker.log" 2>&1 &
  MODE="nohup-fallback"
fi

echo "[7/7] Auto harden level 3..."
if [ -x "$WS/scripts/flow_harden_level3.sh" ]; then
  FLOW_WORKSPACE="$WS" bash "$WS/scripts/flow_harden_level3.sh" || true
else
  echo "[warn] flow_harden_level3.sh not found, skip"
fi

echo "[DONE] Flow Auto Pro V3.0.1 by blackshop.xyz installed ($MODE)"
echo "Inbound folder: $INBOUND"
echo "Image wizard: $WS/scripts/flow_image_wizard.sh"
echo "Download-all tool: $WS/scripts/flow_download_all_completed.py"
echo "Online license config: $WS/keys/license-online.json"
echo "Integrity manifest: $WS/keys/flow-integrity-manifest.json"
echo "GUI mode: $GUI_MODE"
