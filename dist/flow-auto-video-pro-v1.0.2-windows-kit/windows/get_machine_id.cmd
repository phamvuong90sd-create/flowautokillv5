@echo off
setlocal

title Flow Auto - Get Machine ID
set "MID="

REM 1) PowerShell MachineGuid (most reliable when available)
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$x=''; try{$x=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography' -Name MachineGuid -ErrorAction Stop).MachineGuid}catch{}; if([string]::IsNullOrWhiteSpace($x)){try{$x=(Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue).UUID}catch{}}; if([string]::IsNullOrWhiteSpace($x)){$x=$env:COMPUTERNAME}; $x.ToString().Trim().ToLower()" 2^>nul`) do set "MID=%%A"

REM 2) Registry fallback via reg query
if "%MID%"=="" (
  for /f "tokens=1,2,*" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Cryptography" /v MachineGuid 2^>nul ^| findstr /I "MachineGuid"') do set "MID=%%C"
)

REM 3) WMIC fallback
if "%MID%"=="" (
  for /f "tokens=2 delims==" %%A in ('wmic csproduct get uuid /value 2^>nul ^| find "UUID="') do set "MID=%%A"
)

REM 4) Hostname fallback (guaranteed non-empty on normal Windows)
if "%MID%"=="" set "MID=%COMPUTERNAME%"

REM trim spaces
for /f "tokens=* delims= " %%A in ("%MID%") do set "MID=%%A"

if "%MID%"=="" (
  cls
  echo ========================================
  echo        FLOW AUTO - MACHINE ID
  echo ========================================
  echo.
  echo [ERROR] Khong lay duoc Machine ID.
  echo Hay chay CMD bang Run as administrator.
  echo.
  pause
  exit /b 1
)

cls
echo ========================================
echo        FLOW AUTO - MACHINE ID
echo ========================================
echo.
echo %MID%
echo.
echo ========================================
echo Sao chep dong ma tren de tao LICENSE_KEY
echo.
pause
exit /b 0
