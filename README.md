# SIS-MT Clima-Saúde — Sistema Integrado Real para Mato Grosso

Sistema Python/Streamlit para monitoramento em tempo real de risco climático-sanitário no Estado de Mato Grosso, consolidando componentes usados nos projetos TITAN, SENTINELA, AESOP, SIVEP/SRAG, LACEN/GAL, SINAN, SIM, CNES/IndicaSUS e Vigidesastres.

## O que esta versão faz

- Municipaliza os dados por `cod_ibge` e `municipio`.
- Baixa ou atualiza a base municipal de MT pelo IBGE.
- Integra qualidade do ar por Copernicus/CAMS: PM2.5, PM10, O3, NO2, CO e SO2.
- Usa meteorologia operacional por Open-Meteo como fallback e mantém acoplamento Copernicus/ERA5-Land.
- Integra IndicaSUS/leitos, SIVEP/SRAG (indicadores MS), sentinela SG, LACEN/GAL, SINAN, SIM, SENTINELA, Cemaden, ANA, estoque, infraestrutura, busca ativa e comunicação.
- Classifica níveis Verde, Amarela, Laranja, Vermelha e Roxa.
- Envia alerta por mudança de nível via e-mail, Telegram e webhook.
- Gera boletim operacional auditável com camada opcional de IA.
- Apresenta painel Streamlit com situação estadual, municípios prioritários, qualidade do ar, assistência, leitos, infraestrutura, insumos, busca ativa, recomendações e auditoria.

## Instalação rápida no Windows

```bat
copy .env.producao.example .env
instalar.bat
preparar_municipios_ibge.bat
validar_fontes_reais.bat
rodar_ciclo_real.bat
abrir_painel.bat
```

## Operação contínua

```bat
rodar_producao_tempo_real.bat
```

O intervalo é configurado em `.env`:

```env
RUN_REALTIME_INTERVAL_MINUTES=60
```

## Dados reais

A pasta `data/input/` é reservada para bases reais. O script `criar_dados_exemplo.py` existe apenas para teste local e não deve ser usado em produção.

Para detalhes, leia `docs/IMPLEMENTACAO_REAL_MT.md`.


## V4 — Ajuste operacional SES/MT

- IndicaSUS, CNES, SINAN, SIM e GAL/LACEN via Data Warehouse (`DW_` no `.env`).
- SIVEP/SRAG via banco local em `data/local/sivep/sivep_srag_local.db`, atualizado a partir de `data/input/sivep_atualizacao/`.
- Base territorial municipal MT 2025 já incorporada.
- Documentação: `docs/FONTES_REAIS_DW_SIVEP_LOCAL.md`.

## Docker + base única (PostgreSQL)

A base operacional única fica no Postgres (`sis_clima_saude`). O DW continua só como fonte de leitura.

```powershell
copy .env.example .env
docker compose up -d db
docker compose up -d --build
```

Detalhes: `docs/DOCKER_BASE_UNICA.md`.

Fluxo rápido:

```bat
copy .env.producao.example .env
instalar.bat
atualizar_sivep_local.bat
validar_dw_sivep.bat
rodar_ciclo_real.bat
abrir_painel.bat
```


## Uso com `.env` já configurado

Esta versão aceita o `.env` no padrão usado nos projetos anteriores. Não substitua o seu `.env` por `.env.example`. Rode:

```bat
validar_env_existente.bat
```

O sistema reconhece aliases para DW/SQL Server, Copernicus/CDS/ADS, Telegram, SMTP, shapefile municipal, população e SIVEP local. A documentação está em `docs/ENV_EXISTENTE_COMPATIBILIDADE.md`.
