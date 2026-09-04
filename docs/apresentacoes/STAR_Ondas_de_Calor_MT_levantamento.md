# Levantamento STAR — Ondas de Calor (Anexo 1)

**Oficina STAR · Materiais necessários · Tema: Ondas de Calor**  
**Unidade:** CIEVS-MT / SES-MT · plataforma operacional **ARARAS MT**  
**Data de referência da rodada:** 03/09/2026 (SE 35/2026)  
**Natureza:** levantamento técnico com dados disponíveis + lacunas explícitas (não substitui protocolo clínico nem avisos oficiais INMET/Defesa Civil)

---

## 0. Produtos gerados neste levantamento

| Produto | Caminho |
|---------|---------|
| Nota técnica (este documento) | `docs/apresentacoes/STAR_Ondas_de_Calor_MT_levantamento.md` |
| Tabela municipal ampliada (142 mun.) | `data/output/star/STAR_ondas_calor_municipal_SE35_2026.csv` |
| Resumo JSON de indicadores | `data/output/star/STAR_resumo_indicadores.json` |
| Tabela-base da rodada semanal | `data/output/boletim/rodada_semanal_SE_35-2026.csv` |
| Script de exportação | `scripts/exportar_star_ondas_calor.py` |
| Mapas boletim SE 35 | `docs/apresentacoes/_assets_SE_35-2026/` |

**Convenção de status no checklist:**  
- **Disponível** — dado/definição operacional utilizável agora  
- **Parcial** — existe, mas janela, cobertura ou estratificação incompleta  
- **Lacuna** — solicitado no Anexo e ainda sem série/camada adequada no ARARAS

---

## 1. Checklist Anexo STAR (item a item)

### Bloco A — Análise epidemiológica e climática (mínimo 5 anos)

| Item do Anexo | Status | Evidência / fonte ARARAS–SES | Lacuna / observação |
|---|---|---|---|
| Série histórica de ondas de calor, Tmáx, anomalias e alertas por ano/mês/SE | **Parcial** | `met_biometeo`; `hist_clima_municipal_diario` (28/04/2026–09/09/2026; 2.612 linhas); `inmet_alertas` (57 registros recentes); boletim SE 35 | Sem arquivo climatológico ≥5 anos municipal; anomalias atuais ≠ climatologia 1981–2010; alertas sem arquivo histórico 5 anos |
| Definição de limiares (duração, intensidade, áreas) | **Disponível** | `config/settings.yaml` (`limiares_calor`); `sisclima/engines/biometeo.py` (P95 ≥2 dias, EHF, UTCI, risco cumulativo 3d) | P95 municipal ainda frequentemente proxy (q70 da previsão), não climatologia oficial |
| Mapas temáticos (exposição, ilhas de calor, arborização, densidade, vulnerabilidade) | **Parcial** | Mapas classe atual / projeção 7d / territórios tradicionais (boletim SE 35); `geo_vulnerabilidade_municipal` (densidade, idosos, rural) | **Sem** camada de ilha de calor urbana, arborização ou NDVI |
| Tendências, sazonalidade, períodos de maior risco e previsão | **Parcial** | `periodo_critico_meses` = jul–nov; sazonalidade operacional; predição clima 7d; narrativa El Niño no boletim | Sem produto de previsão climática sazonal oficial embutido (CPTEC/INMET/FUNCEME só como referência textual) |
| Atendimentos, internações, remoções e óbitos relacionados ao calor | **Parcial** | `saude_calor_*`; `epi_sim_obitos_calor` (2024-01 a 2026-08); SQL SIM/SIH; pressão SISREG (proxy de demanda) | Janela SIM ~2 anos no SQL; flag “óbito calor direto” pouco preenchida (0 suspeitos na tabela agregada); remoções/ambulância não rotinizadas |
| Distribuição por faixa etária, sexo, município/região e grupos vulneráveis | **Parcial** | SIM bruto tem Sexo/Idade/FaixaEtaria; vulnerabilidade IBGE por município; regionais de saúde | Agregados `saude_calor_*` perdem estratificação; sem tabela STAR rotineira idade×sexo×calor |
| Aumento de demanda / sobrecarga dos serviços | **Disponível (proxy)** | IndicaSUS ocupação estadual 57,0% (3.346/5.872 leitos; 85 mun.); `pressao_calor_pct`; semáforo SISREG | Cobertura ocupação incompleta (57 mun. sem leitos elegíveis/IndicaSUS); ocupação ≠ pressão |
| Outras análises pertinentes | **Disponível** | Impacto da chuva de 01/09; PM2,5; focos; Cuiabá 40,4 °C (31/08) | — |

