# Inventário do Sistema — VIGIA / SIS Clima-Saúde MT

> Documento de referência para continuidade do projeto.  
> Gerado em: 2026-07-23  
> Repositório: `menandesneto51/SIS-Monitoramento-Clima-Sa-de`

---

## 1. Visão geral

O **VIGIA Clima-Saúde MT** (também chamado **SIS Integrado Clima-Saúde MT**) é um sistema de vigilância integrada de clima e saúde para o estado de Mato Grosso. Cruza dados meteorológicos, qualidade do ar, pressão assistencial, epidemiologia e operações para classificar municípios em níveis de risco operacional (verde → roxa) e apoiar a gestão em eventos de calor extremo.

### Propósito operacional

- Monitorar **142 municípios** de MT com indicadores biometeorológicos, assistenciais e epidemiológicos.
- Classificar risco municipal e estadual segundo limiares definidos em `config/settings.yaml`.
- Disponibilizar painel web (Streamlit) para sala de situação e gestores.
- Suportar alertas automáticos (e-mail, Telegram, webhook) em mudanças de nível crítico.
- Integrar fontes reais (DW SES/MT, SIVEP local, Copernicus, INMET, Open-Meteo) via pipeline Python.

### Regra decisória central

O nível final do município é o **maior** entre os domínios avaliados:

```
nivel_final = max(nivel_clima, nivel_assistencia, nivel_leitos, nivel_infra,
                  nivel_estoque, nivel_sentinela, nivel_mortalidade, nivel_inmet)
```

---

## 2. Estrutura do repositório

```
/workspace
├── streamlit_app.py              # Entrada Streamlit Cloud (roteador)
├── app_vigia_sistema_completo_validado.py  # Painel cloud ativo (CSV)
├── app_v9.py / app_v8.py / app_v6.py / app.py  # Versões anteriores (SQLite)
├── pages/                        # Páginas multipage Streamlit
├── sisclima/                     # Pacote Python (pipeline + engines)
├── config/                       # settings.yaml, sources_real.yaml
├── data/
│   ├── public/                   # CSVs/GeoJSON publicados no cloud
│   ├── output/sis_integrado.db   # Banco sanitizado (13 MB, 60 tabelas)
│   ├── sample/                   # Dados demo para pipeline local
│   ├── geo/                      # Shapefile municipal MT 2025
│   └── processed/                # GeoJSON processados
├── sql/                          # Queries DW SES/MT
├── docs/                         # Documentação técnica
└── requirements.txt              # Dependências Python (124 pacotes)
```

---

## 3. Aplicações Streamlit

### 3.1 Roteador (`streamlit_app.py`)

Ponto de entrada do **Streamlit Community Cloud**. Tenta carregar apps nesta ordem:

1. `app_vigia_sistema_completo_validado.py` ← **ativo em produção**
2. `app_v9.py`
3. `app_v8.py`
4. `app_v6.py`

### 3.2 Evolução das versões

| Arquivo | Linhas | Backend | Abas | Uso recomendado |
|---------|--------|---------|------|-----------------|
| `app.py` | ~282 | SQLite via `sisclima.core.db` | 10 | Ambiente local com pipeline ao vivo |
| `app_v6.py` | ~1.165 | SQLite direto | 10 | Mapas choropleth (shapefile) |
| `app_v8.py` | ~1.365 | SQLite direto | 10 | V6 + análise estatística clima-saúde |
| `app_v9.py` | ~1.468 | SQLite direto | 10 | V8 + epidemiologia temporal (V9) |
| `app_vigia_sistema_completo_validado.py` | ~429 | `data/public` CSV | 11 | **Streamlit Cloud** |

### 3.3 Painel ativo — VIGIA validado

**Arquivo:** `app_vigia_sistema_completo_validado.py`

**Abas:**

