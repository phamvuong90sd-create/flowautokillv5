$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
python -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\python -m pip install -r requirements.txt
.\.venv-build\Scripts\python -m PyInstaller --noconfirm --onefile --windowed --name FlowAutoStandalone --icon assets/icon.ico --hidden-import certifi --collect-data certifi --add-data "payload/scripts;payload/scripts" --add-data "assets/subscription_qr.png;assets" --add-data "assets/subscription_qr_bank.png;assets" --collect-submodules urllib --collect-all playwright main.py
New-Item -ItemType Directory -Force -Path dist-out\windows | Out-Null
Copy-Item -Force dist\FlowAutoStandalone.exe dist-out\windows\FlowAutoStandalone-windows.exe
