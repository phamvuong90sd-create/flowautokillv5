#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -U pip
pip install -r requirements.txt
pyinstaller --noconfirm --windowed --name FlowAutoPro \
  --add-data "payload/scripts:payload/scripts" \
  --add-data "payload/core:payload/core" \
  main.py
mkdir -p dist-portable/macos
cp -R dist/FlowAutoPro.app dist-portable/macos/
(cd dist-portable/macos && zip -qry FlowAutoPro-macos.zip FlowAutoPro.app)
echo "DONE: dist-portable/macos/FlowAutoPro-macos.zip"
