#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "[error] Don't run as root. Run as normal user."
  exit 1
fi

WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
INBOUND="${FLOW_INBOUND_DIR:-$HOME/.openclaw/media/inbound}"
ROOT_DIR="$(cd "$(dirname "$0")" && cd .. && pwd)"

PRESET_LICENSE_API_BASE="${PRESET_LICENSE_API_BASE:-https://server-auto-tool.vercel.app/api/license}"
PRESET_LICENSE_KEY="${PRESET_LICENSE_KEY:-}"

echo "[1/6] Prepare folders"
mkdir -p "$WS/scripts" "$WS/flow-auto/processing" "$WS/flow-auto/done" "$WS/flow-auto/failed" "$WS/flow-auto/job-state" "$INBOUND" "$WS/keys"
cp -f "$ROOT_DIR/scripts"/* "$WS/scripts/" 2>/dev/null || true
# Fix CRLF + executable bits for macOS compatibility
find "$WS/scripts" -type f -name "*.sh" -exec sed -i '' $'s/\r$//' {} \; 2>/dev/null || true
chmod +x "$WS/scripts"/*.sh "$WS/scripts"/*.py || true

mkdir -p "$WS/apps/flow_auto_v2"
cp -fR "$ROOT_DIR/gui_v2/"* "$WS/apps/flow_auto_v2/" 2>/dev/null || true

echo "[2/6] Detect Python"
if command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "[error] python3 not found"
  exit 2
fi

echo "[3/6] Machine ID"
MACHINE_ID="$(ioreg -rd1 -c IOPlatformExpertDevice | awk -F\" '/IOPlatformUUID/{print $4}' | tr '[:upper:]' '[:lower:]')"
if [ -z "$MACHINE_ID" ]; then
  MACHINE_ID="$(hostname | tr '[:upper:]' '[:lower:]')"
fi
echo "machine_id=$MACHINE_ID"

echo "[4/6] License config"
LICENSE_API_BASE="$PRESET_LICENSE_API_BASE"
LICENSE_KEY="$PRESET_LICENSE_KEY"
if [ -z "$LICENSE_KEY" ]; then
  read -r -p "Nhập LICENSE_KEY: " LICENSE_KEY
fi
if [ -z "$LICENSE_API_BASE" ] || [ -z "$LICENSE_KEY" ]; then
  echo "[error] Missing LICENSE_API_BASE or LICENSE_KEY"
  exit 3
fi

FLOW_WORKSPACE="$WS" "$PY" "$WS/scripts/flow_license_online_check.py" --setup --api-base "$LICENSE_API_BASE" --license-key "$LICENSE_KEY" --machine-id "$MACHINE_ID"

echo "[5/6] Activate online"
FLOW_WORKSPACE="$WS" FLOW_LICENSE_STRICT_ONLINE=1 "$PY" "$WS/scripts/flow_license_online_check.py" --activate

echo "[5.5/6] GUI desktop mode: disabled (NO GUI build)"
GUI_MODE="disabled-no-gui"


echo "[6/6] Register LaunchAgent"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
PLIST="$LAUNCH_DIR/com.blackshop.flowautopro.worker.plist"
mkdir -p "$LAUNCH_DIR"
cat > "$PLIST" <<EOP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key><string>com.blackshop.flowautopro.worker</string>
    <key>ProgramArguments</key>
    <array>
      <string>$PY</string>
      <string>$WS/scripts/flow_queue_worker.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
      <key>FLOW_WORKSPACE</key><string>$WS</string>
      <key>FLOW_INBOUND_DIR</key><string>$INBOUND</string>
      <key>FLOW_QUEUE_DIR</key><string>$WS/flow-auto</string>
      <key>FLOW_LICENSE_ENFORCE</key><string>1</string>
      <key>FLOW_LICENSE_MODE</key><string>server</string>
      <key>FLOW_LICENSE_FAIL_ACTION</key><string>exit</string>
      <key>FLOW_LICENSE_STRICT_ONLINE</key><string>1</string>
      <key>FLOW_LICENSE_POLL_SEC</key><string>300</string>
      <key>FLOW_LICENSE_CHECK_CMD</key><string>$PY $WS/scripts/flow_license_online_check.py</string>
    </dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$WS/flow-auto/worker.log</string>
    <key>StandardErrorPath</key><string>$WS/flow-auto/worker.err.log</string>
  </dict>
</plist>
EOP

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

echo "[DONE] Flow Auto Pro V4.0 macOS installed"
echo "API: $LICENSE_API_BASE"
echo "GUI mode: $GUI_MODE"
