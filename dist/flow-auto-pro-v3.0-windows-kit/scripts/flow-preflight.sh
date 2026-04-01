#!/usr/bin/env bash
set -euo pipefail

# flow-preflight.sh
# Mục tiêu:
# - Kiểm tra hệ thống trước khi cài/chạy Flow Auto
# - Nếu thiếu dependency thì tự cài luôn (cần sudo)

AUTO_FIX="${AUTO_FIX:-1}"   # 1 = tự sửa
WS="${FLOW_WORKSPACE:-$HOME/.openclaw/workspace}"
VENV="$WS/.venv-flow"

log() { echo "[preflight] $*"; }
warn() { echo "[preflight][warn] $*"; }
err() { echo "[preflight][error] $*"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

ensure_sudo() {
  if sudo -n true 2>/dev/null; then
    return 0
  fi
  log "Cần quyền sudo để auto setup dependency..."
  sudo -v
}

install_apt_pkgs() {
  local pkgs=("$@")
  [ ${#pkgs[@]} -eq 0 ] && return 0
  ensure_sudo
  log "Installing packages: ${pkgs[*]}"
  sudo apt-get update
  sudo apt-get install -y "${pkgs[@]}"
}

check_os() {
  if [ ! -f /etc/os-release ]; then
    err "Không xác định được OS"
    return 1
  fi
  . /etc/os-release
  log "OS: ${PRETTY_NAME:-unknown}"
}

check_core_tools() {
  local missing=()
  for c in python3 wget systemctl; do
    if ! need_cmd "$c"; then
      missing+=("$c")
    fi
  done

  if [ ${#missing[@]} -gt 0 ]; then
    warn "Thiếu tool core: ${missing[*]}"
    if [ "$AUTO_FIX" = "1" ]; then
      local apt_list=()
      for m in "${missing[@]}"; do
        case "$m" in
          python3) apt_list+=(python3) ;;
          wget) apt_list+=(wget) ;;
          systemctl) apt_list+=(systemd) ;;
        esac
      done
      install_apt_pkgs "${apt_list[@]}"
    else
      return 1
    fi
  fi
}

check_python_stack() {
  local need=()
  dpkg -s python3-pip >/dev/null 2>&1 || need+=(python3-pip)
  dpkg -s python3-venv >/dev/null 2>&1 || need+=(python3-venv)
  dpkg -s python3.12-venv >/dev/null 2>&1 || need+=(python3.12-venv)

  if [ ${#need[@]} -gt 0 ]; then
    warn "Thiếu Python stack: ${need[*]}"
    [ "$AUTO_FIX" = "1" ] && install_apt_pkgs "${need[@]}"
  fi
}

check_chrome() {
  if need_cmd google-chrome || need_cmd google-chrome-stable || need_cmd chromium || need_cmd chromium-browser; then
    log "Browser hỗ trợ đã có"
    return 0
  fi

  warn "Chưa có browser hỗ trợ (Chrome/Chromium)"
  if [ "$AUTO_FIX" = "1" ]; then
    ensure_sudo
    tmp_deb="/tmp/google-chrome-stable_current_amd64.deb"
    log "Cài Google Chrome..."
    wget -q -O "$tmp_deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y "$tmp_deb" || {
      sudo dpkg -i "$tmp_deb" || true
      sudo apt-get -f install -y
      sudo dpkg -i "$tmp_deb"
    }
  fi
}

check_venv_and_playwright() {
  if [ ! -x "$VENV/bin/python" ]; then
    warn "Chưa có venv tại $VENV"
    python3 -m venv "$VENV"
  fi

  if ! "$VENV/bin/python" -c "import playwright" >/dev/null 2>&1; then
    warn "Thiếu playwright trong venv"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install playwright requests
  fi

  log "Python venv + playwright: OK"
}

check_openclaw() {
  if need_cmd openclaw; then
    log "openclaw CLI: OK"
  else
    warn "Không tìm thấy openclaw CLI trên PATH"
  fi
}

check_systemd_user() {
  if systemctl --user status >/dev/null 2>&1; then
    log "systemd --user: OK"
  else
    warn "systemd --user chưa sẵn (có thể do session/user env)"
  fi
}

final_notes() {
  cat <<'EOF'

[preflight] DONE.
Việc vẫn cần thủ công (không auto được hoàn toàn):
1) Đăng nhập Google Flow trên Chrome profile chạy automation
2) (Tuỳ chọn) cấu hình TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID để notify

Lệnh kiểm tra nhanh:
- openclaw gateway status
- systemctl --user status flow-auto-worker.service
- Workspace: $WS
EOF
}

main() {
  check_os
  check_core_tools
  check_python_stack
  check_chrome
  check_venv_and_playwright
  check_openclaw
  check_systemd_user
  final_notes
}

main "$@"
