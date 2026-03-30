#!/usr/bin/env bash
set -euo pipefail

if [ "${SUDO_USER:-}" != "" ] || [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "[error] Đừng chạy bằng sudo/root. Hãy chạy bằng user thường: bash install.sh"
  exit 1
fi

WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
INBOUND="${FLOW_INBOUND_DIR:-$HOME/.openclaw/media/inbound}"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$WS/scripts/bin" "$WS/flow-auto/processing" "$WS/flow-auto/done" "$WS/flow-auto/failed" "$WS/flow-auto/job-state" "$INBOUND"
cp -f "$ROOT_DIR/scripts"/* "$WS/scripts/" 2>/dev/null || true
cp -f "$ROOT_DIR/scripts/bin/flow_license_verify" "$WS/scripts/bin/flow_license_verify"
chmod +x "$WS/scripts"/*.sh "$WS/scripts"/*.py "$WS/scripts/bin/flow_license_verify" || true

PY="$(command -v python3)"

echo "[1/5] Preflight môi trường..."
AUTO_FIX=1 FLOW_WORKSPACE="$WS" FLOW_INBOUND_DIR="$INBOUND" "$WS/scripts/flow-preflight.sh"

echo "[2/5] Machine ID của máy này:"
MACHINE_ID="$($WS/scripts/bin/flow_license_verify --machine-id)"
echo "----------------------------------------"
echo "$MACHINE_ID"
echo "----------------------------------------"
echo "Gửi Machine ID này cho ông chủ để lấy mã AUTHOR_CODE."

read -r -p "Nhập AUTHOR_CODE để tiếp tục cài đặt: " AUTHOR_CODE
if [ -z "$AUTHOR_CODE" ]; then
  echo "[error] AUTHOR_CODE trống. Dừng cài đặt."
  exit 2
fi

echo "[3/6] Kích hoạt bản quyền offline (AUTHOR_CODE)..."
FLOW_WORKSPACE="$WS" "$WS/scripts/flow_author_activate.sh" "$AUTHOR_CODE"

echo "[4/6] Cấu hình license online (khuyến nghị)"
read -r -p "Nhập LICENSE_API_BASE (vd: https://your-app.vercel.app/api/license, Enter để bỏ qua): " LICENSE_API_BASE
read -r -p "Nhập LICENSE_KEY cho máy này (Enter để bỏ qua): " LICENSE_KEY

if [ -n "${LICENSE_API_BASE}" ] && [ -n "${LICENSE_KEY}" ]; then
  mkdir -p "$WS/keys"
  FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --setup \
    --api-base "$LICENSE_API_BASE" --license-key "$LICENSE_KEY"

  echo "[license-online] thử activate với server..."
  if FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --activate; then
    ONLINE_OK=1
  else
    ONLINE_OK=0
    echo "[warn] activate online chưa thành công, sẽ fallback offline AUTHOR_CODE"
  fi
else
  ONLINE_OK=0
  echo "[skip] bỏ qua license online, chỉ dùng author code"
fi

echo "[5/6] Setup runtime..."
FLOW_WORKSPACE="$WS" FLOW_INBOUND_DIR="$INBOUND" "$WS/scripts/setup-flow-automation.sh"

echo "[6/6] Kích hoạt worker..."
if systemctl --user status >/dev/null 2>&1; then
  FLOW_WORKSPACE="$WS" "$WS/scripts/flow-auto-service-install.sh"
  mkdir -p "$HOME/.config/systemd/user/flow-auto-worker.service.d"
  cat > "$HOME/.config/systemd/user/flow-auto-worker.service.d/license-enforce.conf" <<EOC
[Service]
Environment=FLOW_LICENSE_ENFORCE=1
Environment=FLOW_LICENSE_MODE=author-rsa
Environment=FLOW_AUTHOR_PUBLIC_KEY=$WS/scripts/flow_author_public.pem
Environment=FLOW_LICENSE_FAIL_ACTION=exit
Environment=FLOW_LICENSE_CHECK_CMD=$PY $WS/scripts/flow_license_online_check.py
Environment=FLOW_LICENSE_POLL_SEC=43200
EOC
  systemctl --user daemon-reload
  systemctl --user restart flow-auto-worker.service
  MODE="systemd-user"
else
  FLOW_LICENSE_ENFORCE=1 FLOW_LICENSE_MODE=author-rsa FLOW_AUTHOR_PUBLIC_KEY="$WS/scripts/flow_author_public.pem" FLOW_LICENSE_FAIL_ACTION=exit \
  FLOW_LICENSE_CHECK_CMD="$PY $WS/scripts/flow_license_online_check.py" FLOW_LICENSE_POLL_SEC=43200 \
    nohup "$WS/.venv-flow/bin/python" "$WS/scripts/flow_queue_worker.py" > "$WS/flow-auto/worker.log" 2>&1 &
  MODE="nohup-fallback"
fi

echo "[DONE] Flow Auto Pro V3.0 by blackshop.xyz installed ($MODE)"
echo "Inbound folder: $INBOUND"
echo "Image wizard: $WS/scripts/flow_image_wizard.sh"
echo "Download-all tool: $WS/scripts/flow_download_all_completed.py"
echo "Online license config: $WS/keys/license-online.json"
