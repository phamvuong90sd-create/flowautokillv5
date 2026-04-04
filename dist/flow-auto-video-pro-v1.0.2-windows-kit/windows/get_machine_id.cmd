@echo off
setlocal ENABLEEXTENSIONS

set "WS=%USERPROFILE%\.openclaw\workspace"
set "OUT=%WS%\keys\machine-id.txt"
set "TMP_PS=%TEMP%\flow_get_mid_%RANDOM%.ps1"

if not exist "%WS%\keys" mkdir "%WS%\keys" >nul 2>&1

(
  echo $ErrorActionPreference = 'SilentlyContinue'
  echo $machineId = ''
  echo $verify = Join-Path $env:USERPROFILE '.openclaw\workspace\scripts\bin\flow_license_verify'
  echo if (Test-Path $verify^) { try { $machineId = (^& $verify --machine-id ^| Out-String^).Trim^(^).ToLower^(^) } catch {} }
  echo if (-not $machineId^) { try { $machineId = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid^).MachineGuid.ToLower^(^).Trim^(^) } catch {} }
  echo if (-not $machineId^) { try { $uuid = (Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue^).UUID; if ($uuid^) { $machineId = $uuid.ToLower^(^).Trim^(^) } } catch {} }
  echo if (-not $machineId^) { $machineId = $env:COMPUTERNAME.ToLower^(^).Trim^(^) }
  echo if (-not $machineId^) { exit 2 }
  echo Set-Content -Path "%OUT%" -Value $machineId -Encoding ascii -Force
  echo Write-Output $machineId
) > "%TMP_PS%"

for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%TMP_PS%"`) do set "MID=%%i"
del "%TMP_PS%" >nul 2>&1

if "%MID%"=="" (
  echo [ERROR] Khong lay duoc Machine ID.
  echo Thu chay lai CMD voi quyen Administrator.
  exit /b 1
)

echo Machine ID: %MID%
echo Saved: %OUT%
echo.
echo Gui Machine ID nay de tao LICENSE_KEY.
exit /b 0
