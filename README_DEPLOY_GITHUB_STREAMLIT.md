# SIS Clima-Saúde MT

Ferramenta para monitoramento de ondas de calor e apoio à tomada de decisão em saúde pública.

## Execução local

```bash
streamlit run streamlit_app.py
```

## Arquivos de entrada

Não subir ao GitHub arquivos com dados sensíveis, credenciais, `.env`, contatos ou bancos SQLite operacionais.

## Deploy no Streamlit Community Cloud

1. Repositório: https://github.com/menandesneto51/SIS-Monitoramento-Clima-Sa-de
2. Abrir https://share.streamlit.io → app existente ou **New app**
3. Configurar:
   - Repository: `menandesneto51/SIS-Monitoramento-Clima-Sa-de`
   - Branch: **`painel-v9`**
   - Main file path: `streamlit_app.py`
   - Python version (Advanced): **3.12** (repo já tem `.python-version` / `runtime.txt`)
4. Em **Advanced settings → Secrets**, colar o conteúdo de `.streamlit/secrets.toml.example` e definir:
   - `DATABASE_URL` apontando para um **Postgres acessível na internet** (Neon/Supabase/Railway).  
     `localhost` / Docker da máquina **não funciona** no Cloud.
5. Deploy / **Reboot** → aguardar build.

Dependências Cloud: `requirements.txt` enxuto (sem Fiona/GDAL/Google gRPC). Lista completa local: `requirements-full.txt`.  
**Não** use `packages.txt` com comentários — o apt do Cloud interpreta cada palavra como pacote.

Sem `DATABASE_URL` no Cloud, o painel usa o snapshot `data/cloud/sis_cloud_seed.db` (KPIs/abas).  
Atualizar snapshot local: `.\\.venv\\Scripts\\python.exe exportar_snapshot_cloud.py` e push em `painel-v9`.
