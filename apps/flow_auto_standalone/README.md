# Flow Auto Standalone (No OpenClaw)

Bản này chạy độc lập, không cần bridge/API OpenClaw.

## Tính năng giữ lại
- Kích hoạt license online
- Chạy Flow batch (start/stop/quick)
- Worker queue (start/stop/status)
- Download completed
- Postprocess videos
- Open exports
- Google login check
- Chọn file prompt từ GUI

## Chạy local
```bash
python3 main.py
```

Dữ liệu runtime nằm ở:
- `~/.flow-auto-standalone/`

## Lưu ý
- Script runtime được copy từ `workspace/scripts` vào `~/.flow-auto-standalone/scripts` khi app mở.
- Không phụ thuộc OpenClaw để chạy GUI này.
