# Site institucional ARARAS MT

Pacote estático para publicação SES/STI no hostname solicitado: **https://araras.saude.mt.gov.br/**

## Abrir localmente

```bash
python -m http.server 8080 --directory sites/araras-mt
```

## Produção (Docker no servidor SES)

```bash
docker compose up -d landing app
```

| URL | Conteúdo |
|-----|----------|
| `http://10.15.0.131/` (porta **80**, ou `LANDING_PORT`) | Esta pasta (`index.html`, `styles.css`, `app.js`, `assets/`) |
| `http://10.15.0.131:8501/` | Painel Streamlit |

Se a porta 80 estiver ocupada no host: `LANDING_PORT=8080 docker compose up -d landing`.

## Produção (STI)

- Document root: esta pasta (`index.html`, `styles.css`, `app.js`, `assets/`)
- HTTPS institucional + DNS `araras.saude.mt.gov.br`
- Painel interno: Streamlit `:8501` (somente rede SES) — CTAs da landing apontam para `http://10.15.0.131:8501/`
