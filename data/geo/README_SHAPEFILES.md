Coloque aqui os shapefiles oficiais de municípios de Mato Grosso, por exemplo:

- MT_Municipios_2024.shp
- MT_Municipios_2024.dbf
- MT_Municipios_2024.shx
- MT_Municipios_2024.prj

Depois ajuste no `.env`:

```env
SHAPEFILE_MT=data/geo/MT_Municipios_2024.shp
MUNICIPIO_KEY=cod_ibge
```

O painel funciona sem shapefile usando a base tabular `municipios_metadata.csv`; com shapefile, o motor geográfico pode gerar mapas municipais completos.