| # | Aba | Conteúdo |
|---|-----|----------|
| 1 | Sumário Executivo | Distribuição por cor de risco, métricas, mapa municipal |
| 2 | Território e Mapas | Camadas geográficas |
| 3 | Município / Regional | Detalhe territorial com filtros |
| 4 | Pressão Assistencial | Ocupação hospitalar, CNES |
| 5 | Saúde | Epidemiologia, priorização V9 |
| 6 | Clima e Ar | Biometeorologia, qualidade do ar |
| 7 | Vulnerabilidade | Índices de vulnerabilidade |
| 8 | Predição e Alertas | Predição 7d, alerta inteligente V6 |
| 9 | GeoCalor | Cardiorrespiratório (Cuiabá + municipal) |
| 10 | Catálogo de Indicadores | Inventário de bases e colunas |
| 11 | Administração Técnica | Arquivos publicados, status |

**Filtros sidebar:** Regional de Saúde, Município.

**Correções validadas (v11):**
- Usa exclusivamente `data/public`
- GeoJSON municipal por `cod_ibge`
- GeoCalor Cuiabá com fallback em cadeia
- Filtro municipal robusto (nome, cod_ibge, fallback sem erro)

### 3.4 Páginas multipage (`pages/`)

| Arquivo | Backend | Função |
|---------|---------|--------|
| `10_GeoCalor_Cardiorrespiratorio.py` | SQLite (`geocalor_*`) | Ondas de calor × hospitalizações/óbitos cardiorrespiratórios |
| `12_Alertas_Agendados_VIGIA.py` | `data/public` CSV | Alertas agendados (estado, regionais, Cuiabá) |

> **Nota:** As páginas multipage só aparecem quando o app principal é executado como projeto multipage. O roteador atual (`runpy`) carrega um único app monolítico.

---

## 4. Pacote `sisclima/` — Motor de dados

### 4.1 Módulos

| Módulo | Responsabilidade |
|--------|------------------|
| `pipeline.py` | Orquestrador principal — `run_pipeline(send_alerts=True)` |
| `core/config.py` | Carrega `.env` + `config/settings.yaml` |
| `core/db.py` | Persistência SQLite/SQLAlchemy |
| `core/logging_utils.py` | Log em `logs/sisclima.log` |
| `ingestion/local_csv.py` | Leitura de CSVs em `data/input/` |
| `ingestion/openmeteo.py` | API Open-Meteo (previsão municipal) |
| `ingestion/inmet.py` | Alertas INMET |
| `ingestion/indicasus.py` | Leitos IndicaSUS (DW → CSV fallback) |
| `ingestion/dw_sources.py` | Queries SQL Server (SES/MT DW) |
| `ingestion/sqlserver.py` | Conexão ODBC/pyodbc |
| `ingestion/sivep_local.py` | Banco SQLite local SIVEP/SRAG |
| `ingestion/copernicus_air_quality.py` | CAMS Copernicus (qualidade do ar) |
| `ingestion/copernicus_cams_real.py` | CAMS alternativo (não ligado ao pipeline) |
| `ingestion/copernicus.py` | ERA5-Land (placeholder) |
| `ingestion/ibge_municipios.py` | Municípios MT via IBGE API/cache |
| `engines/biometeo.py` | Heat Index, UTCI, EHF, ondas de calor |
| `engines/air_quality.py` | Score qualidade do ar |
| `engines/epidemiology.py` | Pressão assistencial, SIVEP, LACEN, SINAN, SIM |
| `engines/hospital.py` | Capacidade e ocupação de leitos |
| `engines/operations.py` | Estoque, infraestrutura, busca ativa, comunicação |
| `engines/sentinel.py` | Score SENTINELA (rumores) |
| `engines/resilience.py` | Índice de resiliência e vulnerabilidade |
| `engines/stages.py` | Classificação de estágio (`StageResult`) |
| `engines/recommendations.py` | Recomendações por nível |
| `engines/geospatial.py` | Join espacial com shapefile |
| `alerts/change_detector.py` | Detecção de mudança de nível |
| `alerts/notifier.py` | E-mail, Telegram, webhook |
| `ai/report_generator.py` | Boletim diário (determinístico ou LLM) |
| `utils/dates.py` | Timestamps ISO |
| `utils/municipios.py` | Normalização `cod_ibge` / `municipio` |
| `utils/io.py` | Leitura multi-formato (CSV/XLSX/Parquet/DBF) |
| `validation/validate_sources.py` | Checklist pré-execução |

