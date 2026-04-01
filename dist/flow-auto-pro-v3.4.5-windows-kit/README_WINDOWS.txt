Flow Auto Pro V3.4.5 by blackshop.xyz - Windows Kit

Yêu cầu:
- Windows 10/11
- Python 3.11+
- Google Chrome Stable (bắt buộc)

Cài đặt nhanh (PowerShell script):
1) Giải nén package
2) Mở PowerShell as current user (không Run as Administrator)
3) Chạy:
   powershell -ExecutionPolicy Bypass -File .\windows\install_windows.ps1

Build .EXE installer (trên Windows):
1) Cài NSIS: https://nsis.sourceforge.io/Download
2) Chạy:
   .\windows\build_exe_on_windows.bat
3) File output:
   .\windows\FlowAutoPro_v3.4.5_Setup.exe

Trong lúc cài .EXE:
- có màn hình nhập LICENSE_KEY trực tiếp trong installer UI
- LICENSE_API_BASE đã preset: https://server-auto-tool.vercel.app/api/license

Sau cài:
- Task Scheduler tạo task: FlowAutoWorker
- Worker tự chạy khi đăng nhập

Lưu ý:
- Bản Windows này dùng full server-key (không AUTHOR_CODE)
- Verify online bắt buộc, poll 5 phút (strict online)
- Chrome chạy qua remote-debugging port 18800 cho automation
