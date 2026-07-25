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
  set "ERR=%ERRORLEVEL%"
  if not "%ERR%"=="0" (
    echo.
    echo [ERROR] Launcher failed with exit code %ERR%.
    echo If Python is missing, install 3.12+ from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then open a NEW terminal.
    echo If ports are busy:  python scripts\coordinator.py stop
    echo Or check:  netstat -ano ^| findstr ":8753 :8740"
    echo See README Troubleshooting for more.
    pause
  )
  exit /b %ERR%
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python "%~dp0scripts\coordinator.py" start --portal
  set "ERR=%ERRORLEVEL%"
  if not "%ERR%"=="0" (
    echo.
    echo [ERROR] Launcher failed with exit code %ERR%.
    echo If Python is missing, install 3.12+ from https://www.python.org/downloads/
    echo and enable "Add python.exe to PATH", then open a NEW terminal.
    echo If ports are busy:  python scripts\coordinator.py stop
    echo Or check:  netstat -ano ^| findstr ":8753 :8740"
    echo See README Troubleshooting for more.
    pause
  )
  exit /b %ERR%
)

echo.
echo [ERROR] Python 3.12+ was not found on PATH.
echo.
echo Next steps:
echo   1. Install Python 3.12+ from https://www.python.org/downloads/
echo   2. Enable: "Add python.exe to PATH"
echo   3. Open a NEW terminal
echo   4. Verify:  py -3 --version   or   python --version
echo   5. Re-run start.bat
echo.
pause
exit /b 1
