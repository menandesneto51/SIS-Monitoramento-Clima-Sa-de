# SIS-MT Clima-Saúde V4 — regra de fontes reais

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

Configure no `.env`:

```env
USE_SQLSERVER=true
DW_SERVER=SERVIDOR
DW_DATABASE=NOME_DO_DW
DW_USER=SEU_LOGIN
DW_PASSWORD=SUA_SENHA
DW_DRIVER=ODBC Driver 17 for SQL Server
```

As consultas ficam na pasta `sql/` e devem ser ajustadas aos nomes reais das views/tabelas do DW.

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
