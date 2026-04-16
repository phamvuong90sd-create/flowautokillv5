@echo off
setlocal

where makensis >nul 2>nul
if errorlevel 1 (
  echo [ERROR] NSIS (makensis) not found. Please install NSIS first.
  echo Download: https://nsis.sourceforge.io/Download
  pause
  exit /b 1
)

cd /d %~dp0
makensis FlowAutoPro_Windows.nsi
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo [DONE] Built FlowAutoPro_v3.0.1_Setup.exe
pause
