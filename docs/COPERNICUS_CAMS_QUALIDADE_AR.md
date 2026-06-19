# Copernicus/CAMS - Qualidade do ar municipal

O módulo `sisclima.ingestion.copernicus_air_quality` foi preparado para baixar previsões de composição atmosférica pelo Copernicus Atmosphere Data Store/CAMS e transformar os dados para uma tabela municipal.

## Variáveis usadas

- PM2.5
- PM10
- Ozônio/O3
- Dióxido de nitrogênio/NO2
- Monóxido de carbono/CO
- Dióxido de enxofre/SO2

A saída operacional é a tabela `qualidade_ar_municipal`, com nível por município e poluente dominante.

## Como ativar

1. Criar conta no Copernicus Atmosphere Data Store.
2. Aceitar os termos de uso do dataset `cams-global-atmospheric-composition-forecasts`.
3. Criar o arquivo `%USERPROFILE%\.cdsapirc` no Windows ou preencher `COPERNICUS_KEY` no `.env`.
4. No `.env`, usar:

```env
USE_COPERNICUS=true
COPERNICUS_URL=https://ads.atmosphere.copernicus.eu/api
COPERNICUS_CAMS_DATASET=cams-global-atmospheric-composition-forecasts
COPERNICUS_AREA_NORTH=-7.0
COPERNICUS_AREA_WEST=-62.0
COPERNICUS_AREA_SOUTH=-18.5
COPERNICUS_AREA_EAST=-50.0
```

## Saída municipal

A rotina usa `municipios_metadata.csv`, com `cod_ibge`, `municipio`, `lat` e `lon`, para extrair o ponto mais próximo de cada município. Quando o shapefile municipal estiver configurado, a etapa poderá ser substituída por média zonal.

## Observação operacional

A qualidade do ar entra no estágio operacional quando `qualidade_ar.peso_no_estagio=true` no `config/settings.yaml`. O plano também agrava o risco quando há combinação de calor elevado e qualidade do ar ruim.
