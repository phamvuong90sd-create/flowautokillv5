$ErrorActionPreference = 'Stop'

$WS = if ($env:FLOW_WORKSPACE) { $env:FLOW_WORKSPACE } else { Join-Path $HOME '.openclaw\workspace' }
$INBOUND = if ($env:FLOW_INBOUND_DIR) { $env:FLOW_INBOUND_DIR } else { Join-Path $HOME '.openclaw\media\inbound' }
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent


# Load preseed license from config/customer-license.env if present
$preseedFile = Join-Path $ROOT 'config\customer-license.env'
if (Test-Path $preseedFile) {
  Get-Content $preseedFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    $kv = $line -split '=',2
    if ($kv.Count -eq 2) {
      $k = $kv[0].Trim()
      $v = $kv[1].Trim().Trim('"')
      if (-not (Get-Item "Env:$k" -ErrorAction SilentlyContinue)) {
        [Environment]::SetEnvironmentVariable($k, $v, 'Process')
      }
    }
  }
}

Write-Host "[1/6] Prepare folders"
New-Item -ItemType Directory -Force -Path "$WS\scripts" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\processing" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\done" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\failed" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\flow-auto\job-state" | Out-Null
New-Item -ItemType Directory -Force -Path "$INBOUND" | Out-Null
New-Item -ItemType Directory -Force -Path "$WS\keys" | Out-Null

Copy-Item -Force "$ROOT\scripts\*" "$WS\scripts\" -Recurse

# Inject Flow menu auto-rules so AI on customer machine can recognize menu commands
$agentsFile = Join-Path $WS 'AGENTS.md'
if (-not (Test-Path $agentsFile)) { Set-Content -Path $agentsFile -Value "# AGENTS.md`r`n" }
$agentsText = Get-Content -Path $agentsFile -Raw
if ($agentsText -notmatch 'FLOW_MENU_AUTORULES_BEGIN') {
  Add-Content -Path $agentsFile -Value @"

<!-- FLOW_MENU_AUTORULES_BEGIN -->
## Flow Auto Pro Menu Autorules (Customer)
When user sends any of these commands:
- "Hiển thị menu"
- "/hiển thị menu"
- "menu flow"
- "show menu"
- "show_menu_options"

Assistant should immediately display Flow Auto Pro menu with action buttons:
- set_text_prompt
- set_image_prompt
- set_image_path
- run_quick_start
- run_start
- run_stop
- download_all_completed
- check_license_remaining
- show_menu_options
- clear_browser_cache
- repair_chrome_reinstall
- google_login_auto_check

Behavior requirements:
1) No extra explanation before menu.
2) Keep Vietnamese concise.
3) After customer installation, menu behavior should match owner machine.
<!-- FLOW_MENU_AUTORULES_END -->
"@
}

Write-Host "[2/6] Detect Python (compat mode)"
$py = ""
$pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  # Ưu tiên py launcher để tương thích nhiều máy Windows
  $py = "py"
  $pyArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $py = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
  $py = "python3"
} else {
  throw "Python not found. Please install Python 3.11+ and rerun."
}

Write-Host "[3/6] Read machine id"
$machineId = ""

# 1) Prefer same generator as license verify tool (most consistent)
$verifyExe = Join-Path $WS "scripts\bin\flow_license_verify"
if (Test-Path $verifyExe) {
  try {
    $machineId = (& $verifyExe --machine-id | Out-String).Trim().ToLower()
  } catch {}
}

# 2) Registry MachineGuid fallback
if (-not $machineId) {
  try {
    $machineId = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid).MachineGuid.ToLower().Trim()
  } catch {}
}

# 3) CIM/BIOS fallback
if (-not $machineId) {
  try {
    $uuid = (Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue).UUID
    if ($uuid) { $machineId = $uuid.ToLower().Trim() }
  } catch {}
}

# 4) Hostname fallback
if (-not $machineId) {
  $machineId = $env:COMPUTERNAME.ToLower().Trim()
}

if (-not $machineId) {
  throw "Không lấy được Machine ID. Hãy chạy lại installer bằng PowerShell Run as Administrator hoặc kiểm tra WMI/Registry quyền truy cập."
}

# Save for support/debug
Set-Content -Path "$WS\keys\machine-id.txt" -Value $machineId -Encoding ascii -Force
Write-Host "Machine ID: $machineId"
Write-Host "Saved: $WS\keys\machine-id.txt"

Write-Host "[4/6] License config"
$apiBase = $env:PRESET_LICENSE_API_BASE
if (-not $apiBase) { $apiBase = "https://server-auto-tool.vercel.app/api/license" }
Write-Host "LICENSE_API_BASE: $apiBase"
$key = Read-Host "Nhập LICENSE_KEY"
if (-not $apiBase -or -not $key) { throw "Thiếu LICENSE_API_BASE hoặc LICENSE_KEY" }

& $py @pyArgs "$WS\scripts\flow_license_online_check.py" --setup --api-base "$apiBase" --license-key "$key" --machine-id "$machineId"

Write-Host "[5/6] Activate online"
& $py @pyArgs "$WS\scripts\flow_license_online_check.py" --activate
if ($LASTEXITCODE -ne 0) { throw "Activate online thất bại" }

Write-Host "[6/6] Register startup task (fallback to Startup folder if denied)"
$taskName = "FlowAutoWorker"
$pyExecForTask = if ($py -eq "py") { "py -3" } else { $py }
$cmd = "$pyExecForTask `"$WS\scripts\flow_queue_worker.py`""
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $cmd"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$taskOk = $false
try {
  try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  } catch {}
  Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Flow Auto Worker" | Out-Null
  Start-ScheduledTask -TaskName $taskName
  $taskOk = $true
  Write-Host "[ok] Scheduled Task created: $taskName"
} catch {
  Write-Warning "Register-ScheduledTask failed: $($_.Exception.Message)"
  Write-Warning "Fallback: tạo startup script trong Startup folder user hiện tại"
}

if (-not $taskOk) {
  $startupDir = [Environment]::GetFolderPath('Startup')
  New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
  $startupCmd = Join-Path $startupDir "FlowAutoWorker.cmd"
  $pyArgsText = if ($py -eq "py") { "-3" } else { "" }
  @"
@echo off
set WS=$WS
set PY=$py
set PY_ARGS=$pyArgsText
if not exist "%WS%\scripts\flow_queue_worker.py" exit /b 0
%PY% %PY_ARGS% "%WS%\scripts\flow_queue_worker.py"
"@ | Out-File -FilePath $startupCmd -Encoding ascii -Force

  # start now (no need to wait next logon)
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$startupCmd`"" -WindowStyle Minimized | Out-Null
  Write-Host "[ok] Startup fallback created: $startupCmd"
}

Write-Host "[DONE] Flow Auto Video Pro V1.0.2 Windows (compat) installed"
Write-Host "Workspace: $WS"
Write-Host "Inbound: $INBOUND"
