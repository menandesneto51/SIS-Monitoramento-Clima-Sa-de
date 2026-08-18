@echo off
REM Reconstroi o banco local SIVEP a partir de data\input\sivep_atualizacao
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "from sisclima.ingestion.sivep_local import rebuild_sivep_local_db; import json; print(json.dumps(rebuild_sivep_local_db(), ensure_ascii=False, indent=2))"
) else if exist "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\araras-mt-venv\Scripts\python.exe" -c "from sisclima.ingestion.sivep_local import rebuild_sivep_local_db; import json; print(json.dumps(rebuild_sivep_local_db(), ensure_ascii=False, indent=2))"
) else (
  python -c "from sisclima.ingestion.sivep_local import rebuild_sivep_local_db; import json; print(json.dumps(rebuild_sivep_local_db(), ensure_ascii=False, indent=2))"
)
exit /b %ERRORLEVEL%
