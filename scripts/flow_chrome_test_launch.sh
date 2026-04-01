#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
BIN="${FLOW_BROWSER_BIN:-$HOME/chrome-for-testing/chrome-linux64/chrome}"
USER_DATA="${FLOW_CHROME_USER_DATA:-$HOME/.config/google-chrome-flow-testing}"
CDP_PORT="${FLOW_CDP_PORT:-18800}"
FLOW_URL="${FLOW_START_URL:-https://labs.google/fx/tools/flow}"

WINDOW_STATE="${FLOW_WINDOW_STATE:-normal}"
WINDOW_W="${FLOW_WINDOW_WIDTH:-1280}"
WINDOW_H="${FLOW_WINDOW_HEIGHT:-800}"
WINDOW_X="${FLOW_WINDOW_X:-20}"
WINDOW_Y="${FLOW_WINDOW_Y:-20}"

if [ ! -x "$BIN" ]; then
  echo "[error] Chrome for Testing not found: $BIN"
  echo "Install path expected: ~/chrome-for-testing/chrome-linux64/chrome"
  exit 2
fi

mkdir -p "$USER_DATA"

pkill -x google-chrome >/dev/null 2>&1 || true
pkill -x google-chrome-stable >/dev/null 2>&1 || true
pkill -x chromium >/dev/null 2>&1 || true
pkill -x chromium-browser >/dev/null 2>&1 || true

CMD=("$BIN"
  "--remote-debugging-port=$CDP_PORT"
  "--user-data-dir=$USER_DATA"
  --no-first-run
  --no-default-browser-check
  --new-window
  --force-device-scale-factor=1
)

if [ "$WINDOW_STATE" = "maximized" ]; then
  CMD+=(--start-maximized)
else
  CMD+=("--window-size=${WINDOW_W},${WINDOW_H}" "--window-position=${WINDOW_X},${WINDOW_Y}")
fi

CMD+=("$FLOW_URL")
nohup "${CMD[@]}" >/tmp/flow-chrome-testing.log 2>&1 &

echo "[ok] launched Chrome for Testing on CDP :$CDP_PORT"
echo "[ok] bin=$BIN"
echo "[ok] user-data=$USER_DATA"