### Bloco B — Caracterização do evento e impactos à saúde

| Item do Anexo | Status | Evidência | Lacuna |
|---|---|---|---|
| Impactos diretos observados (desidratação, insolação, cardio/respiratório/renal) | **Parcial** | Grupo `obitos_sensivel_calor` = 15.329 eventos na série estadual (2024-01→2026-09); CIDs E86/E87/T67/X30 + sensíveis no catálogo | Poucos eventos tipados como calor direto (T67/X30) nos agregados; GeoCalor ainda insuficiente para RR diário |
| Impactos indiretos (água, alimentos, DTHA, ar, serviços essenciais) | **Parcial** | PM2,5 (18/142 ≥25 µg/m³); focos 7d; hidro/estiagem parcial; arbovirose no consolidado saúde-calor | Vigiágua/qualidade de alimentos e interrupção de serviços sem série municipal completa |
| Fatores amplificadores | **Parcial** | UR baixa (alertas INMET); trabalho ao ar livre (narrativa AdaptaSUS/boletim); densidade/idosos/rural | Sem indicador municipal de moradia sem ventilação / eventos de massa / abrigos |
| Grupos vulneráveis | **Parcial** | Idosos %, crianças 0–4 %, rural %, territórios tradicionais, índice vulnerabilidade calor | Sem rotina estadual para situação de rua, PPL, gestantes e imunossuprimidos em recorte calor |
| Outras características do território | **Disponível** | El Niño confirmado; SE crítica jul–nov; combinação calor+fumaça | — |

### Bloco C — Sistema de vigilância e capacidade de resposta

| Item do Anexo | Status | Evidência | Lacuna |
|---|---|---|---|
| Estrutura da vigilância (federal / estadual / municipal) | **Disponível** | CIEVS-MT; Portaria 0590/2026/GBSES (Sala); ARARAS MT; Vigidesastres; avisos INMET; AdaptaSUS | Inventário formal de capacidades municipais ainda incompleto |
| Insumos, exames e protocolos | **Parcial** | Limiares assistenciais/operacionais; estoque/autonomia em módulo operacional; catálogo Plano El Niño | Quantitativos de insumos/laboratório por município não inventariados neste levantamento |
| Recursos humanos e lacunas | **Lacuna** | — | Sem quadro RH estadual/municipal específico para ondas de calor no ARARAS |
| Articulação intersetorial | **Disponível** | Matriz áreas SES do Plano El Niño / boletim; SEMA/CBM (atos ambientais); assistência social citada na governança | Intensidade da articulação varia por regional — não há score único |
| Planos, políticas, normas | **Disponível** | Portaria 0590/2026; Decreto 2.015/2026 (emergência ambiental); Plano El Niño SES-MT; minuta Portaria ARARAS; AdaptaSUS | Planos municipais de calor extremo não catalogados em base única |
| Desafios e oportunidades | **Disponível** | Ver seção 7 | — |

---

## 2. Limiares operacionais de onda de calor (ARARAS MT)

Fonte normativa operacional: `config/settings.yaml` + motor `sisclima/engines/biometeo.py`.  
**Não substituem** avisos oficiais do INMET.

### 2.1 UTCI / proxy (conforto térmico)

| Classe | Limiar UTCI/proxy (°C) |
|--------|-------------------------|
| Verde | ≤ 26 |
| Amarela | ≤ 32 |
| Laranja | ≤ 38 |
| Vermelha | ≤ 46 |
| Roxa | > 46 (ou combinação com outros pilares) |

