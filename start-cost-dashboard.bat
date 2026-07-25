@echo off
setlocal
cd /d "%~dp0agent"

set "HOST=127.0.0.1"
set "PORT=8753"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  start "Agent Cost Dashboard" /MIN py -3 cost_dashboard.py --host %HOST% --port %PORT%
) else (
  where python >nul 2>nul
  if %ERRORLEVEL%==0 (
    start "Agent Cost Dashboard" /MIN python cost_dashboard.py --host %HOST% --port %PORT%
  ) else (
    echo [ERROR] Python 3.12+ not found. Install Python and retry.
    pause
    exit /b 1
  )
)

timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:%PORT%/"
echo Cost dashboard: http://127.0.0.1:%PORT%/  (bound to loopback only)
endlocal
