#!/usr/bin/env bash
set -euo pipefail

# setup-flow-automation.sh
# Mục tiêu:
# 1) Cài trình duyệt hỗ trợ automation (Google Chrome) nếu thiếu
# 2) Cài Python runtime + venv + playwright cho script Flow
# 3) Đảm bảo các script chính tồn tại
# 4) In hướng dẫn chạy nhanh

WORKSPACE="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
SCRIPTS_DIR="$WORKSPACE/scripts"
VENV_DIR="$WORKSPACE/.venv-flow"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[error] Missing command: $1"
    exit 1
  }
}

install_chrome_if_missing() {
  if command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1; then
    echo "[ok] Google Chrome đã có"
    return
  fi

  echo "[step] Cài Google Chrome..."
  require_cmd wget
  require_cmd sudo

  tmp_deb="/tmp/google-chrome-stable_current_amd64.deb"
  wget -q -O "$tmp_deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

  # Dùng apt để tự xử lý dependency
  sudo apt-get update
  sudo apt-get install -y "$tmp_deb" || {
    echo "[warn] apt install trực tiếp .deb lỗi, thử dpkg + apt -f"
    sudo dpkg -i "$tmp_deb" || true
    sudo apt-get -f install -y
    sudo dpkg -i "$tmp_deb"
  }

  echo "[ok] Chrome version: $(google-chrome --version 2>/dev/null || google-chrome-stable --version)"
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

  install_chrome_if_missing
  install_python_stack

  echo "[step] Gợi ý: restart gateway để browser tool attach ổn định"
  echo "       openclaw gateway restart"

  print_next_steps
}

main "$@"
