# Extração em tempo real

A versão V2 inclui o script `main_tempo_real.py`.

## Executar continuamente

```bat
rodar_tempo_real.bat
```

## Executar um único ciclo

```bat
rodar_tempo_real_uma_vez.bat
```

## Intervalo

Configurar no `.env`:

```env
RUN_REALTIME_INTERVAL_MINUTES=60
```

## Fontes online

- Open-Meteo municipal: ativar com `REFRESH_OPENMETEO=true`.
- Copernicus/CAMS: ativar com `USE_COPERNICUS=true`.
- INMET: configurar endpoint ou CSV conforme `sisclima/ingestion/inmet.py`.

Se uma API falhar, o pipeline mantém fallback CSV/local para evitar interrupção operacional do painel.
