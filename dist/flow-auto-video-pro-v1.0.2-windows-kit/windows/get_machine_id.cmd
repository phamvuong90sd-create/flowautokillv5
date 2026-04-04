@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

set "WS=%USERPROFILE%\.openclaw\workspace"
set "OUT=%WS%\keys\machine-id.txt"
set "MID="

if not exist "%WS%\keys" mkdir "%WS%\keys" >nul 2>&1

rem 1) Registry MachineGuid (ổn định nhất)
for /f "tokens=3" %%A in ('reg query "HKLM\SOFTWARE\Microsoft\Cryptography" /v MachineGuid 2^>nul ^| find /i "MachineGuid"') do (
  set "MID=%%A"
)

rem 2) WMIC fallback (nếu còn trên máy)
if not defined MID (
  for /f "tokens=2 delims==" %%A in ('wmic csproduct get uuid /value 2^>nul ^| find "UUID="') do (
    set "MID=%%A"
  )
)

rem 3) Hostname fallback
if not defined MID (
  set "MID=%COMPUTERNAME%"
)

if not defined MID (
  echo [ERROR] Khong lay duoc Machine ID.
  echo Thu chay CMD voi quyen Administrator.
  exit /b 1
)

rem normalize lowercase (basic)
for %%L in (A=a B=b C=c D=d E=e F=f G=g H=h I=i J=j K=k L=l M=m N=n O=o P=p Q=q R=r S=s T=t U=u V=v W=w X=x Y=y Z=z) do set "MID=!MID:%%L!"

echo !MID!>"%OUT%"

echo Machine ID: !MID!
echo Saved: %OUT%
echo.
echo Gui Machine ID nay de tao LICENSE_KEY.
exit /b 0
