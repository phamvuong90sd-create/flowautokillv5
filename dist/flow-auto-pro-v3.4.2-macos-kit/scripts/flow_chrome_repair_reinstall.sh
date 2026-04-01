#!/usr/bin/env bash
set -euo pipefail

# Flow Auto Pro - Chrome repair (reinstall + clean profile + reopen Flow)
# Usage:
#   bash scripts/flow_chrome_repair_reinstall.sh

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
CHROME_USER_DATA="${FLOW_CHROME_USER_DATA:-$HOME/.config/google-chrome-flow}"
FLOW_URL="${FLOW_START_URL:-https://labs.google/fx/tools/flow}"

WINDOW_STATE="${FLOW_WINDOW_STATE:-normal}"
WINDOW_W="${FLOW_WINDOW_WIDTH:-1280}"
WINDOW_H="${FLOW_WINDOW_HEIGHT:-800}"
WINDOW_X="${FLOW_WINDOW_X:-20}"
WINDOW_Y="${FLOW_WINDOW_Y:-20}"

echo "[repair] stop worker + close browser"
systemctl --user stop flow-auto-worker.service >/dev/null 2>&1 || true
pkill -x google-chrome >/dev/null 2>&1 || true
pkill -x google-chrome-stable >/dev/null 2>&1 || true
pkill -x chromium >/dev/null 2>&1 || true
pkill -x chromium-browser >/dev/null 2>&1 || true

if command -v apt >/dev/null 2>&1; then
  echo "[repair] reinstall google-chrome-stable via apt"
  sudo apt update
  sudo apt install --reinstall -y google-chrome-stable
else
  echo "[warn] apt not found, skip reinstall step"
fi

echo "[repair] clean Chrome Flow profile cache"
mkdir -p "$CHROME_USER_DATA"
find "$CHROME_USER_DATA" -type d \( -name "Cache" -o -name "Code Cache" -o -name "GPUCache" -o -name "GrShaderCache" -o -name "DawnCache" -o -name "ShaderCache" \) -prune -exec rm -rf {} + || true
find "$CHROME_USER_DATA" -type f -name "*.log" -delete || true

echo "[repair] relaunch Chrome + Flow"
BROWSER_BIN="${FLOW_BROWSER_BIN:-$HOME/chrome-for-testing/chrome-linux64/chrome}"
if [ ! -x "$BROWSER_BIN" ]; then
  BROWSER_BIN="$(command -v google-chrome || command -v google-chrome-stable || true)"
fi
if [ -z "$BROWSER_BIN" ]; then
  echo "[error] no browser binary found"
  exit 3
fi
CMD=("$BROWSER_BIN"
  --remote-debugging-port=18800
  --user-data-dir="$CHROME_USER_DATA"
  --no-first-run
  --no-default-browser-check
  --new-window
  --force-device-scale-factor=1
)

if [ "$WINDOW_STATE" = "maximized" ]; then
  CMD+=(--start-maximized)
else
  CMD+=(--window-size="${WINDOW_W},${WINDOW_H}" --window-position="${WINDOW_X},${WINDOW_Y}")
fi

CMD+=("$FLOW_URL")
nohup "${CMD[@]}" >/tmp/flow-chrome.log 2>&1 &

sleep 3
echo "[done] chrome repaired/reinstalled and flow reopened"
exit 0
