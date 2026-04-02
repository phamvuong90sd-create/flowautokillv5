@echo off
setlocal
set WS=%USERPROFILE%\.openclaw\workspace
if not "%FLOW_WORKSPACE%"=="" set WS=%FLOW_WORKSPACE%

set PY=python
set PY_ARGS=
where py >nul 2>nul
if %errorlevel%==0 (
  set PY=py
  set PY_ARGS=-3
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set PY=python
  ) else (
    set PY=python3
  )
)

%PY% %PY_ARGS% "%WS%\scripts\flow_queue_worker.py"
