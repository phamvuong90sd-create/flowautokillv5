#!/usr/bin/env bash
set -euo pipefail

# setup-flow-automation.sh
# Mục tiêu:
# 1) Cài Chrome for Testing (mặc định) cho automation ổn định
# 2) Cài Python runtime + venv + playwright cho script Flow
# 3) Đảm bảo các script chính tồn tại
# 4) Tự cấu hình worker dùng Chrome for Testing
# 5) In hướng dẫn chạy nhanh

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
SCRIPTS_DIR="$WORKSPACE/scripts"
VENV_DIR="$WORKSPACE/.venv-flow"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[error] Missing command: $1"
    exit 1
  }
}

install_chrome_for_testing_if_missing() {
  local cft_bin="$HOME/chrome-for-testing/chrome-linux64/chrome"
  if [ -x "$cft_bin" ]; then
    echo "[ok] Chrome for Testing đã có: $cft_bin"
    return
  fi

  echo "[step] Cài Chrome for Testing..."
  require_cmd wget
  require_cmd unzip

  local base="$HOME/chrome-for-testing"
  local zip="/tmp/chrome-for-testing-linux64.zip"

  mkdir -p "$base"
  wget -q -O "$zip" "https://storage.googleapis.com/chrome-for-testing-public/last-known-good-versions-with-downloads.json"

  local dl_url
  dl_url=$(python3 - <<'PY'
import json
p='/tmp/chrome-for-testing-linux64.zip'
with open(p,'r',encoding='utf-8') as f:
    data=json.load(f)
arr=data['channels']['Stable']['downloads']['chrome']
url=[x['url'] for x in arr if x.get('platform')=='linux64'][0]
print(url)
PY
)

  wget -q -O "$zip" "$dl_url"
  rm -rf "$base/chrome-linux64"
  unzip -q -o "$zip" -d "$base"

  if [ ! -x "$cft_bin" ]; then
    echo "[error] Cài Chrome for Testing thất bại"
    exit 1
  fi

  echo "[ok] Chrome for Testing: $($cft_bin --version 2>/dev/null || true)"
}

configure_worker_default_browser_testing() {
  echo "[step] Cấu hình worker mặc định dùng Chrome for Testing..."
  local override_dir="$HOME/.config/systemd/user/flow-auto-worker.service.d"
  local override_file="$override_dir/browser-testing.conf"
  mkdir -p "$override_dir"

  cat > "$override_file" <<EOF
[Service]
Environment=FLOW_BROWSER_BIN=$HOME/chrome-for-testing/chrome-linux64/chrome
Environment=FLOW_CHROME_USER_DATA=$HOME/.config/google-chrome-flow-testing
Environment=FLOW_CDP=http://127.0.0.1:18800
Environment=FLOW_START_URL=https://labs.google/fx/tools/flow
Environment=FLOW_GOOGLE_LOGIN_FIRST=1
Environment=FLOW_GOOGLE_LOGIN_URL=https://accounts.google.com
EOF

  systemctl --user daemon-reload || true
  systemctl --user restart flow-auto-worker.service >/dev/null 2>&1 || true
  echo "[ok] Worker default browser set to Chrome for Testing"
}

install_python_stack() {
  echo "[step] Kiểm tra Python stack..."

  local need_install=0
  dpkg -s python3-pip >/dev/null 2>&1 || need_install=1
  dpkg -s python3-venv >/dev/null 2>&1 || need_install=1
  dpkg -s python3.12-venv >/dev/null 2>&1 || need_install=1

  if [ "$need_install" -eq 1 ]; then
    echo "[step] Cài Python packages hệ thống cần thiết..."
    require_cmd sudo
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv python3.12-venv
  else
    echo "[ok] Python apt packages đã đủ, bỏ qua cài lại"
  fi

  echo "[step] Tạo/kiểm tra virtualenv tại $VENV_DIR ..."
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
  fi

  echo "[step] Kiểm tra packages Python trong venv..."
  if ! "$VENV_DIR/bin/python" -c "import playwright, requests" >/dev/null 2>&1; then
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install playwright requests
    echo "[ok] Đã cài playwright + requests"
  else
    echo "[ok] playwright + requests đã có, bỏ qua cài lại"
  fi

  echo "[ok] Python stack ready"
}

verify_scripts() {
  echo "[step] Kiểm tra scripts cần thiết..."

  local required=(
    "$SCRIPTS_DIR/flow_batch_runner.py"
    "$SCRIPTS_DIR/openclaw-backup.sh"
    "$SCRIPTS_DIR/openclaw-restore.sh"
  )

  local missing=0
  for f in "${required[@]}"; do
    if [ -f "$f" ]; then
      echo "[ok] found: $f"
    else
      echo "[missing] $f"
      missing=1
    fi
  done

  if [ "$missing" -eq 1 ]; then
    echo "[error] Thiếu script. Hãy tạo lại script còn thiếu trước khi chạy setup này."
    exit 1
  fi

  chmod +x "$SCRIPTS_DIR/openclaw-backup.sh" "$SCRIPTS_DIR/openclaw-restore.sh"
}

print_next_steps() {
  cat <<EOF

================= DONE =================
Các script chính:
- $WORKSPACE/scripts/flow_batch_runner.py
- $WORKSPACE/scripts/openclaw-backup.sh
- $WORKSPACE/scripts/openclaw-restore.sh

Chạy backup:
  $WORKSPACE/scripts/openclaw-backup.sh

Chạy restore:
  $WORKSPACE/scripts/openclaw-restore.sh <backup.tar.gz>

Chạy automation video:
  $WORKSPACE/.venv-flow/bin/python \
    $WORKSPACE/scripts/flow_batch_runner.py \
    --prompts '$HOME/.openclaw/media/inbound/<ten_file_txt>.txt' \
    --state $WORKSPACE/.flow_state.json \
    --start-from 1
========================================
EOF
}

main() {
  require_cmd bash
  require_cmd python3

  verify_scripts

  # Preflight first (auto-fix dependencies when possible)
  if [ -x "$SCRIPTS_DIR/flow-preflight.sh" ]; then
    FLOW_WORKSPACE="$WORKSPACE" "$SCRIPTS_DIR/flow-preflight.sh"
  fi

  install_chrome_for_testing_if_missing
  install_python_stack
  configure_worker_default_browser_testing

  echo "[step] Gợi ý: restart gateway để browser tool attach ổn định"
  echo "       openclaw gateway restart"

  print_next_steps
}

main "$@"