### 4.2 Fluxo do pipeline

```
run_pipeline()
  ├─ load_all_inputs() + municípios (CSV ou IBGE)
  ├─ Meteorologia: CSV + Open-Meteo → biometeo
  ├─ INMET: API ou CSV
  ├─ Qualidade do ar: CAMS Copernicus ou CSV
  ├─ Hospital: DW/CSV → capacidade + ocupação IndicaSUS
  ├─ Epidemiologia: SIVEP local, DW SINAN/SIM/GAL
  ├─ Operações: estoque, infra, busca ativa, comunicação
  ├─ Vulnerabilidade + resiliência
  ├─ _build_municipal_summary() → classify_stage()
  ├─ Resumo estadual (pior município)
  ├─ Auditoria + recomendações
  └─ Alertas (se mudança de nível)
```

### 4.3 Pontos de entrada

| Função | Onde | Uso |
|--------|------|-----|
| `run_pipeline(send_alerts=True)` | `pipeline.py` | Execução completa |
| `validate_sources()` | `validation/validate_sources.py` | Pré-voo |
| `generate_daily_report()` | `ai/report_generator.py` | Boletim pós-pipeline |
| `init_db()` | `core/db.py` | Cria tabelas de controle |

---

## 5. Dados

### 5.1 `data/public/` — Publicados no cloud (11 arquivos)

| Arquivo | Linhas | Descrição |
|---------|--------|-----------|
| `resumo_municipal_atual.csv` | 143 | **Obrigatório.** Resumo integrado por município (92 colunas) |
| `municipios_mt_2025_simplificado.geojson` | — | Geometria municipal para mapas |
| `predicao_calor_7d_municipal_v6.csv` | 143 | Predição de calor 7 dias |
| `alerta_inteligente_municipal_v6.csv` | 143 | Alertas inteligentes V6 |
| `v9_priorizacao_epidemiologica.csv` | 143 | Priorização epidemiológica V9 |
| `qualidade_ar_municipal.csv` | 143 | Qualidade do ar (PM2.5, O3, etc.) |
| `hospital_ocupacao_municipio.csv` | 40 | Ocupação de leitos por município |
| `ops_resumo_operacional_cnes.csv` | 143 | Resumo operacional CNES |
| `geocalor_status_modelagem_v11_12.csv` | 2 | Status modelagem GeoCalor |
| `geocalor_cardioresp_rr_municipal_v11_12.csv` | 4.545 | RR cardiorrespiratório municipal |
| `geocalor_cuiaba_cardioresp_v11_12.csv` | 33 | RR cardiorrespiratório Cuiabá |

**Estado atual dos níveis (resumo_municipal_atual):**

| Nível | Municípios |
|-------|------------|
| Verde | 92 |
| Amarela | 36 |
| Laranja | 11 |
| Vermelha | 3 |
| Roxa | 0 |

### 5.2 `data/public/` — Arquivos referenciados mas ausentes

| Arquivo | Referenciado em |
|---------|-----------------|
| `status_alertas_vigia.csv` | App validado (catálogo), `pages/12_*` |
| `alertas_estado_vigia.csv` | `pages/12_*` |
| `alertas_regionais_vigia.csv` | `pages/12_*` |
| `alerta_cuiaba_vigia.csv` | `pages/12_*` |

### 5.3 `data/output/sis_integrado.db` — Banco sanitizado

- **Tamanho:** ~13 MB
- **Tabelas:** 60 (ver `README_BANCO_SANITIZADO_V11_25.txt`)
- **Commitado no git** (único arquivo em `data/output/`)

**Tabelas com dados relevantes (amostra):**

