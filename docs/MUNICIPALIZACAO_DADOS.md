# Municipalização dos dados

A versão V2 gera e armazena os principais indicadores por município, usando as chaves:

- `cod_ibge`
- `municipio`

Tabelas municipalizadas principais:

- `resumo_municipal_atual`
- `met_biometeo`
- `qualidade_ar_municipal`
- `epi_pressao_assistencial`
- `hospital_capacidade_agregada`
- `ops_estoque_autonomia`
- `ops_infraestrutura_resumo`
- `ops_busca_ativa`
- `epi_sivep_srag`
- `lab_lacen_gal`
- `epi_sinan_agravos`
- `epi_sim_obitos_calor`
- `sentinela_rumores_score`
- `geo_vulnerabilidade_municipal`

Para operar nos 141 municípios de Mato Grosso, substituir `data/input/municipios_metadata.csv` por uma base completa contendo ao menos:

```csv
cod_ibge,municipio,lat,lon,idosos_pct,pobreza_pct,sem_ar_condicionado_pct,rural_pct,pop_rua,densidade
```

Quando as bases reais vierem do SQL Server, manter `cod_ibge` no SELECT do IndicaSUS, CNES, SIVEP, SINAN, SIM e LACEN sempre que possível.
