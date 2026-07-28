# SIS Clima-Saúde MT

Ferramenta para monitoramento de ondas de calor e apoio à tomada de decisão em saúde pública.

## Execução local

streamlit run streamlit_app.py

## Streamlit Community Cloud

- Main file path: streamlit_app.py
- Configure secrets no painel do Streamlit Cloud.
- Não commitar .env, secrets.toml, bancos SQLite, contatos, logs ou dados operacionais locais.

## GeoCalor cardiorrespiratório

O módulo calcular_geocalor_cardioresp_v11_12.py calcula RR por lag 0-7 quando existir base diária com cod_ibge, data, isHW, internacoes_cardio, internacoes_resp, obitos_cardio e obitos_resp.

Sem essa base diária, o sistema registra status de dados insuficientes e não inventa RR.
