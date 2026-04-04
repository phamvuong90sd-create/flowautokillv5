Flow Auto Video Pro V1.0.1 - Windows Kit (Compat)

Điểm mới V1.0.1:
- Quy trình bắt buộc: Chọn mode -> Thoát -> Mở lại -> Tạo video.
- Trước khi tạo video đầu tiên sẽ hỏi mode (9:16 / 16:9).
- Chỉ hỗ trợ 2 tỉ lệ: 9:16 và 16:9.

Tương thích Windows:
- Detect Python: `py -3` -> `python` -> `python3`
- Fallback Startup folder nếu Task Scheduler bị chặn
- Worker launcher hỗ trợ py/python/python3

Cài đặt:
  powershell -ExecutionPolicy Bypass -File .\windows\install_windows.ps1

Patch OpenClaw-ready sau cài (không activate lại):
  - dùng script: scripts/flow_auto_activate_patch.sh
  - check-only: scripts/flow_auto_activate_patch.sh --check-only

Build EXE:
  .\windows\build_exe_on_windows.bat
  Output: .\windows\FlowAutoVideoPro_v1.0.1_Setup.exe
