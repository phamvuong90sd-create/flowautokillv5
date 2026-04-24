$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
python -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\python -m pip install -r requirements.txt
.\.venv-build\Scripts\python -m PyInstaller --noconfirm --onefile --windowed --name FlowAutoStandalone --add-data "payload/scripts;payload/scripts" main.py
New-Item -ItemType Directory -Force -Path dist-out\windows | Out-Null
Copy-Item -Force dist\FlowAutoStandalone.exe dist-out\windows\FlowAutoStandalone-windows.exe
