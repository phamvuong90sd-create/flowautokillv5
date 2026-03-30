#!/usr/bin/env bash
set -euo pipefail

# setup-flow-automation.sh
# Mục tiêu:
# 1) Cài trình duyệt hỗ trợ automation (Google Chrome) nếu thiếu
# 2) Cài Python runtime + venv + playwright cho script Flow
# 3) Đảm bảo các script chính tồn tại
# 4) In hướng dẫn chạy nhanh

WORKSPACE="/home/davis/.openclaw/workspace"
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
  echo "[step] Cài Python packages hệ thống cần thiết..."
  require_cmd sudo
  sudo apt-get update
  sudo apt-get install -y python3 python3-pip python3-venv python3.12-venv

  echo "[step] Tạo virtualenv tại $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"

  echo "[step] Cài playwright vào venv..."
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install playwright

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
  cat <<'EOF'

================= DONE =================
Các script chính:
- /home/davis/.openclaw/workspace/scripts/flow_batch_runner.py
- /home/davis/.openclaw/workspace/scripts/openclaw-backup.sh
- /home/davis/.openclaw/workspace/scripts/openclaw-restore.sh

Chạy backup:
  /home/davis/.openclaw/workspace/scripts/openclaw-backup.sh

Chạy restore:
  /home/davis/.openclaw/workspace/scripts/openclaw-restore.sh <backup.tar.gz>

Chạy automation video:
  /home/davis/.openclaw/workspace/.venv-flow/bin/python \
    /home/davis/.openclaw/workspace/scripts/flow_batch_runner.py \
    --prompts '/home/davis/.openclaw/media/inbound/kịch_bản_2---7297c459-3818-4874-b979-6892c6e3c3d1.txt' \
    --state /home/davis/.openclaw/workspace/.flow_state.json \
    --start-from 1
========================================
EOF
}

main() {
  require_cmd bash
  require_cmd python3

  verify_scripts
  install_chrome_if_missing
  install_python_stack

  echo "[step] Gợi ý: restart gateway để browser tool attach ổn định"
  echo "       openclaw gateway restart"

  print_next_steps
}

main "$@"
