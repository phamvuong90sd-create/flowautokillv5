$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
py -m venv .venv-build
.\.venv-build\Scripts\python -m pip install --upgrade pip
.\.venv-build\Scripts\python -m pip install -r requirements.txt
.\.venv-build\Scripts\pyinstaller --noconfirm --onefile --windowed --name FlowAutoPro --add-data "payload/scripts;payload/scripts" --add-data "payload/core;payload/core" main.py
New-Item -ItemType Directory -Force -Path dist-portable\windows | Out-Null
Copy-Item -Force dist\FlowAutoPro.exe dist-portable\windows\FlowAutoPro-windows.exe
Write-Host "DONE: dist-portable\\windows\\FlowAutoPro-windows.exe"
