Flow Auto Video Pro V1.0

Tập trung 2 tính năng chính theo yêu cầu:
- Mapping nhập prompt ổn định (selector-first, ưu tiên nút Create/Tạo theo id/aria/data-testid)
- Mapping đổi mode ổn định cho 2 tỉ lệ: 16:9 và 9:16

Mapping mode mặc định:
- Video            -> trigger-VIDEO
- Thành phần       -> trigger-VIDEO_REFERENCES
- 16:9             -> trigger-LANDSCAPE
- 9:16             -> trigger-PORTRAIT
- x1               -> trigger-1

Luồng mặc định khi đổi mode:
1) Mở Flow + New project (nếu cần)
2) Chuyển về Video
3) Áp profile mặc định: Video + Thành phần + 16:9 + x1
4) Đổi sang mode đích (16:9 hoặc 9:16)
5) Chụp ảnh debug trước/sau

Scripts chính:
- scripts/flow_batch_runner.py      (nhập prompt + tạo)
- scripts/flow_switch_mode.py       (mapping đổi mode)
- scripts/flow_download_all_completed.py

Install:
  tar -xzf flow-auto-video-pro-v1.0-kit.tar.gz
  cd flow-auto-video-pro-v1.0-kit
  bash install.sh

Ghi chú:
- Phiên bản này chỉ hỗ trợ 2 tỉ lệ: 16:9 và 9:16 (không dùng 1:1).
- Nếu UI chưa render cụm trigger tab, cần vào đúng composer state rồi chạy lại.
