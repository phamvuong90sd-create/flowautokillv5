Flow Auto Video Pro V1.0.1

Điểm mới V1.0.1 (quan trọng):
- Quy trình bắt buộc: Chọn mode -> Thoát -> Mở lại -> Tạo video.
- Trước khi tạo video đầu tiên sẽ hỏi mode kích thước.
- Chỉ hỗ trợ 2 tỉ lệ: 16:9 và 9:16 (bỏ 1:1).

Mapping mode:
- Video            -> trigger-VIDEO
- Thành phần       -> trigger-VIDEO_REFERENCES
- 16:9             -> trigger-LANDSCAPE
- 9:16             -> trigger-PORTRAIT
- x1               -> trigger-1

Scripts chính:
- scripts/flow_batch_runner.py      (nhập prompt + tạo)
- scripts/flow_switch_mode.py       (đổi mode + thoát)
- scripts/flow_download_all_completed.py

Install:
  tar -xzf flow-auto-video-pro-v1.0.1-kit.tar.gz
  cd flow-auto-video-pro-v1.0.1-kit
  bash install.sh

Patch OpenClaw-ready sau cài (không activate lại):
  bash scripts/flow_auto_activate_patch.sh
