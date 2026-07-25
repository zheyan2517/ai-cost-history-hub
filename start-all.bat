@echo off
setlocal
cd /d "%~dp0"

echo === Wangquanti unified launcher (Scheme A: CCHV + Cost sidecar) ===
echo.

REM 1) Start Agent Cost Dashboard on 127.0.0.1 only
call "%~dp0start-cost-dashboard.bat"

echo.
echo 2) CCHV desktop app
echo    - Dev:   cd claude ^&^& pnpm install ^&^& pnpm tauri:dev
echo    - Build: cd claude ^&^& pnpm tauri:build
echo    - Or open the installed Claude Code History Viewer, then click the wallet icon "Cost Dashboard"
echo.
echo Tips:
echo    - Cost dashboard binds ONLY to 127.0.0.1 (not exposed to LAN)
echo    - Override agent path: set AGENT_COST_DASHBOARD_DIR=%~dp0agent
echo.
endlocal