### 2.2 Fallback por temperatura máxima (quando UTCI formal indisponível)

| Classe | Tmáx (°C) |
|--------|-----------|
| Amarela | ≥ 37 |
| Laranja | ≥ 39 |
| Vermelha | ≥ 41 |
| Roxa | ≥ 43 |

### 2.3 Risco cumulativo 3 dias (acima de limiar térmico)

- Umbral de temperatura: **39 °C**  
- Escala: amarela ≥3 · laranja ≥7 · vermelha ≥12 · **roxa ≥18**

### 2.4 Excess Heat Factor (EHF) adaptado

- EHF positivo: **> 0**  
- Persistência para emergência: **5 dias**

### 2.5 Definição operacional de “onda de calor” (duração / intensidade)

1. Identifica-se dia com temperatura média **acima do P95** local (`dia_acima_p95_tmedia`).  
2. Conta-se a **duração consecutiva** (`duracao_onda_calor_dias`).  
3. Flag de onda: **≥ 2 dias** consecutivos (`onda_calor_p95_2d = 1`; `min_dias` padrão = 2).  
4. Calculam-se `intensidade_onda_calor` e `severidade_onda_calor`; EHF adaptado quando disponível.

**Atenção metodológica:** na ausência de climatologia municipal longa, o P95 pode ser **proxy** (quantil 70 da própria série de previsão, com piso 27,5 °C). Isso detecta persistência relativa em tempo real, **mas não deve ser lido como anomalia climatológica oficial**.

### 2.6 Período crítico sazonal (estado)

Meses de maior risco operacional configurados: **julho a novembro** (`periodo_critico_meses: [7,8,9,10,11]`).

### 2.7 CID / grupos monitorados (saúde–calor)

Catálogo operacional (`config/monitoramento_agravos_el_nino.yaml`):

- Desidratação / efeitos do calor: **E86, E87, T67, X30**  
- Mortalidade sensível a calor: cardiocirculatório / respiratório / renal (conjunto SIM em `sql/dw_sim_obitos_calor.sql`)

---

## 3. Situação atual do território (SE 35/2026 · 03/09/2026)

### 3.1 Cartões estaduais

| Indicador | Valor |
|-----------|------:|
| Municípios em vermelho ou roxo (atual) | **115/142 (81,0%)** |
| Municípios em vermelho ou roxo (projeção ~7 dias) | **128/142 (90,1%)** |
| Distribuição atual | amarela 2 · laranja 25 · vermelha 51 · **roxa 64** |
| Tmáx máxima (rodada) | **39,3 °C** (Cocalinho) |
| Municípios com Tmáx ≥ 37 °C | **15** |
| Municípios com PM2,5 ≥ 25 µg/m³ | **18** |
| Flag onda P95≥2d na rodada | **2** municípios |
| Ocupação hospitalar IndicaSUS | **57,0%** (3.346/5.872; 85 mun. com ocupação) |
| Histórico climático local acumulado | 28/04/2026 a 09/09/2026 |

### 3.2 Impacto da chuva de 01/09/2026 (alívio temporário)

| Data | Mun. com chuva ≥1 mm | Mun. Tmáx ≥37 °C | Tmáx média (°C) |
|------|---------------------:|-----------------:|----------------:|
| 31/08 | 6 | 54 | 36,6 |
| **01/09** | **85** | **15** | **34,7** |
| 02/09 | 44 | 1 | 33,2 |
| 03/09 | 13 | 8 | 34,9 |

Leitura: a pancada de segunda reduziu a intensidade térmica e o número de municípios em calor extremo; a projeção de 7 dias, contudo, **volta a pressionar** (~90% vermelho/roxo). Não houve “fim” da onda estadual — houve **oscilação**.

### 3.3 Cuiabá (referência)

| Registro | Valor |
|----------|------:|
| Pico Open-Meteo / ARARAS (31/08) | **40,4 °C** (alinhado à mídia ~41 °C) |
| 01/09 (com chuva) | queda acentuada de Tmáx + UR mais alta |
| Rodada 03/09 | Tmáx ~37,2 °C · classe **roxa** · pred. 7d **roxa** |

