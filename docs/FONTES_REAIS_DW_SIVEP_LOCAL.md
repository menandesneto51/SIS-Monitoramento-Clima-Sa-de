# ARARAS MT V4 — regra de fontes reais

Esta versão incorpora a regra operacional definida pela SES/MT:

1. **IndicaSUS, CNES, SINAN, SIM e GAL/LACEN** serão acessados pelo **Data Warehouse** com o login e senha configurados no `.env` pelo prefixo `DW_`.
2. **SIVEP/SRAG** será mantido em **banco local atualizado** dentro da pasta do sistema, junto da base territorial e dos shapefiles.
3. O cruzamento territorial usa `cod_ibge` como chave única municipal.
4. Os shapefiles municipais 2025 e a população 2020–2025 já estão incorporados ao pacote.

## Arquivos sensíveis

Não coloque senha dentro de código Python nem em SQL. Configure somente no `.env`, que não deve ser enviado por e-mail ou versionado em repositório público.

## Pastas principais

```text
data/geo/municipios_mt/MT_Municipios_2025.shp
data/input/municipios_mt.csv
data/input/populacao_municipal_mt_2020_2025.csv
data/input/sivep_atualizacao/
data/local/sivep/sivep_srag_local.db
sql/dw_indicasus_leitos.sql
sql/dw_sinan_agravos_calor.sql
sql/dw_sim_obitos_calor.sql
sql/dw_gal_lacen_resultados.sql
```

## Fluxo recomendado

```bat
copy .env.producao.example .env
instalar.bat
atualizar_sivep_local.bat
validar_dw_sivep.bat
rodar_ciclo_real.bat
abrir_painel.bat
```

## DW

Configure no `.env` (mesmo contrato dos projetos **Meningites** e **Ondas de calor**):

```env
USE_SQLSERVER=true
DW_SERVER=10.15.1.50
DW_HOST=10.15.1.50
DW_DATABASE=Datawarehouse
DW_USER=menandes_cievs
DW_PASSWORD=  # senha real — não versionar
DW_DRIVER=ODBC Driver 18 for SQL Server
DW_ENCRYPT=no
DW_TRUST_SERVER_CERTIFICATE=yes
# Opcional: reutilizar .env de outro projeto CIEVS
# DW_ENV_FILE=C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor\.env
```

Validar:

```bash
python validar_dw_conexao.py
```

Inventário completo (somente leitura, VPN SES):

```bash
python scripts/inventario_dw_completo.py
```

Artefatos (metadados, sem PII/credenciais):

- [`docs/dw/inventario_dw_latest.md`](dw/inventario_dw_latest.md) — ranking + classes
- [`docs/dw/inventario_dw_latest.json`](dw/inventario_dw_latest.json) — máquina
- [`docs/dw/sql_adapters_candidatos.md`](dw/sql_adapters_candidatos.md) — SQL/loaders candidatos (**não** ligados em produção)

Snapshot 2026-09-12: conta `menandes_cievs` acessa **1** banco (`Datawarehouse`), **83** objetos `dbo` (26 views / 57 tables). Núcleo ARARAS já linkado: SINAN (calor + extras), GAL, SIM, CNES, `VW_INTERNACAO`. Novos candidatos altos: CNES profissionais/equipamentos/eAB, `SIVEP_MALARIA`, leish tegumentar — stubs só após CIEVS. Sem views `SISREG`/`AIH`/`DDA`/`NEBUL` no `dbo` visível nesta conta.

### Onda 1 (implementada) — ampliar consumo já linkado

- Pipeline persiste `epi_sinan_intoxicacao_detalhe` e `epi_sinan_agravos_extras_clima`.
- Enrich (`dw_sinais_municipais`) agrega por município: fumaça 7d, extras clima, internações CID; marca `fonte_srag` (SIVEP local preferencial; SINAN DW se lacuna).
- Visão: cards compostos + extras/SRAG/internação; `sinal_fumaca_sem_pm` também liga com intox DW.
- Boletim técnico/executivo: bloco extras clima + nota de fonte SRAG.

### Onda 2 (implementada) — novos loaders

- Leish tegumentar no extras SINAN; malária (`dw_sivep_malaria_municipal.sql`); CNES equipamentos/nebulização (`dw_cnes_equipamentos_municipal.sql`).
- Flags existentes: `USE_DW_SINAN` / `USE_DW_SIVEP` / `USE_DW_CNES` (sem flags novas).
- Tabelas: `epi_sivep_malaria`, `epi_cnes_equipamentos_municipal`.

### Onda 3 (implementada) — rede CNES APS

- Profissionais, equipes eAB e serviços/classificação — só contagens municipais (`USE_DW_CNES`).
- Tabelas: `epi_cnes_profissionais_municipal`, `epi_cnes_equipes_ab_municipal`, `epi_cnes_servico_classificacao_municipal`.
- Sem PII; não altera `nivel`/pred 7d.

### IRM + domínio RIT `rede` (implementado)

- Motor: `sisclima/engines/indice_resiliencia_municipal.py` → `indice_resiliencia_municipal_0_100` (capacidade).
- RIT: `rit_score_rede = 100 − IRM` (fragilidade); IRM alto **não** eleva RIT. Ver `docs/adr/ADR-RIT-multirisco.md`.
- Compostos: `gap_fumaca_nebulizacao`, `pressao_x_resiliencia`.
- Flag: `USE_DW_CNES` (sem flag nova). Ordem enrich: sinais DW → IRM → RIT → compostos.
- Frescor: `sisclima/engines/resumo_frescor.py` reaplicado antes de alertas, boletim e painel.

As consultas ficam na pasta `sql/` e devem ser ajustadas aos nomes reais das views/tabelas do DW.
Views já usadas pelos projetos irmãos: `VW_SINAN_*`, `VW_GAL`, `CNES_ESTABELECIMENTOS`, `SIM`.

## e-SUS APS (Centralizador Postgres)

Não passa pelo DW. Configure `ESUS_APS_*` no `.env` e, com VPN SES:

```powershell
.\.venv\Scripts\python.exe scripts\explorar_esus_aps.py
```

Detalhes: `docs/ESUS_APS.md`.

## SIVEP local

Coloque arquivos exportados do SIVEP em:

```text
data/input/sivep_atualizacao/
```

Depois rode:

```bat
atualizar_sivep_local.bat
```

O sistema criará:

```text
data/local/sivep/sivep_srag_local.db
```

Durante o pipeline, esse banco é lido automaticamente e resumido por município de residência e data de início dos sintomas.
