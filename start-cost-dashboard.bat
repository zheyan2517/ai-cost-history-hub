@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set "AGENT_COST_DASHBOARD_DIR=%~dp0agent"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0scripts\coordinator.py" open-cost
  exit /b %ERRORLEVEL%
)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0scripts\coordinator.py" open-cost
  exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3.12+ not found.
pause
exit /b 1
