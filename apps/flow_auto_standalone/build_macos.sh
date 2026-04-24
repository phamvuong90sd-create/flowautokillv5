#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv-build
./.venv-build/bin/python -m pip install -U pip
./.venv-build/bin/python -m pip install -r requirements.txt
./.venv-build/bin/python -m PyInstaller --noconfirm --windowed --name FlowAutoStandalone --add-data "payload/scripts:payload/scripts" --collect-submodules urllib --collect-all playwright main.py
mkdir -p dist-out/macos
ditto -c -k --sequesterRsrc --keepParent dist/FlowAutoStandalone.app dist-out/macos/FlowAutoStandalone-macos.zip
