#!/usr/bin/env python3
import os
import requests

# Env expected:
# TELEGRAM_BOT_TOKEN=123:abc
# TELEGRAM_CHAT_ID=6480134003
# FLOW_EVENT=done|failed
# FLOW_FILE=<filename>
# FLOW_RC=<exit code>
# FLOW_PROGRESS=<optional text>


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        return 0

    event = os.getenv("FLOW_EVENT", "event")
    file_name = os.getenv("FLOW_FILE", "unknown.txt")
    rc = os.getenv("FLOW_RC", "0")
    progress = os.getenv("FLOW_PROGRESS", "").strip()

    if progress:
        text = f"🎬 Flow progress: {progress}\n📄 File: {file_name}"
    else:
        icon = "✅" if event == "done" else "⚠️"
        text = f"{icon} Flow job {event}\n📄 File: {file_name}\n🔢 rc={rc}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
