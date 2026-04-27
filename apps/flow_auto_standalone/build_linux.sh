#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv-build
./.venv-build/bin/python -m pip install -U pip
./.venv-build/bin/python -m pip install -r requirements.txt
./.venv-build/bin/python -m PyInstaller --noconfirm --onefile --name FlowAutoStandalone --icon assets/icon.png --hidden-import certifi --collect-data certifi --add-data "payload/scripts:payload/scripts" --add-data "assets/subscription_qr.png:assets" --add-data "assets/subscription_qr_bank.png:assets" --collect-submodules urllib --collect-all playwright --collect-all google main.py
mkdir -p dist-out/linux
cp -f dist/FlowAutoStandalone dist-out/linux/FlowAutoStandalone-linux
