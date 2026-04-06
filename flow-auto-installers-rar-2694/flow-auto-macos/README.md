# Flow Auto Installer (macOS)

Prompt rule v2.0:
- Clear prompt đúng 1 lần: Ctrl+A -> Delete
- Không multi-pass clear, không JS clear fallback
- Gõ prompt bằng type() với delay để ổn định UI

## Cài đặt
```bash
chmod +x ./install/install.sh
./install/install.sh
```

> Ghi chú: script dùng `systemctl --user`. Nếu máy không có systemd (đa số macOS),
> hãy chạy worker thủ công bằng launchd hoặc tmux.
