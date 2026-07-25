@echo off
setlocal
set PYTHONUTF8=1
title agent-cost-dashboard
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 cost_dashboard.py --host 127.0.0.1 --port 8753
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python cost_dashboard.py --host 127.0.0.1 --port 8753
  exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3.12+ not found. Install Python and retry.
pause
exit /b 1
