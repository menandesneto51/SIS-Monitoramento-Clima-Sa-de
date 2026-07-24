# FONTES_REAIS_DW_SIVEP_LOCAL.md — mapa de senhas e papéis

Esta versão incorpora a regra operacional SES/MT:

| Fonte | Servidor / objeto | Senha | Uso no SIS |
|-------|-------------------|-------|------------|
| SIM, SINAN, GAL, CNES_*, VW_INTERNACAO | DW `10.15.1.50` / `Datawarehouse` | **sua** (`DW_PASSWORD`) | óbitos, agravos, lab, resiliência CNES, pressão fallback |
| SISREG | `10.15.1.71` / `SES` | `SISREG_PASSWORD` | **pressão** assistencial (preferencial) |
| IndicaSUS | `10.15.0.222` / `BdSES` | **Roney** (`INDICASUS_PASSWORD`) | **ocupação** de leitos tempo real |
| SIVEP/SRAG | banco local | — | SRAG (não usa DW neste fluxo) |

1. **CNES** (`CNES_ESTABELECIMENTOS`, `CNES_LEITOS`, `CNES_EQUIPAMENTOS`, equipes) → `ops_cnes_municipio` + `indice_capacidade_cnes` na resiliência.
2. **SISREG** (ou `VW_INTERNACAO` no DW) → `epi_pressao_assistencial`.
3. **IndicaSUS/BdSES (Roney)** → `hospital_ocupacao_municipio`.
4. O cruzamento territorial usa `cod_ibge` como chave única municipal.

## Arquivos sensíveis

Não coloque senha dentro de código Python nem em SQL. Configure somente no `.env`.

## SQL principal

```text
sql/dw_cnes_estabelecimentos.sql
sql/dw_cnes_leitos.sql
sql/dw_cnes_equipamentos.sql
sql/dw_cnes_equipes.sql
sql/dw_cnes_profissionais.sql
sql/dw_sih_internacoes_calor.sql
sql/dw_sinan_agravos_calor.sql
sql/dw_sim_obitos_calor.sql
sql/dw_gal_lacen_resultados.sql
sql/indicasus_ocupacao_municipio.sql
```

## Validação

```powershell
.\.venv\Scripts\python.exe validar_fontes_dw.py
.\.venv\Scripts\python.exe atualizar_ocupacao_indicasus.py --descobrir
.\.venv\Scripts\python.exe atualizar_ocupacao_indicasus.py
.\.venv\Scripts\python.exe run_ciclo_completo.py --force-alert
```
