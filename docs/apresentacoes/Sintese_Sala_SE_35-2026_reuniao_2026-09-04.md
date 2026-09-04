# Síntese para a Sala — SE 35/2026 (reunião 04/09/2026)

**Atualizado:** 03/09/2026 17h54 · boletim + PPTX com e-SUS×clima (Spearman) e STAR/EHF (**1.386** eventos · janela 2021-07 a 2026-09)  
**Semana:** SE 35/2026 (30/08 a 05/09/2026)  
**QA:** APROVADA (Issues: 0)  
**ETL:** e-SUS + STAR integrados ao `pipeline.py`; ETL completa em curso (`--force`) · CDS 2020 ainda na fila (job tmin 2020)  
**PPTX:** `docs/apresentacoes/Sala_Situacao_SE35_2026_ARARAS.pptx`

## Cartões executivos (rodada 16h59)

| Indicador | Valor |
|-----------|-------|
| Vermelho/roxo (atual) | **94/142** (66,2%) |
| Vermelho/roxo (proj. ~7d) | **115/142** (81,0%) |
| Tmáx máxima | ver boletim / top STAR (até **39,3 °C**) |
| PM2,5 ≥ 25 µg/m³ | **18/142** |
| Ocupação IndicaSUS | **~57%** (3346/5872 leitos · 85 mun.) |

**Leitura:** alívio térmico após a chuva de segunda (01/09), mas a projeção ~7d sobe de novo para ~81% vermelho/roxo.

## Novidades desta versão (para amanhã)

### 1) Atenção primária — PEC/eSUS
- Cadastro estadual: **5.402.079** · asma **26.847** · DPOC **7.375** · idosos 60+ **727.991** · gestantes **192.553** · acamados **17.616**
- Atendimentos 28d: **14.636** (66 municípios com registro) · CID respiratório 28d **116**
- Tabelas 5–6 no boletim: PEC/eSUS por classe ARARAS e ranking municipal
- **94** municípios vermelho/roxo com cadastro APS cruzado (prioridade)
- Observação: VPN/Centralizador não respondeu na tarde; números de cadastro/atendimento são da carga já gravada + recruze com a classe atual

### 2) Ondas de calor — STAR + GeoCalor
- Nova seção no boletim: **“Ondas de calor — levantamento STAR (Anexo 1) e método GeoCalor”**
- Flag operacional de onda (P95≥2d): **2/142**
- Top Tmáx e prioridade STAR (Tabelas 7–8)
- Catálogo científico EHF (CDS ERA5-Land): smoke jan/2024 OK · **1 evento / 3 dias** (série ≥5 anos ainda em carga)
- GeoCalor Fiocruz **não** publica Cuiabá/MT; ARARAS aplica EHF aos 142 municípios

## Arquivos para a reunião

| Produto | Caminho |
|---------|---------|
| Boletim MD | `docs/apresentacoes/Boletim_ElNino_SE_35-2026.md` |
| PDF apresentável | `docs/apresentacoes/Boletim_ElNino_SE_35-2026_apresentavel.pdf` |
| PDF Sala (nome oficial) | `docs/apresentacoes/Boletim Informativo Sala de Situação MT El Niño SE 35-2026.pdf` |
| Cópias | `exports/relatorios/` |
| Anexo STAR XLSX | `data/output/star/STAR_Anexo1_Ondas_de_Calor_Materiais.xlsx` |
| Esta síntese | `docs/apresentacoes/Sintese_Sala_SE_35-2026_reuniao_2026-09-04.md` |

## Fala sugerida (2 min)

1. Cenário atual **66%** vermelho/roxo (94/142), com chuva de segunda aliviando o pico da semana anterior.  
2. Projeção ~7d: **81%** (115/142) — manter atenção.  
3. APS: mais de **5,4 milhões** de cadastros; vulneráveis (asma, idosos, gestantes, acamados) já cruzados com a classe ARARAS.  
4. STAR/ondas: método GeoCalor/EHF embutido no boletim; alerta diário continua P95≥2d; catálogo científico de 5 anos em andamento via Copernicus CDS.
