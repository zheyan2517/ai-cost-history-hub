@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set "AGENT_COST_DASHBOARD_DIR=%~dp0agent"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%~dp0scripts\coordinator.py" open-cost
  set "ERR=%ERRORLEVEL%"
  if not "%ERR%"=="0" (
    echo.
    echo [ERROR] Could not open cost dashboard (exit %ERR%).
    echo Install Python 3.12+ and add it to PATH if missing:
    echo   https://www.python.org/downloads/
    echo If a port is busy:  python scripts\coordinator.py stop
    pause
  )
  exit /b %ERR%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0scripts\coordinator.py" open-cost
  set "ERR=%ERRORLEVEL%"
  if not "%ERR%"=="0" (
    echo.
    echo [ERROR] Could not open cost dashboard (exit %ERR%).
    echo Install Python 3.12+ and add it to PATH if missing:
    echo   https://www.python.org/downloads/
    echo If a port is busy:  python scripts\coordinator.py stop
    pause
  )
  exit /b %ERR%
)

echo.
echo [ERROR] Python 3.12+ was not found on PATH.
echo Install from https://www.python.org/downloads/ ^(enable Add to PATH^)
echo Then open a NEW terminal and re-run this script.
echo.
pause
exit /b 1
