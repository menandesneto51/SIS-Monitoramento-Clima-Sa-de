@echo off
REM Digest de alertas SES/CIEVS (uma vez)
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m sisclima.alerts.scheduler --once
) else if exist "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" -m sisclima.alerts.scheduler --once
) else (
  python -m sisclima.alerts.scheduler --once
)
exit /b %ERRORLEVEL%
