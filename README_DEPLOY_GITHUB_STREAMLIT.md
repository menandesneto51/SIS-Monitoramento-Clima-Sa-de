# ARARAS MT — implantação do painel

![ARARAS MT](assets/branding/araras-mt-logo-horizontal.png)

Plataforma para monitoramento integrado de clima, ambiente, agravos e saúde, com apoio à análise e à tomada de decisão em saúde pública.

## Execução local (rápido)

```bash
# Linux/macOS
chmod +x configurar_painel.sh && ./configurar_painel.sh

# Windows
configurar_painel.bat
```

Ou manualmente:

```bash
streamlit run streamlit_app.py
```

Defaults CIEVS aplicados pelo script:
- `ALERT_CENTRAL_ONLY_SES=true` → e-mail/Telegram centrais recebem **somente** o alerta estadual
- `ALERT_FANOUT_ENABLED=false` até existir `data/input/contatos_alertas.csv`
- `SEND_ALERT_ON_LEVEL_CHANGE=false` (seguro) até validar na aba **Alertas**
- `ALERT_EMAIL_TO=notifica@ses.mt.gov.br` (adicione seu e-mail pessoal no `.env` se quiser)

## Arquivos de entrada

Não subir ao GitHub arquivos com dados sensíveis, credenciais, `.env`, contatos ou bancos SQLite operacionais.

## Deploy no Streamlit Community Cloud

**Manter apenas 1 app** deste repositório no https://share.streamlit.io:

| Manter | Apagar |
|--------|--------|
| Branch **`painel-v9`** · `streamlit_app.py` | Branch **`main`** · `streamlit_app.py` (deps pesadas / pasta `pages/` / painel antigo) |

1. Em https://share.streamlit.io, no app da branch **`main`**: menu **⋯** → **Delete app**
2. No app da branch **`painel-v9`**: menu **⋯** → **Reboot app** (ou **Manage app** → logs, se o ícone vermelho persistir)
3. Configuração correta do app único:
   - Repository: `menandesneto51/SIS-Monitoramento-Clima-Sa-de`
   - Branch: **`painel-v9`**
   - Main file path: `streamlit_app.py`
   - Python version (Advanced): **3.12** (preferencial). O Cloud **ignora** `runtime.txt`; se ficar em 3.14, o `requirements.txt` já usa wheels compatíveis (`psycopg2-binary>=2.9.12`, `pyarrow>=25`).
4. Em **Advanced settings → Secrets**, colar o conteúdo de `.streamlit/secrets.toml.example` e definir:
   - `ALERT_EMAIL_TO` = `seu_email,notifica@ses.mt.gov.br`
   - `ALERT_CENTRAL_ONLY_SES` = `"true"`
   - `ALERT_FANOUT_ENABLED` = `"false"`
   - `DATABASE_URL` apontando para um **Postgres acessível na internet** (Neon/Supabase/Railway), se quiser dados ao vivo.
     `localhost` / Docker da máquina **não funciona** no Cloud.
5. Aguardar o build ficar verde e abrir o link do app.

Dependências Cloud: `requirements.txt` enxuto (sem Fiona/GDAL/Google gRPC). Lista completa local: `requirements-full.txt`.
**Não** use `packages.txt` com comentários — o apt do Cloud interpreta cada palavra como pacote.

Sem `DATABASE_URL` no Cloud, o painel usa o snapshot `data/cloud/sis_cloud_seed.db` (KPIs/abas).
Atualizar snapshot local: `.\\.venv\\Scripts\\python.exe exportar_snapshot_cloud.py` e push em `painel-v9`.

## Docker (servidor SES — painel + agendador diário)

```bash
docker compose up -d db app landing alerts-scheduler
# entrada (landing): http://localhost/  (LANDING_PORT=80)
# painel: http://localhost:8501
```
