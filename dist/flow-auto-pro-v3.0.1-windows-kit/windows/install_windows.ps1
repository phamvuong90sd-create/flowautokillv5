$ErrorActionPreference = 'Stop'

$WS = if ($env:FLOW_WORKSPACE) { $env:FLOW_WORKSPACE } else { Join-Path $HOME '.openclaw\workspace' }
$INBOUND = if ($env:FLOW_INBOUND_DIR) { $env:FLOW_INBOUND_DIR } else { Join-Path $HOME '.openclaw\media\inbound' }
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent

Write-Host "[1/6] Prepare folders"
New-Item -ItemType Directory -Force -Path "$WS\scripts" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\processing" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\done" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\failed" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\job-state" | Out-Null
New-Item -ItemType Directory -Force -Path "$INBOUND" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\keys" | Out-Null

Copy-Item -Force "$ROOT\scripts\*" "$WS\scripts\" -Recurse
New-Item -ItemType Directory -Force -Path "$WS\apps\flow_auto_v2" | Out-Null
if (Test-Path "$ROOT\gui_v2") { Copy-Item -Force "$ROOT\gui_v2\*" "$WS\apps\flow_auto_v2\" -Recurse }

Write-Host "[2/6] Detect Python"
$py = ""
if (Get-Command py -ErrorAction SilentlyContinue) {
  $py = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $py = "python"
} else {
  throw "Python not found. Please install Python 3.11+ and rerun."
}

Write-Host "[3/6] Read machine id"
$machineId = ""
try {
  $machineId = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid.ToLower().Trim()
} catch {
  $machineId = $env:COMPUTERNAME.ToLower().Trim()
}
Write-Host "Machine ID: $machineId"

Write-Host "[4/6] License config"
$apiBase = $env:PRESET_LICENSE_API_BASE
if (-not $apiBase) { $apiBase = "https://server-auto-tool.vercel.app/api/license" }
Write-Host "LICENSE_API_BASE: $apiBase"
$key = $env:PRESET_LICENSE_KEY
if (-not $key) { $key = Read-Host "Nhập LICENSE_KEY" }
if (-not $apiBase -or -not $key) { throw "Thiếu LICENSE_API_BASE hoặc LICENSE_KEY" }

& $py "$WS\scripts\flow_license_online_check.py" --setup --api-base "$apiBase" --license-key "$key" --machine-id "$machineId"

Write-Host "[5/6] Activate online"
& $py "$WS\scripts\flow_license_online_check.py" --activate
if ($LASTEXITCODE -ne 0) { throw "Activate online thất bại" }

Write-Host "[5.5/6] Optional GUI mode"
$installGui = $env:INSTALL_GUI
if (-not $installGui) { $installGui = Read-Host "Cai them GUI desktop mode? (y/N)" }
if ($installGui -match '^(?i:y|yes)$') {
  @"
@echo off
python "%USERPROFILE%\.openclaw\workspace\apps\flow_auto_v2\core\service.py"
"@ | Set-Content -Encoding ASCII "$WS\scripts\flow_auto_v2_server.bat"

  @"
@echo off
python "%USERPROFILE%\.openclaw\workspace\apps\flow_auto_v2\core\desktop_gui.py"
"@ | Set-Content -Encoding ASCII "$WS\scripts\flow_auto_v2_gui.bat"
  $GUI_MODE = 'installed'
} else {
  $GUI_MODE = 'skip'
}

Write-Host "[6/6] Register startup task"
$taskName = "FlowAutoWorker"
$cmd = "`"$py`" `"$WS\scripts\flow_queue_worker.py`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
} catch {}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Flow Auto Worker" | Out-Null
Start-ScheduledTask -TaskName $taskName

Write-Host "[DONE] Flow Auto Pro V3.0.1 Windows installed"
Write-Host "Workspace: $WS"
Write-Host "Inbound: $INBOUND"

Write-Host "GUI mode: $GUI_MODE"
