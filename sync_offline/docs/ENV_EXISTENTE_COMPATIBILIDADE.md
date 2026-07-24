# Uso do `.env` existente

Esta versão não exige recriar o `.env`. O carregador de configuração reconhece os nomes de variáveis usados nos projetos anteriores do TITAN, AESOP, LACEN, Monitora Hospitalar, SIVEP e na V4 do SIS-MT.

## Regra operacional

- Não copie `.env.example` por cima do `.env` já configurado.
- Rode primeiro `validar_env_existente.bat`.
- O sistema aceita arquivos territoriais organizados em `data/geo/municipios_mt/` ou soltos na raiz da pasta do projeto.
- O DW é a fonte institucional para IndicaSUS, CNES, SINAN, SIM e GAL/LACEN.
- O SIVEP/SRAG fica em banco local atualizado na pasta do projeto.

## Fontes obrigatórias

- `.env` existente.
- Shapefile municipal de MT 2025.
- `municipios_mt.csv` ou planilha equivalente.
- População municipal 2020-2025.
- Credenciais DW, se `USE_SQLSERVER=true` ou equivalente.
- Credenciais Copernicus ou `.cdsapirc`, se `USE_COPERNICUS=true` ou equivalente.

## Comandos recomendados

```bat
instalar.bat
validar_env_existente.bat
atualizar_sivep_local.bat
rodar_ciclo_real.bat
abrir_painel.bat
```