Diferenças de ~0,5–1 °C entre mídia e grade são esperadas (ponto de grade × estação urbana).

### 3.4 Top 10 Tmáx (rodada)

| Município | Regional | Tmáx (°C) | Classe | PM2,5 |
|-----------|----------|----------:|--------|------:|
| Cocalinho | Água Boa | 39,3 | roxa | 14,6 |
| Nova Nazaré | Água Boa | 38,7 | roxa | 23,4 |
| Araguaiana | Barra do Garças | 38,6 | roxa | 18,1 |
| Novo Santo Antônio | São Félix do Araguaia | 38,6 | roxa | 19,5 |
| Canabrava do Norte | Porto Alegre do Norte | 38,0 | roxa | 21,6 |
| Água Boa | Água Boa | 37,9 | roxa | 30,4 |
| Nova Xavantina | Barra do Garças | 37,7 | roxa | 38,7 |
| Luciara | São Félix do Araguaia | 37,6 | roxa | 49,1 |
| Canarana | Água Boa | 37,4 | roxa | 18,0 |
| Cuiabá | Baixada Cuiabana | 37,2 | roxa | 10,2 |

### 3.5 Top 10 vulnerabilidade ao calor (índice IBGE/ARARAS)

| Município | Índice | Idosos % | Classe |
|-----------|-------:|---------:|--------|
| São José do Povo | 58,9 | 26,2 | vermelha |
| Nossa Senhora do Livramento | 52,5 | 21,0 | vermelha |
| Porto Estrela | 51,6 | 21,0 | vermelha |
| Vale de São Domingos | 50,5 | 18,0 | laranja |
| Acorizal | 49,6 | 21,4 | roxa |
| Ponte Branca | 48,3 | 22,5 | laranja |
| Nova Nazaré | 48,1 | 10,0 | roxa |
| Tesouro | 47,6 | 20,9 | laranja |
| Barão de Melgaço | 47,5 | 19,3 | vermelha |

### 3.6 Alertas meteorológicos recentes (INMET na base)

- **57** avisos ingeridos; predominam **Baixa Umidade** (40) e **Tempestade** (13).  
- Úteis como sinal oficial complementar; **não** formam ainda série histórica de 5 anos no ARARAS.

---

## 4. Bloco B — Impactos à saúde e fatores de risco

### 4.1 Impactos diretos (dados disponíveis)

Na consolidação `saude_calor_serie_estado` (jan/2024–set/2026):

| Grupo | Eventos (soma da série) |
|-------|------------------------:|
| Arbovirose (contexto El Niño / sazonal) | 113.233 |
| Outros | 34.380 |
| Óbitos sensíveis a calor (SIM agregado) | **15.329** |
| Positivos laboratório | 122 |
| SRAG | 98 |

`epi_sim_obitos_calor`: período **2024-01-01 a 2026-08-14**; total de óbitos na extração = 15.329. A coluna de “suspeitos calor direto” está **zerada** no agregado atual — indica necessidade de revisão da tipificação T67/X30/E86 no pipeline, não ausência absoluta de mortalidade sensível.

**Interpretação clínica (sem substituir avaliação caso a caso):** calor extremo aumenta risco de desidratação, exaustão, insolação e descompensação cardiovascular, respiratória e renal — alinhado aos CIDs monitorados.

### 4.2 Impactos indiretos já observáveis no estado

- **Qualidade do ar:** 18 municípios com PM2,5 ≥ 25 µg/m³ (máx. ~62 µg/m³ em Marcelândia na rodada).  
- **Fogo / fumaça:** focos elevados na janela 7d do boletim (centenas de focos; dezenas de municípios).  
- **Hídrico:** estiagem / nível de rio em recortes parciais (`hidro_risco` / determinantes da rodada).  
- **Arboviroses e DDA:** presentes no consolidado saúde–calor / SINAN; associação causal com onda específica exige estudo epidemiológico próprio.

### 4.3 Amplificadores de risco

