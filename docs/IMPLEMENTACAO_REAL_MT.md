# SIS-MT Clima-Saúde — Implementação real para Mato Grosso

Esta versão foi reorganizada para produção real. O ciclo principal não depende de dados simulados. Os dados de exemplo ficam restritos ao script `criar_dados_exemplo.py` e servem apenas para validação local.

## Fontes reais previstas

1. **Municípios e geografia**
   - Fonte primária: IBGE Localidades e Malhas para UF 51.
   - Saída: `data/input/municipios_metadata.csv` com `cod_ibge`, `municipio`, `lat`, `lon`.
   - Comando: `preparar_municipios_ibge.bat` ou `python main_real.py municipios --force`.

2. **Copernicus/CAMS — qualidade do ar**
   - Dataset: `cams-global-atmospheric-composition-forecasts`.
   - Poluentes operacionais: PM2.5, PM10, O3, NO2, CO e SO2.
   - Configure `.cdsapirc` ou `COPERNICUS_URL`/`COPERNICUS_KEY` no `.env`.
   - Para arquivo já baixado pelo TITAN, use `COPERNICUS_CAMS_LOCAL_FILE=C:\caminho\arquivo.nc`.

3. **Copernicus/ERA5-Land e meteorologia operacional**
   - A versão mantém Open-Meteo como fallback municipal em tempo real.
   - ERA5-Land fica parametrizado para acoplamento histórico e baseline climático.

4. **IndicaSUS, CNES e monitoramento hospitalar**
   - Configure `USE_SQLSERVER=true` e os prefixos `INDICASUS_*` e `DW_*`.
   - Ajuste `sql/indicasus_leitos.sql` conforme views reais do ambiente SES/MT.

5. **SIVEP/SRAG, SINAN, SIM e LACEN/GAL**
   - Podem entrar por CSV real em `data/input/` ou por SQL Server.
   - Há SQLs-modelo em `sql/` para padronização por município de residência e data correta.
   - SIVEP deve ser analisado por `data_sintomas` e município de residência.

6. **SENTINELA/TITAN/AESOP**
   - Rumores, sinais e eventos críticos entram por `sentinela_rumores.csv` ou API futura.
   - O motor de risco integrado combina clima, qualidade do ar, assistência, leitos, infraestrutura, estoques, busca ativa e sinais precoces.

7. **Relatórios e alertas**
   - Mudança de nível aciona e-mail, Telegram e webhook quando configurados.
   - `gerar_relatorio_diario.bat` gera boletim operacional auditável; opcionalmente usa IA institucional via endpoint configurável.

## Sequência de produção

```bat
copy .env.producao.example .env
instalar.bat
preparar_municipios_ibge.bat
validar_fontes_reais.bat
rodar_ciclo_real.bat
abrir_painel.bat
```

Operação contínua:

```bat
rodar_producao_tempo_real.bat
```

## Critério de prontidão

O sistema é considerado pronto para uso operacional quando `validar_fontes_reais.bat` não indicar pendência obrigatória e quando o painel exibir os 141 municípios com `cod_ibge`, `municipio`, `lat` e `lon`.
