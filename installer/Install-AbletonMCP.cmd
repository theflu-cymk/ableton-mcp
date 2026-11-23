@echo off
setlocal
set "SCRIPT=%~dp0AbletonMCP-Setup.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" (
  echo AbletonMCP setup failed with exit code %CODE%.
  echo See %LOCALAPPDATA%\AbletonMCP\logs\install.log for details.
)
pause
exit /b %CODE%
