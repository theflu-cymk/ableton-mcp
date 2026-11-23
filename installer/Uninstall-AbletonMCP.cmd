@echo off
setlocal
set "SCRIPT=%~dp0AbletonMCP-Setup.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Uninstall %*
set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%
