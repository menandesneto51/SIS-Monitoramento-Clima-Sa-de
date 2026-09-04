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
| `http://10.15.0.131/` (porta **80**, ou `LANDING_PORT`) | Esta pasta (`index.html`, `styles.css`, `app.js`, `assets/`, `paineis/`) |
| `http://10.15.0.131/paineis/` | Hub dos módulos temáticos (CE, AR, AS, AF, RT, SS) |
| `http://10.15.0.131:8501/` | Painel Streamlit |
| `http://10.15.0.131:8501/?aba=ar` | Deep-link para aba (aliases: `ce`, `ar`, `as`, `rt`, `assistencia`, `sala`, `visao`) |

Se a porta 80 estiver ocupada no host: `LANDING_PORT=8080 docker compose up -d landing`.

A base do painel nos CTAs pode ser trocada com `data-panel-base` no `<html>` ou `?painel=` na URL do site.

## Produção (STI)

- Document root: esta pasta (`index.html`, `styles.css`, `app.js`, `assets/`, `paineis/`)
- HTTPS institucional + DNS `araras.saude.mt.gov.br`
- Painel interno: Streamlit `:8501` (somente rede SES) — CTAs e cards apontam para `http://10.15.0.131:8501/?aba=…`
