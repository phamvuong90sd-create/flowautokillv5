Flow Auto Pro V3.0 by blackshop.xyz

Giữ nguyên option như bộ cũ + thêm các cập nhật mới:
- Auto check/chuyển Video mode trước khi chạy
- Auto retry set ratio (16:9 / 9:16) + debug screenshot
- Auto open New project khi cần
- Auto download sau khi hoàn tất run (best effort)
- Script tải tất cả completed: scripts/flow_download_all_completed.py
- Hỗ trợ prompt delay từ .flow_state.json (9/15/30/45s)
- Hỗ trợ license online check định kỳ qua API: scripts/flow_license_online_check.py

Install:
  tar -xzf flow-auto-pro-v3.0-by-blackshop.xyz.tar.gz
  cd flow-auto-pro-v3.0-kit
  bash install.sh

Trong lúc cài:
- vẫn nhập AUTHOR_CODE như cũ (offline)
- có thể nhập thêm LICENSE_API_BASE + LICENSE_KEY để kích hoạt check online

Sau cài:
- worker/service giữ flow cũ
- nếu có online config, worker sẽ verify định kỳ 12h/lần
- file cấu hình online license: ~/.openclaw/workspace/keys/license-online.json
- tên banner: Flow Auto Pro V3.0 by blackshop.xyz
