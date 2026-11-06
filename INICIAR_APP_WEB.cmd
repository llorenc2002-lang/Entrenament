@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_APP_WEB.ps1"
if errorlevel 1 (
  echo La app web se ha detenido con un error. Revisa el mensaje anterior.
  pause
)
endlocal
