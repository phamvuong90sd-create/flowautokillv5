#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv .venv-build
./.venv-build/bin/python -m pip install -U pip
./.venv-build/bin/python -m pip install -r requirements.txt
# Bundle Node runtimes for both mac architectures (Playwright driver compatibility)
mkdir -p payload/node/macos/x64 payload/node/macos/arm64 .tmp-node
curl -L https://nodejs.org/dist/v20.19.1/node-v20.19.1-darwin-x64.tar.gz -o .tmp-node/node-x64.tgz
curl -L https://nodejs.org/dist/v20.19.1/node-v20.19.1-darwin-arm64.tar.gz -o .tmp-node/node-arm64.tgz
tar -xzf .tmp-node/node-x64.tgz -C .tmp-node
tar -xzf .tmp-node/node-arm64.tgz -C .tmp-node
cp -f .tmp-node/node-v20.19.1-darwin-x64/bin/node payload/node/macos/x64/node
cp -f .tmp-node/node-v20.19.1-darwin-arm64/bin/node payload/node/macos/arm64/node
chmod +x payload/node/macos/x64/node payload/node/macos/arm64/node

./.venv-build/bin/python -m PyInstaller --noconfirm --windowed --target-arch universal2 --name FlowAutoStandalone --icon assets/icon.icns --hidden-import certifi --collect-data certifi --add-data "payload/scripts:payload/scripts" --add-data "payload/node:payload/node" --add-data "assets/subscription_qr.png:assets" --collect-submodules urllib --collect-all playwright main.py
mkdir -p dist-out/macos
ditto -c -k --sequesterRsrc --keepParent dist/FlowAutoStandalone.app dist-out/macos/FlowAutoStandalone-macos.zip