- Baixa umidade (avisos INMET).  
- Trabalho ao ar livre e exposição ocupacional (orientação AdaptaSUS / boletim Saúde do Trabalhador).  
- Densidade urbana (ex.: Cuiabá) + população idosa elevada em municípios do interior.  
- Sobreposição calor + fumaça (Nova Xavantina, Luciara, Água Boa etc.).  
- Territórios tradicionais (`n_territorios_tradicionais` na tabela STAR).

### 4.4 Grupos vulneráveis — matriz STAR

| Grupo (Anexo) | Dado municipal rotineiro no ARARAS? | Como usar agora |
|---------------|-------------------------------------|-----------------|
| Crianças | Sim (`criancas_0_4_pct`) | Priorizar mun. com calor + alta proporção infantil |
| Idosos | Sim (`idosos_pct`, `idosos_60mais`) | Cruzar com classe vermelha/roxa |
| Gestantes | Não | Lacuna — acionar APS/SINASC pontualmente |
| Doenças crônicas / imunossuprimidos | Não (individual) | Lacuna — vigilância de unidades / Hiperdia |
| Situação de rua | Não | Lacuna — assistência social / consulta municipal |
| Privados de liberdade | Não | Lacuna — articulação SEJUDH/SES |
| Indígenas / quilombolas | Parcial (territórios) | Mapas boletim + DSEI/SESAI |
| Trabalhadores expostos | Narrativa / AdaptaSUS | Saúde do Trabalhador |
| Moradias precárias | Proxy rural / vulnerabilidade | Índice vulnerabilidade calor |

---

## 5. Bloco C — Vigilância e capacidade de resposta

### 5.1 Estrutura atual (níveis)

| Nível | Papel no tema Ondas de Calor |
|-------|------------------------------|
| **Federal** | INMET (avisos); MS / AdaptaSUS / Guia Mudanças Climáticas e Saúde; CIEVS Nacional |
| **Estadual** | CIEVS-MT (coordenação técnica); Sala de Situação (Portaria 0590/2026/GBSES); ARARAS MT (monitoramento integrado, boletim, alertas, registro Plano El Niño); Vigidesastres; áreas técnicas SES |
| **Municipal** | Vigilância em Saúde / Defesa Civil / APS e rede assistencial; uso do painel e alertas municipais (ex.: Cuiabá) |

### 5.2 Instrumentos e planos

- Portaria nº **0590/2026/GBSES** — Sala de Situação em Saúde (El Niño 2026–2027 e extremos climáticos).  
- **ARARAS MT** — ferramenta oficial de apoio (minuta Portaria ARARAS v3; complementar aos sistemas SUS).  
- **Plano El Niño SES-MT** — catálogo de indicadores/ações, validação CIEVS, briefing da Sala (`docs/PLANO_EL_NINO_SALA_SITUACAO.md`).  
- Decreto nº **2.015/2026** — emergência ambiental / queimadas (contexto agravante).  
- Limiares de autonomia de insumos, falhas de infraestrutura e comunicação em `settings.yaml` (módulos operacionais).

### 5.3 Articulação intersetorial (já prevista na governança)

Saúde (CIEVS, Vigilâncias, Assistência, Farmácia, Imunização, Saúde do Trabalhador, Vigiágua) · Meio Ambiente / SEMA · Corpo de Bombeiros · Educação · Assistência Social · Defesa Civil · DSEI/SESAI (territórios indígenas).

### 5.4 Insumos, exames, RH

| Tema | Situação neste levantamento |
|------|-----------------------------|
| Protocolos / limiares | Disponíveis (settings + biometeo + catálogo agravos) |
| Laboratório / insumos | Parcial (módulo estoque/autonomia; sem inventário STAR completo) |
| RH dedicado a ondas de calor | **Lacuna** — não inventariado no ARARAS |

### 5.5 Desafios

1. Série climática municipal **≥5 anos** ainda não consolidada (hist atual ~abril–set/2026).  
2. Anomalias e P95 sem climatologia oficial longa.  
3. Ausência de mapas de **ilha de calor / arborização**.  
4. Tipificação de óbitos/atendimentos “calor direto” frágil nos agregados.  
5. Ocupação IndicaSUS com cobertura parcial; pressão SISREG ≠ ocupação.  
6. DW epidemiológico depende de rede SES (timeout fora da VPN).  
7. GeoCalor cardiorrespiratório ainda com status insuficiente de dados diários.

