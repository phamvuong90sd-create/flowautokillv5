Flow Auto Video Pro V1.0 - Windows Kit (Tương thích cao)

Yêu cầu:
- Windows 10/11
- Python 3.11+ (khuyến nghị cài Python chính chủ)
- Google Chrome Stable

Điểm tăng tương thích trong bản này:
- Detect Python theo thứ tự: `py -3` -> `python` -> `python3`
- Scheduled Task fallback sang Startup folder khi bị chặn quyền
- Worker launcher Windows hỗ trợ cả py/python/python3
- Giữ cơ chế activate + verify online bắt buộc (strict)

Cài đặt nhanh (PowerShell):
1) Giải nén package
2) Mở PowerShell (user thường, không cần admin)
3) Chạy:
   powershell -ExecutionPolicy Bypass -File .\windows\install_windows.ps1

Build .EXE installer (trên Windows):
1) Cài NSIS: https://nsis.sourceforge.io/Download
2) Chạy:
   .\windows\build_exe_on_windows.bat
3) File output:
   .\windows\FlowAutoVideoPro_v1.0_Setup.exe

Trong lúc cài .EXE:
- nhập LICENSE_KEY trực tiếp trong installer
- LICENSE_API_BASE preset: https://server-auto-tool.vercel.app/api/license

Sau cài:
- Task Scheduler tạo task: FlowAutoWorker (hoặc Startup fallback)
- Worker tự chạy khi đăng nhập

Lưu ý:
- Bản này dùng full server-key (không AUTHOR_CODE)
- Verify online bắt buộc, poll 5 phút (strict online)
- Chrome dùng remote-debugging port 18800
