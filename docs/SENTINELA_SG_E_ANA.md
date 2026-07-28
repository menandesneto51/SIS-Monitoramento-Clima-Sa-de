# Sentinela SG + ANA — uso operacional

## 1) Vigilância Sentinela de SG (MS)

### Entradas
Coloque em `data/input/`:

- `sentinela_sg_agregado_semanal.csv` — por US/SE: `atendimentos_sg`, `atendimentos_total`, `amostras_coletadas`
- `sentinela_sg_amostras.csv` — amostras individuais (definição de caso, preenchimento, RT-PCR, vírus, idade)

Modelos de exemplo: `data/sample/sentinela_sg_*.csv`.

### Saídas
- `epi_sentinela_sg_indicadores` (SG-01 … SG-13)
- `epi_sentinela_sg_semanal`
- `epi_sentinela_sg_virus_se`
- `epi_sentinela_sg_faixa_etaria`

UI: `pages/14_Sentinela_SG_MS.py`  
Catálogo: `config/indicadores_ms_sentinela_sg.yaml`

## 2) ANA (hidrologia / telemetria)

### Configuração (`.env`)
```env
USE_ANA=true
ANA_UF=MT
ANA_FETCH_SERIES=false   # true consulta SOAP (lento); false usa CSV
ANA_MAX_ESTACOES=10
ANA_SSL_VERIFY=false     # se proxy corporativo
```

### Entradas
- API SOAP pública ANA (`ListaEstacoesTelemetricas` / `DadosHidrometeorologicos`)
- Fallback: `data/input/ana_estacoes_mt.csv`, `data/input/ana_telemetria.csv`

### Saídas
- `ana_estacoes`
- `ana_telemetria`
- `ana_risco_municipal` (chuva/cota/nível → alimenta resumo municipal e estágio)

UI: seção ANA em `pages/12_Riscos_Hidrologicos_Cemaden.py`

### Validação
```bash
python validar_sentinela_ana.py
```
