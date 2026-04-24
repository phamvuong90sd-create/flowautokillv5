#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv-build
./.venv-build/bin/python -m pip install -U pip
./.venv-build/bin/python -m pip install -r requirements.txt
./.venv-build/bin/python -m PyInstaller --noconfirm --onefile --name FlowAutoStandalone main.py
mkdir -p dist-out/linux
cp -f dist/FlowAutoStandalone dist-out/linux/FlowAutoStandalone-linux