| Tabela | Registros | Domínio |
|--------|-----------|---------|
| `resumo_municipal_atual` | 142 | Resumo integrado |
| `met_biometeo` | 994 | Biometeorologia |
| `epi_sinan_agravos` | 82.207 | SINAN |
| `epi_sim_obitos_calor` | 9.933 | SIM óbitos calor |
| `geocalor_cardioresp_rr_municipal_v11_12` | 4.544 | GeoCalor |
| `v9_painel_saude_municipal_mensal` | 29.269 | V9 temporal |
| `hospital_capacidade_unidade` | 1.240 | Capacidade leitos |
| `hospital_ocupacao_unidade` | 907 | Ocupação unidade |

**Tabelas vazias no banco sanitizado:**

`epi_sivep_srag`, `ops_busca_ativa`, `ops_comunicacao`, `ops_estoque_autonomia`, `ops_infraestrutura_resumo`, `ops_infraestrutura_unidade`, `gal_positividade_estado_serie_v7`, `gal_positividade_estado_serie_v7_3`, `sim_obitos_calor_estado_serie_v7`, `sim_obitos_calor_municipal_v7`, `v9_painel_clima_saude_mensal`

**Tabelas excluídas do banco sanitizado** (por segurança): `alertas_enviados`, `auditoria_indicadores`, `pipeline_runs`, `nivel_atual`, `recomendacoes_operacionais`, `inmet_alertas`, `sentinela_rumores_score`, etc.

### 5.4 `data/sample/` — Dados demo (15 CSVs)

Usados pelo pipeline local via `data/input/` (não versionados). Espelham os nomes em `config/settings.yaml` → `data_sources`.

### 5.5 `data/geo/` — Shapefile municipal

- `municipios_mt/MT_Municipios_2025.shp` (+ .cpg, .prj, .qmd)
- Usado por `app_v6`–`app_v9` e `sisclima/engines/geospatial.py`

---

## 6. Configuração

### 6.1 `config/settings.yaml`

| Seção | Conteúdo |
|-------|----------|
| `app` | Nome, município foco (Cuiabá), UF, coordenadas, meses críticos |
| `stages` | Mapeamento verde(0) → roxa(4) |
| `limiares_calor` | UTCI, Tmax fallback, EHF, risco cumulativo 3d |
| `limiares_assistenciais` | Pressão calor %, ocupação leitos %, z-score |
| `limiares_operacionais` | Autonomia insumos, falhas infra %, busca ativa, comunicação |
| `pesos_resiliencia` | Pesos do índice composto |
| `data_sources` | Caminhos e nomes de CSVs de entrada |
| `alertas` | Push em mudança de nível, cooldown 60 min |
| `qualidade_ar` | Limiares PM2.5, PM10, O3, NO2, CO |
| `tempo_real` | Intervalo 60 min, rodar ao iniciar |
| `municipalizacao` | Chave IBGE, shapefile MT |

### 6.2 `config/sources_real.yaml`

Documentação operacional das fontes reais (não importada diretamente pelo código):

- **DW SES/MT** (SQL Server, prefixo `DW_` no `.env`): IndicaSUS, CNES, SINAN, SIM, GAL/LACEN
- **SIVEP local**: SQLite em `data/local/sivep/`
- **Copernicus**: CAMS (ar) + ERA5-Land (meteorologia)
- **INMET**: API ou CSV
- **SENTINELA**: CSV ou API
- **Alertas**: e-mail, Telegram, webhook

### 6.3 Variáveis de ambiente (`.env` — não versionado)

Principais grupos (ver `docs/ENV_EXISTENTE_COMPATIBILIDADE.md`):

| Prefixo | Uso |
|---------|-----|
| `DW_*` | Conexão SQL Server (host, user, password, database) |
| `USE_SQLSERVER`, `USE_OPENMETEO`, `USE_COPERNICUS` | Flags de fontes |
| `COPERNICUS_KEY` / `~/.cdsapirc` | API Copernicus CDS/ADS |
| `INMET_ALERTS_URL` | Endpoint alertas INMET |
| `SMTP_*`, `TELEGRAM_*`, `WEBHOOK_URL` | Canais de alerta |
| `LLM_API_*` | Boletim com LLM (opcional) |
| `DATABASE_URL` | Override do SQLite padrão |

---

## 7. Queries SQL (`sql/`)

