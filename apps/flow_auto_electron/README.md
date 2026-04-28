# FLOW AUTO VEO 3 Modern UI

Bản UI riêng dùng Electron + React + Tailwind/shadcn-style. Bản này chạy song song, không thay thế `apps/flow_auto_standalone` ổn định.

## Mục tiêu

- Giao diện thương mại đẹp hơn: sidebar, card, dashboard, form rõ ràng.
- Giữ payload script Flow hiện tại để nối dần backend.
- Có bridge Electron cho: status, license check, AI prompt/script generation, pause/resume/stop.

## Dev

```bash
npm install
npm run dev
```

## Build

```bash
npm run dist
```

Artifacts nằm trong `release/`.

## Ghi chú

- Đây là bản Modern UI riêng, đang ở giai đoạn scaffold/tích hợp dần.
- Bản ổn định hiện tại vẫn là `apps/flow_auto_standalone`.
