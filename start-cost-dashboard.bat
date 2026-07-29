@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set PYTHONUTF8=1
set "AGENT_COST_DASHBOARD_DIR=%~dp0agent"

where py >nul 2>nul
if not errorlevel 1 goto use_py

where python >nul 2>nul
if not errorlevel 1 goto use_python

goto python_missing

:use_py
py -3 "%~dp0scripts\coordinator.py" open-cost
set "ERR=%ERRORLEVEL%"
goto report_result

:use_python
python "%~dp0scripts\coordinator.py" open-cost
set "ERR=%ERRORLEVEL%"
goto report_result

:report_result
if "%ERR%"=="0" exit /b 0
echo.
echo [ERROR] Could not open cost dashboard (exit %ERR%).
echo Install Python 3.12+ and add it to PATH if missing:
echo   https://www.python.org/downloads/
echo If a port is busy:  python scripts\coordinator.py stop
exit /b %ERR%

:python_missing
echo.
echo [ERROR] Python 3.12+ was not found on PATH.
echo Install from https://www.python.org/downloads/ ^(enable Add to PATH^)
echo Then open a NEW terminal and re-run this script.
echo.
exit /b 1
