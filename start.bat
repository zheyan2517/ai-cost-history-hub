@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title AI Cost History Hub
set PYTHONUTF8=1
set "AGENT_COST_DASHBOARD_DIR=%~dp0agent"

echo.
echo  ============================================
echo   AI Cost History Hub
echo   Local history and cost analytics
echo  ============================================
echo.

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0scripts\coordinator.py" start --portal
  exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0scripts\coordinator.py" start --portal
  exit /b %ERRORLEVEL%
)

echo [ERROR] Python 3.12+ not found.
echo Install from https://www.python.org/downloads/ and re-run.
pause
exit /b 1
