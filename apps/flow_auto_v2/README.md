# Flow Auto v2 (2-mode)

## Mode 1: Server Web/API
```bash
bash /home/davis/.openclaw/workspace/apps/flow_auto_v2/scripts/run_server_mode.sh
```
- Health: `GET http://127.0.0.1:18777/health`
- Start job: `POST /api/start`
- Stop job: `POST /api/stop`
- Status: `GET /api/status`
- License check: `GET /api/license/check`

## Mode 2: Desktop GUI
```bash
bash /home/davis/.openclaw/workspace/apps/flow_auto_v2/scripts/run_desktop_mode.sh
```
> GUI gọi local API của mode server.

## Telegram/OpenClaw integration
- Telegram vẫn ra lệnh qua OpenClaw bình thường.
- OpenClaw chỉ cần gọi local API mode server để `start/stop/status`.
