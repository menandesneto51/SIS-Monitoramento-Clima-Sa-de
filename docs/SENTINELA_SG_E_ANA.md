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
ANA_FETCH_SERIES=true    # live (REST se ativo, senão SOAP)
ANA_MAX_ESTACOES=35      # prioriza estações fluviométricas / com régua
ANA_SERIES_DAYS=21       # janela → enum DIAS_21 no REST
ANA_SSL_VERIFY=true      # false só se proxy corporativo exigir
# REST HidroWebService (credenciais só no .env local)
ANA_USE_HIDROWEB_REST=true
# ANA_HIDROWEB_IDENTIFICADOR=
# ANA_HIDROWEB_SENHA=
# Opcional: cotas absolutas por estação
# ANA_COTAS_REFERENCIA_CSV=config/ana_cotas_referencia_mt.csv
```

### Entradas
- Preferencial: API REST HidroWeb (`OAUth` + inventário + série adotada) com parâmetros oficiais em português
- Fallback SOAP público (`ListaEstacoesTelemetricas` / `DadosHidrometeorologicos`) via `sisclima.core.http_client`
- Fallback CSV: `data/input/ana_estacoes_mt.csv`, `data/input/ana_telemetria.csv`
- Opcional: `config/ana_cotas_referencia_mt.csv` (cota_seca_cm / cota_alerta_cm / cota_emergencia_cm)

### Saídas
- `ana_estacoes`
- `ana_telemetria`
- `ana_risco_municipal` (chuva/cota/nível → alimenta resumo municipal e estágio)
- `hidro_risco_municipal` (`situacao_hidro` ∈ seca_baixa / normal / inundacao_alta; `risco_predominante` estiagem/cheia)

UI: aba **Cemaden / ANA** e **Clima / TITAN → Hidro risco**.

### Validação
```bash
# Live (respeita env já exportado; .env não sobrescreve):
set ANA_FETCH_SERIES=true
python validar_sentinela_ana.py
```
