@echo off
setlocal
set WS=%USERPROFILE%\.openclaw\workspace
if not "%FLOW_WORKSPACE%"=="" set WS=%FLOW_WORKSPACE%

where py >nul 2>nul
if %errorlevel%==0 (
  set PY=py
) else (
  set PY=python
)

%PY% "%WS%\scripts\flow_queue_worker.py"