| Arquivo | Fonte DW | Domínio |
|---------|----------|---------|
| `dw_indicasus_leitos.sql` | DW SES/MT | Leitos IndicaSUS |
| `dw_cnes_estabelecimentos.sql` | DW SES/MT | Estabelecimentos CNES |
| `dw_cnes_leitos.sql` | DW SES/MT | Leitos CNES |
| `dw_sinan_agravos_calor.sql` | DW SES/MT | Agravos SINAN (calor) |
| `dw_sim_obitos_calor.sql` | DW SES/MT | Óbitos SIM (calor) |
| `dw_gal_lacen_resultados.sql` | DW SES/MT | Exames GAL/LACEN |
| `indicasus_leitos.sql` | Standalone | Query IndicaSUS |
| `lacen_gal_resultados.sql` | Standalone | Query LACEN |
| `sinan_agravos_calor.sql` | Standalone | Query SINAN |
| `sim_obitos_calor.sql` | Standalone | Query SIM |
| `sivep_srag_residencia.sql` | SIVEP | SRAG por residência |

---

## 8. Documentação existente (`docs/`)

| Documento | Conteúdo |
|-----------|----------|
| `ARQUITETURA.md` | Camadas Bronze/Silver/Gold, regra decisória |
| `DICIONARIO_DADOS.md` | Esquema dos CSVs de entrada |
| `OPERACAO.md` | Rotina diária (07h30–pós-evento) |
| `TEMPO_REAL.md` | Configuração tempo real |
| `MUNICIPALIZACAO_DADOS.md` | Chaves municipais e shapefile |
| `IMPLEMENTACAO_REAL_MT.md` | Implementação com fontes reais |
| `FONTES_REAIS_DW_SIVEP_LOCAL.md` | DW + SIVEP local |
| `COPERNICUS_CAMS_QUALIDADE_AR.md` | Integração CAMS |
| `ENV_EXISTENTE_COMPATIBILIDADE.md` | Compatibilidade de variáveis .env |
| `INVENTARIO_SISTEMA.md` | Este documento |

---

## 9. Dependências externas

### APIs

| Serviço | Módulo | Ativação |
|---------|--------|----------|
| Open-Meteo | `ingestion/openmeteo.py` | `USE_OPENMETEO=true` |
| INMET alertas | `ingestion/inmet.py` | `INMET_ALERTS_URL` |
| IBGE (municípios) | `ingestion/ibge_municipios.py` | `REFRESH_IBGE_MUNICIPIOS` |
| Copernicus CAMS | `ingestion/copernicus_air_quality.py` | `USE_COPERNICUS=true` |
| Telegram | `alerts/notifier.py` | `TELEGRAM_BOT_TOKEN` |
| LLM (boletim) | `ai/report_generator.py` | `USE_LLM_REPORT=true` |

### Bancos de dados

| Store | Caminho | Uso |
|-------|---------|-----|
| SQLite integrado | `data/output/sis_integrado.db` | Saída principal do pipeline |
| SQLite SIVEP | `data/local/sivep/sivep_srag_local.db` | Espelho local SIVEP |
| SQL Server DW | Via ODBC | Fontes institucionais SES/MT |

### Stack Python principal

`streamlit 1.57`, `pandas 3.0`, `plotly 6.7`, `geopandas 0.14`, `pyodbc 5.3`, `cdsapi 0.7`, `xarray 2026`, `statsmodels 0.14`, `google-generativeai 0.8`

---

## 10. Deploy e operação

### Streamlit Cloud

- **Main file:** `streamlit_app.py`
- **Branch:** `main`
- **Dados:** `data/public/` (CSVs) — sem `.env` nem credenciais
- **Tema:** `primaryColor='#D83232'` (`.streamlit/config.toml`)

### Ambiente local completo

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Configurar .env (DW, Copernicus, alertas)
cp .env.example .env   # se existir; senão criar manualmente

