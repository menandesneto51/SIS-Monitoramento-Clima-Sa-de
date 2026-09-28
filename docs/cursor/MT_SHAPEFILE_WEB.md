# Cursor — Malha Municipal MT 2025 via Shapefile

## Fonte primária

Conjunto IBGE Malha Municipal Digital 2025:

- `data/geo/municipios_mt/MT_Municipios_2025.shp`
- `data/geo/municipios_mt/MT_Municipios_2025.shx`
- `data/geo/municipios_mt/MT_Municipios_2025.dbf`
- `data/geo/municipios_mt/MT_Municipios_2025.prj`
- `data/geo/municipios_mt/MT_Municipios_2025.cpg`

CRS confirmado:
`EPSG:4674 / SIRGAS 2000`

## Regra

O shapefile é a fonte cartográfica primária.

GeoJSON, TopoJSON ou qualquer outro formato usado na web é **derivado**, nunca fonte independente.

## Fluxo

### 1. Descobrir schema real

```powershell
python scripts/build_mt_shapefile_web.py
```

Na primeira execução, com mapping pendente, o script deve listar:
- feature_count;
- CRS;
- columns;
- geometry types;

e interromper com:

`SHAPEFILE_MAPPING_PENDING`

### 2. Mapear explicitamente os campos da DBF

Editar:

`config/mt_shapefile_web.json`

Preencher:

```json
"fields": {
  "cod_ibge": "<CAMPO_REAL>",
  "municipio": "<CAMPO_REAL>"
}
```

Não presumir nomes como CD_MUN/NM_MUN sem confirmar no schema real.

### 3. Gerar derivado web

Executar novamente:

```powershell
python scripts/build_mt_shapefile_web.py
pytest tests/test_mt_shapefile_web.py -q
```

Saída esperada:

`data/public/municipios_mt_2025_shapefile_web.geojson`

Manifest:

`data/public/municipios_mt_2025_shapefile_web.manifest.json`

## Validações obrigatórias

- 142 feições;
- CRS EPSG:4674;
- código IBGE único;
- nenhuma geometria vazia;
- reparo de geometria inválida quando possível;
- simplificação com preservação de topologia;
- hashes SHA-256 de cada componente do shapefile;
- hash SHA-256 do artefato web.

## Integração com simulador CIEVS

O repositório `aprendendo-sobre-o-sarampo` deve consumir somente o artefato gerado por este pipeline.

Nunca usar o GeoJSON web como fonte autoritativa para:
- composição municipal;
- código IBGE;
- limites;
- CRS.

## Agentes

Revisão obrigatória:
- Data Architect;
- Data Governance;
- GIS/Geoprocessamento;
- QA;
- Chief Architect.

## DoD

- mapping real confirmado;
- pipeline executado;
- manifest gerado;
- 142 municípios;
- testes verdes;
- artefato web atualizado no simulador;
- documentação de proveniência sincronizada.
