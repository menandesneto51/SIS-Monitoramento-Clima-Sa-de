# Site institucional ARARAS MT

Pacote estático para publicação SES/STI no hostname solicitado: **https://araras.saude.mt.gov.br/**

## Abrir localmente

```bash
python -m http.server 8080 --directory sites/araras-mt
```

## Produção (STI)

- Document root: esta pasta (`index.html`, `styles.css`, `app.js`, `assets/`)
- HTTPS institucional + DNS `araras.saude.mt.gov.br`
- Painel interno (opcional): `araras-painel.saude.mt.gov.br` → Streamlit `:8501` (somente rede SES)