# 3. Popular data/input/ (ou usar data/sample/)
cp data/sample/*.csv data/input/

# 4. Rodar pipeline
python -c "from sisclima.pipeline import run_pipeline; run_pipeline()"

# 5. Abrir painel
streamlit run app_v9.py          # SQLite completo
streamlit run streamlit_app.py   # Cloud (CSV)
```

### Rotina operacional diária

Ver `docs/OPERACAO.md`:

| Horário | Ação |
|---------|------|
| 07h30 | Ingestão meteorologia, INMET, Copernicus, dados assistenciais |
| 08h00 | Pipeline → indicadores e classificação |
| 08h15 | Validação boletim na sala de situação |
| ≤2h após alerta INMET | Comunicação municipal |
| 12h e 17h | Reprocessamento (níveis Laranja+) |
| Pós-evento | Auditoria, morbimortalidade, lições aprendidas |

### Scripts Windows (não versionados — `.gitignore`)

Referenciados no `README.md` para sincronização local ↔ cloud:

- `RESTAURAR_PAINEL_ORIGINAL_STREAMLIT_CLOUD_V11_25.cmd`
- `SUBIR_STREAMLIT_CLOUD_ORIGINAL_GITHUB_V11_25.cmd`
- `FORCE_PUSH_STREAMLIT_CLOUD_ORIGINAL_V11_25.cmd`

---

## 11. Histórico Git (commits recentes)

| Commit | Descrição |
|--------|-----------|
| `2486084` | Adiciona página de alertas agendados do VIGIA |
| `79fd42d` | Prioriza app VIGIA completo validado no Streamlit Cloud |
| `46147fd` | Painel VIGIA completo com correção GeoCalor Cuiabá |
| `44d5e3f` | SIS Clima-Saúde MT — painel original no Streamlit Cloud |

---

## 12. Lacunas e pendências conhecidas

### Dados

- [ ] Publicar CSVs de alertas VIGIA em `data/public/` (4 arquivos)
- [ ] Tabelas vazias no banco sanitizado (SIVEP, ops_*, algumas séries V7)
- [ ] `data/input/` e `data/local/` não versionados — necessários para pipeline local

### Código

- [ ] `copernicus_cams_real.py` não está ligado ao `pipeline.py` (existe alternativa)
- [ ] `config/sources_real.yaml` é documentação — não é lido pelo código
- [ ] Páginas `pages/10_*` e `pages/12_*` não integradas ao roteador `streamlit_app.py`
- [ ] `app.py` é a única versão com botão "Rodar pipeline agora"

### Infraestrutura

- [ ] Sem CI/CD configurado
- [ ] Sem testes automatizados
- [ ] Sem issues abertas no GitHub
- [ ] Scripts `.cmd`/`.bat` de deploy existem apenas no ambiente local Windows

---

## 13. Mapa de decisão — qual componente usar?

```
Preciso de...                          → Usar
─────────────────────────────────────────────────────────
Painel no Streamlit Cloud              → streamlit_app.py
Painel local com todos os indicadores  → app_v9.py + sis_integrado.db
Rodar pipeline com dados reais         → sisclima/pipeline.py + .env
Validar fontes antes de rodar          → validate_sources()
Atualizar dados do cloud               → Exportar CSVs → data/public/
GeoCalor detalhado                     → pages/10_* ou aba 9 do VIGIA
Alertas agendados                      → pages/12_* (após publicar CSVs)
Entender limiares de risco             → config/settings.yaml
Entender fontes de dados               → config/sources_real.yaml + docs/
```

---

## 14. Próximos passos sugeridos

1. **Publicar CSVs de alertas** — completar `data/public/` para a página 12
2. **Integrar multipage** — converter roteador para suportar `pages/` nativamente
3. **Automatizar exportação** — script que gera `data/public/` a partir do pipeline/SQLite
4. **Testes** — validação de `validate_sources()` e smoke test do pipeline com `data/sample/`
5. **CI** — lint + teste de sintaxe dos apps Streamlit
6. **Documentar .env** — criar `.env.example` versionado com chaves sem valores

---

*Este inventário deve ser atualizado sempre que houver mudança estrutural no projeto (novos apps, tabelas, fontes ou deploy).*