### 5.6 Oportunidades de melhoria

1. Backfill Open-Meteo Archive → `hist_clima` (5 anos) e recomputo de P95/eventos.  
2. Ampliar SQL SIM/SIH para `YEAR−5` e preservar sexo/idade nos exports STAR.  
3. Export STAR automático semanal (reutilizar `scripts/exportar_star_ondas_calor.py`).  
4. Integrar camada GIS de temperatura de superfície / NDVI (parceiro ambiental).  
5. Rotina de validação CIEVS dos indicadores de calor no Plano El Niño.  
6. Fechar inventário municipal de planos de contingência a calor extremo.

---

## 6. Tabela municipal ampliada — dicionário resumido

Arquivo: `data/output/star/STAR_ondas_calor_municipal_SE35_2026.csv` (142 linhas).

Principais colunas além da rodada semanal:

- Exposição: `tmax`, `tmin`, `utci_proxy`, `umidade_media`, `risco_cumulativo_3d`, `onda_calor_flag`, `duracao_onda_calor_dias`, `intensidade_onda_calor`, `severidade_onda_calor`, `ehf_adaptado`, `pm25_ugm3`, `focos_queimadas_7d`  
- Flags: `tmax_ge_37`, `pm25_ge_25`, `ur_le_30`  
- Sobrecarga: `ocupacao_leitos_pct`, `fonte_ocupacao`, `pressao_calor_pct`, `semaforo_pressao`, `indice_pressao_saude`  
- Vulnerabilidade: `populacao`, `idosos_pct`, `criancas_0_4_pct`, `rural_pct`, `densidade`, `indice_vulnerabilidade_calor`, `n_territorios_tradicionais`  
- Saúde agregada: colunas `saude_calor_*` e `obitos_*_sim` quando disponíveis  
- Valores ausentes: células vazias / NaN (= **ND** / sem dado na rodada)

Para gerar de novo:

```bash
python scripts/exportar_star_ondas_calor.py
```

---

## 7. Resposta sintética ao Anexo (pronto para oficina)

1. **O estado está sob risco térmico alto disseminado** (81% vermelho/roxo; projeção 90%).  
2. **Há definição operacional clara de limiares** (UTCI, Tmáx, risco 3d, EHF, onda ≥2d P95).  
3. **A série ≥5 anos ainda é a principal lacuna** climática e, em parte, sanitária.  
4. **Impactos à saúde** são rastreados por mortalidade sensível e agravos climáticos, com necessidade de melhorar tipificação de calor direto e estratificação.  
5. **A capacidade de resposta estadual existe** (Sala, CIEVS, ARARAS, Plano El Niño, Vigidesastres), com lacunas de RH inventariado, GIS urbano e planos municipais catalogados.  
6. **A tabela municipal STAR** já permite priorização por exposição × vulnerabilidade × sobrecarga para a oficina.

---

## 8. Referências internas

- Anexo 1 — Avaliação STAR (Materiais_Ondas de Calor).pdf (oficina)  
- `config/settings.yaml` · `sisclima/engines/biometeo.py`  
- `config/monitoramento_agravos_el_nino.yaml` · `sql/dw_sim_obitos_calor.sql`  
- `docs/PLANO_EL_NINO_SALA_SITUACAO.md` · Portaria 0590/2026/GBSES  
- `docs/institucional/Minuta_Portaria_ARARAS_MT_v3.md`  
- `docs/apresentacoes/Boletim_ElNino_SE_35-2026.md`  
- `docs/apresentacoes/Sintese_Sala_SE_35-2026_reuniao_2026-09-04.md`

---

*Documento gerado para subsidiar a Oficina STAR. Dados sujeitos a atualização na próxima ETL/rodada ARARAS. Não inventa RH, estoques ou planos municipais inexistentes na base.*
