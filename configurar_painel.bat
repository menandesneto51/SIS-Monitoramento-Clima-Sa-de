@echo off
REM Configura o painel Streamlit local (Windows) com defaults CIEVS.
cd /d "%~dp0"

if not exist ".env" (
  echo Criando .env a partir de .env.example ...
  copy /Y ".env.example" ".env" >nul
)

if not exist ".streamlit\secrets.toml" (
  echo Criando .streamlit\secrets.toml a partir do exemplo ...
  copy /Y ".streamlit\secrets.toml.example" ".streamlit\secrets.toml" >nul
)

REM Defaults de roteamento CIEVS (nao sobrescreve se ja existirem no .env)
findstr /B /C:"ALERT_CENTRAL_ONLY_SES=" ".env" >nul || echo ALERT_CENTRAL_ONLY_SES=true>> ".env"
findstr /B /C:"ALERT_FANOUT_ENABLED=" ".env" >nul || echo ALERT_FANOUT_ENABLED=false>> ".env"
findstr /B /C:"SEND_ALERT_ON_LEVEL_CHANGE=" ".env" >nul || echo SEND_ALERT_ON_LEVEL_CHANGE=false>> ".env"
findstr /B /C:"ALERT_INTERVAL_HOURS=" ".env" >nul || echo ALERT_INTERVAL_HOURS=24>> ".env"
findstr /B /C:"ALERT_EMAIL_TO=" ".env" >nul || echo ALERT_EMAIL_TO=notifica@ses.mt.gov.br>> ".env"

if not exist ".venv\Scripts\python.exe" (
  echo Criando venv e instalando dependencias ...
  py -3.12 -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install -U pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

echo.
echo Painel: http://localhost:8501
echo Aba Alertas: canal central = somente estadual; fan-out territorial adiado ate a planilha.
echo.
streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501
