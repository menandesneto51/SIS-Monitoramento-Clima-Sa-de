@echo off
REM Regeneracao / ciclo operacional diario (Agendador Windows)
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" rotina_diaria_ops.py %*
) else if exist "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" rotina_diaria_ops.py %*
) else (
  python rotina_diaria_ops.py %*
)
exit /b %ERRORLEVEL%
