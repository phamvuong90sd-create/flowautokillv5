Flow Auto Pro V3.4.2 by blackshop.xyz

Giữ nguyên option như bộ cũ + thêm các cập nhật mới:
- Auto check/chuyển Video mode trước khi chạy
- Auto retry set ratio (16:9 / 9:16) + debug screenshot
- Auto open New project khi cần
- Auto download sau khi hoàn tất run (best effort)
- Script tải tất cả completed: scripts/flow_download_all_completed.py
- Hỗ trợ prompt delay từ .flow_state.json (9/15/30/45s)
- Hỗ trợ license online check định kỳ qua API: scripts/flow_license_online_check.py

Install:
  tar -xzf flow-auto-pro-v3.4.2-by-blackshop.xyz.tar.gz
  cd flow-auto-pro-v3.4.2-macos-kit
  bash install.sh

Trong lúc cài (full server-key):
- bắt buộc có LICENSE_API_BASE + LICENSE_KEY (không cho skip)
- tự lấy machine_id của máy cài
- activate online bắt buộc thành công mới cài tiếp
- không dùng AUTHOR_CODE

Tuỳ chọn pre-config:
- Tạo file `config/customer-license.env` trong bộ cài với nội dung:
  - `PRESET_LICENSE_API_BASE=https://your-app.vercel.app/api/license`
  - `PRESET_LICENSE_KEY=LIC-XXXX-XXXX-XXXX`
- Khi có file này, installer tự điền sẵn các giá trị tương ứng.

Sau cài:
- worker/service giữ flow cũ
- nếu có online config, worker sẽ verify định kỳ 12h/lần
- file cấu hình online license: ~/.openclaw/workspace/keys/license-online.json
- tên banner: Flow Auto Pro V3.4.2 by blackshop.xyz
