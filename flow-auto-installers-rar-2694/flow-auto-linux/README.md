# Flow Auto Installer (Linux)

Prompt rule v1.1.2:
- Clear prompt đúng 1 lần: Ctrl+A -> Delete
- Không multi-pass clear, không JS clear fallback
- Gõ prompt bằng type() với delay để ổn định UI

## Cài đặt
```bash
chmod +x ./install/install.sh
./install/install.sh
```

## Kiểm tra service
```bash
systemctl --user status openclaw-flow-auto-worker.service
```
