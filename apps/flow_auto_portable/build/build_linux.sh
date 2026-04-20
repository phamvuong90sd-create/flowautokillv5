#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-build
source .venv-build/bin/activate
pip install -U pip
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --name FlowAutoPro main.py
mkdir -p dist-portable/linux
cp -f dist/FlowAutoPro dist-portable/linux/FlowAutoPro-linux
chmod +x dist-portable/linux/FlowAutoPro-linux
echo "DONE: dist-portable/linux/FlowAutoPro-linux"
