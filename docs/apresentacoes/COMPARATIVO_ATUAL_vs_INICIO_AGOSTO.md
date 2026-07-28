# Comparativo real — cenário atual × início de agosto/2026

**Extração:** 27 jul. 2026  
**Backend SIS:** PostgreSQL  
**Fonte meteorológica de curto prazo:** Open-Meteo via tabela `met_biometeo` (CIEVS-MT, 2026; OPEN-METEO, 2026)  
**Último pipeline:** 27 jul. 2026, 08:41:22 — status `success` — mensagem “Nível roxa”

---

## 1. Comparativo climático estadual (142 municípios)

| Indicador (média estadual) | Atual 27/07/2026 | Projeção 01/08/2026 | Δ (01/08 − 27/07) | Projeção 02/08/2026 |
|---|---:|---:|---:|---:|
| Tmax (°C) | 33,61 | 34,34 | **+0,73** | 32,35 |
| Tmin (°C) | 20,63 | 21,53 | +0,90 | 22,22 |
| Tmédia (°C) | 27,12 | 27,94 | +0,82 | 27,29 |
| Umidade relativa média (%) | 55,73 | 44,55 | **−11,18** | 53,31 |
| Precipitação (mm) | 0,05 | 0,05 | ~0 | 1,60 |
| UTCI proxy | 32,46 | 32,89 | +0,43 | 31,19 |
| Risco cumulativo 3d | 5,70 | 10,13 | **+4,44** | 8,30 |

**Extremos em 01/08/2026 (Open-Meteo/SIS):**

| Indicador | Mín. | Máx. | P90 |
|---|---:|---:|---:|
| Tmax (°C) | 30,7 | **37,5** | 36,0 |
| Umidade (%) | **22** | 78 | 61 |
| UTCI proxy | 28,9 | 35,7 | 34,3 |
| Risco 3d | 0,0 | 22,8 | 16,2 |

**Municípios com maior Tmax projetada em 01/08/2026:** Várzea Grande (37,5 °C), Nossa Senhora do Livramento (37,4), Acorizal (37,2), Rosário Oeste (37,2), Cuiabá (36,6).

**Municípios com menor umidade projetada em 01/08/2026:** Novo São Joaquim, Pedra Preta, Nova Nazaré (UR ~22%), Água Boa e Ribeirãozinho (~23%).

### Leitura operacional (sem extrapolação indevida)

- Do dia **27/07** para **01/08**, o SIS indica **ligeiro aumento de Tmax** e **queda relevante de umidade** (~11 p.p.), com **chuva quase nula** — quadro de **estiagem relativa** no curto prazo.
- O **risco cumulativo 3d médio sobe** (~5,7 → ~10,1), coerente com persistência de calor.
- Em **02/08** a série sugere **alguma recuperação de umidade** e chuva média ~1,6 mm (ainda localizada; máx. municipal 15,6 mm) — horizonte curto, sujeito a atualização do Open-Meteo.

---

## 2. Situação operacional do SIS (resumo municipal atual)

| Item | Valor real |
|---|---|
| Municípios no resumo | 142 |
| Níveis | Laranja 67 · Vermelha 34 · Amarela 21 · Roxa 16 · Verde 4 |
| Predição 7d (níveis) | Vermelha 52 · Laranja 51 · Roxa 18 · Amarela 16 · Verde 5 |
| Tmax máximo na predição 7d | 38,0 °C (média dos máximos municipais 34,9 °C) |
| UTCI máx. na predição 7d | 36,2 (média 33,6) |
| Alertas inteligentes gerados | 142 municípios |
| Cemaden (registros na base) | 2 |
| ANA risco municipal | 11 |
| Ocupação IndicaSUS | Indisponível (login BdSES falhou nesta operação) |

**Top correlações Spearman (exploratórias, não causais):**

1. `risco_cumulativo_3d` → `pressao_calor_pct` (ρ ≈ 0,84; n = 142)  
2. `risco_calor_diario` → `pressao_calor_pct` (ρ ≈ 0,79; n = 142)  
3. `utci_proxy` → `pressao_calor_pct` (ρ ≈ 0,72; n = 142)

---

## 3. O que é projeção do SIS vs. cenário sazonal oficial

| Tipo | Horizonte | Fonte | O que afirma |
|---|---|---|---|
| Comparativo 27/07 → 01–02/08 | Curto (~7 dias) | Open-Meteo / `met_biometeo` (SIS) | Números da tabela acima |
| Predição operacional 7d | ~7 dias | SIS (`predicao_calor_7d_*`) | Níveis Verde→Roxa por município |
| Cenário ago.–set. (chuva/temp. sazonal) | Trimestre JAS/2026 | Painel El Niño INMET–CPTEC–INPE | Chuva abaixo da média no centro-norte; temperatura acima da média; potencial de queimadas — **não** é output numérico do SIS |

---

## 4. Referências (ABNT NBR 6023:2018)

Lista completa em [`REFERENCIAS_ABNT_6023.md`](REFERENCIAS_ABNT_6023.md).

Principais:

- CIEVS-MT (2026) — dados operacionais SIS (extração 27 jul. 2026).  
- OPEN-METEO (2026) — API de previsão de curto prazo.  
- INMET et al. (2026a) — Painel El Niño 2026-2027, boletim mensal n.º 01.  
- NOAA (2026); IRI (2026) — status ENSO / El Niño.
