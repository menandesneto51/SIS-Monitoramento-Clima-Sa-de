Coloque aqui os shapefiles oficiais de municípios de Mato Grosso:

- `MT_Municipios_2025.shp`
- `MT_Municipios_2025.dbf`
- `MT_Municipios_2025.shx`
- `MT_Municipios_2025.prj`
- `MT_Municipios_2025.cpg` (opcional)

Caminho padrão:

```text
data/geo/municipios_mt/MT_Municipios_2025.shp
```

No `.env`:

```env
SHAPEFILE_MT=data/geo/municipios_mt/MT_Municipios_2025.shp
MUNICIPIO_KEY=cod_ibge
```

Todos os mapas do painel (`app_v9`/`v8`/`v6`, `app.py` e páginas) usam `sisclima.engines.geospatial`:
1. shapefile municipal (prioridade);
2. GeoJSON processado em `data/processed/` (fallback);
3. pontos lat/lon (último recurso).
