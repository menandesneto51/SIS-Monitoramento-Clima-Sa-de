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
2. Abrir https://share.streamlit.io → **New app**
3. Configurar:
   - Repository: `menandesneto51/SIS-Monitoramento-Clima-Sa-de`
   - Branch: `main` (ou `painel-v9` se ainda não mergeado)
   - Main file path: `streamlit_app.py`
4. Em **Advanced settings → Secrets**, colar o conteúdo de `.streamlit/secrets.toml.example` e definir:
   - `DATABASE_URL` apontando para um **Postgres acessível na internet** (Neon/Supabase/Railway).  
     `localhost` / Docker da máquina **não funciona** no Cloud.
5. Deploy → aguardar build.

Sem `DATABASE_URL` válido no Cloud, o painel sobe em fallback SQLite vazio (sem dados do CIEVS).
