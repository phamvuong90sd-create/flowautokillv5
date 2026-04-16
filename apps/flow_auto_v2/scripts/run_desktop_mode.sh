#!/usr/bin/env bash
set -e
# mode desktop: cần server mode chạy trước
cd /home/davis/.openclaw/workspace/apps/flow_auto_v2/core
exec python3 desktop_gui.py
