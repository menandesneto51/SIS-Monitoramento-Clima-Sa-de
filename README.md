# SIS Clima-Saúde MT — Streamlit Cloud

Versão cloud preservando o painel original local.

## Main file path

`streamlit_app.py`

## Dados

A pasta `data/output` contém apenas `sis_integrado.db` sanitizado, com tabelas agregadas/operacionais necessárias ao painel.  
Não inclui `.env`, tokens, contatos, logs, histórico de envio, bases locais brutas ou credenciais.

## Alertas por WhatsApp

O canal de WhatsApp usa provedores gratuitos (Cloud API da Meta, Evolution API auto-hospedada,
CallMeBot ou ponte por webhook). Para configurar, abra a página **Configurar WhatsApp** no painel
ou rode `python -m sisclima.alerts.whatsapp_agent diagnostico`.

- **Tutorial passo a passo (Meta + número no WhatsApp Business):**
  [`docs/TUTORIAL_WHATSAPP_META_CLOUD.md`](docs/TUTORIAL_WHATSAPP_META_CLOUD.md)
- **Referência geral dos provedores:** [`docs/WHATSAPP_GRATUITO.md`](docs/WHATSAPP_GRATUITO.md)

## Atualização

Na pasta operacional local, rode:

`RESTAURAR_PAINEL_ORIGINAL_STREAMLIT_CLOUD_V11_25.cmd`

Depois, na pasta cloud, rode:

`SUBIR_STREAMLIT_CLOUD_ORIGINAL_GITHUB_V11_25.cmd`

Se houver rejeição por histórico remoto e você quiser substituir o remoto:

`FORCE_PUSH_STREAMLIT_CLOUD_ORIGINAL_V11_25.cmd`
