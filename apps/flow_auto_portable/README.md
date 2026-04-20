# Flow Auto Pro Portable (No-install)

Portable GUI app (first run requires LICENSE_KEY activation online).

## First-run flow
1. Mở app
2. Nếu chưa active, app hiện popup nhập `LICENSE_KEY`
3. App gọi activate online qua `scripts/flow_license_online_check.py`
4. Active thành công -> lưu vào workspace keys -> app chạy bình thường các lần sau

## Runtime requirements
- OpenClaw workspace exists at `~/.openclaw/workspace`
- `apps/flow_auto_v2/core/service.py` exists (bridge service)
- scripts in `~/.openclaw/workspace/scripts`

## Build in VSCode
- Linux: `bash build/build_linux.sh`
- macOS: `bash build/build_macos.sh`
- Windows: `powershell -ExecutionPolicy Bypass -File build/build_windows.ps1`

Outputs:
- Linux: `dist-portable/linux/FlowAutoPro-linux`
- macOS: `dist-portable/macos/FlowAutoPro-macos.zip`
- Windows: `dist-portable/windows/FlowAutoPro-windows.exe`
