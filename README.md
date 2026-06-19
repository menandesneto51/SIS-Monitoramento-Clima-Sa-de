# SIS Clima-Saúde MT — Streamlit Cloud

Versão cloud preservando o painel original local.

## Main file path

`streamlit_app.py`

## Dados

A pasta `data/output` contém apenas `sis_integrado.db` sanitizado, com tabelas agregadas/operacionais necessárias ao painel.  
Não inclui `.env`, tokens, contatos, logs, histórico de envio, bases locais brutas ou credenciais.

## Atualização

Na pasta operacional local, rode:

`RESTAURAR_PAINEL_ORIGINAL_STREAMLIT_CLOUD_V11_25.cmd`

Depois, na pasta cloud, rode:

`SUBIR_STREAMLIT_CLOUD_ORIGINAL_GITHUB_V11_25.cmd`

Se houver rejeição por histórico remoto e você quiser substituir o remoto:

`FORCE_PUSH_STREAMLIT_CLOUD_ORIGINAL_V11_25.cmd`
