# Flow Auto Installer (Windows)

Prompt rule v2.0:
- Clear prompt đúng 1 lần: Ctrl+A -> Delete
- Không multi-pass clear, không JS clear fallback
- Gõ prompt bằng type() với delay để ổn định UI

## Cài đặt
Mở PowerShell (Run as Administrator nếu cần), chạy:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install\install.ps1
```

## Gỡ cài đặt nhanh
```powershell
Unregister-ScheduledTask -TaskName OpenClaw-FlowAuto-Worker -Confirm:$false
```
