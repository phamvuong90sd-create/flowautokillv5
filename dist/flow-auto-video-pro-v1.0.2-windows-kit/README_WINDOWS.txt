Flow Auto Video Pro V1.0.2 - Windows Kit (Compat)

Điểm mới V1.0.2:
- Thêm patch CMD lấy mã máy: windows\\get_machine_id.cmd
- Quy tắc nhập prompt v1.0.2: clear 1 lần duy nhất (Ctrl+A -> Delete), không multi-pass, không JS clear fallback.

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

Ghi chú lấy mã máy:
- Chạy trực tiếp patch CMD (double-click hoặc Run as Administrator): .\windows\get_machine_id.cmd
- CMD sẽ chỉ hiển thị mã máy trên màn hình để copy, không lưu file.
- Dùng mã này để tạo LICENSE_KEY chính xác cho khách.

Patch OpenClaw-ready hiện tích hợp tự động trong install.sh (Linux/macOS).
Trên Windows có thể chạy check-only từ script nếu dùng môi trường bash tương thích:
  scripts/flow_auto_activate_patch.sh --check-only

Build EXE:
  .\windows\build_exe_on_windows.bat
  Output: .\windows\FlowAutoVideoPro_v1.0.1_Setup.exe
