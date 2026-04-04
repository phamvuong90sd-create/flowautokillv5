Flow Auto Video Pro V1.0.1 - macOS Kit

Yêu cầu:
- macOS 12+
- Python 3.10+
- Google Chrome Stable (bắt buộc)

Cài đặt:
1) Giải nén package
2) Mở Terminal và chạy:
   bash ./macos/install_macos.sh

Trong lúc cài:
- API base đã preset: https://server-auto-tool.vercel.app/api/license
- nhập LICENSE_KEY

Sau cài:
- LaunchAgent: com.blackshop.flowautopro.worker
- worker tự chạy khi đăng nhập

Lệnh quản lý:
- unload: launchctl unload ~/Library/LaunchAgents/com.blackshop.flowautopro.worker.plist
- load:   launchctl load ~/Library/LaunchAgents/com.blackshop.flowautopro.worker.plist

Lưu ý:
- full server-key (không AUTHOR_CODE)
- verify online strict, poll 5 phút
- Silent/auto-activate: điền config/customer-license.env rồi chạy:
  FLOW_NON_INTERACTIVE=1 bash ./install.sh

Điểm mới V1.0.1:
- Bắt buộc quy trình: chọn mode -> thoát -> mở lại -> tạo video
- Chỉ hỗ trợ 16:9 và 9:16 (không còn 1:1)
