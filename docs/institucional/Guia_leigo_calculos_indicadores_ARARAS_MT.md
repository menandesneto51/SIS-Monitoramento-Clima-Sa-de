# Guia leigo — Como o ARARAS MT calcula indicadores, pesos e classificações

**Produto:** ARARAS MT (Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde)  
**Público:** gestores, Sala de Situação, CRS/SMS, imprensa técnica e leitores do painel público  
**Versão:** 1.3 — 18/09/2026  
**Responsável técnico:** CIEVS-MT / SES-MT  

Este texto explica, em linguagem simples, **de onde vêm os números**, **como se combinam**, **quais pesos usam** e **o que cada cor significa**. Os valores de peso abaixo são os **padrões operacionais atuais** do sistema (podem ser recalibrados pelo CIEVS em `config/settings.yaml` / arquivos de índice, sem mudar o sentido geral).

**Novidade v1.3:** catálogo ampliado de **doenças e agravos** (além de SRAG e arboviroses): desidratação/calor, cardiovascular, respiratório e renal no SIM; DDA e internações por CID; intoxicação/fumaça; SINAN extras (hantavirose, leishmaniose visceral, febre maculosa, animais peçonhentos); malária; GAL/LACEN. Seção nova **“Agravos e doenças monitorados”**.

**Novidade v1.2:** **IRM** (capacidade CNES) e domínio RIT **fragilidade de rede**; compostos `gap_fumaca_nebulizacao` e `pressao_x_resiliencia`; frescor obrigatório (IRM→RIT→compostos) antes de alertas, boletim e painel.

**Novidade v1.1:** linhagem oficial do **EHF GeoCalor (STAR)** → resumo → RIT e alertas; distinção da aba “GeoCalor” de risco relativo cardiorrespiratório.

---

## 1. Regra de ouro (leia antes de tudo)

1. **Sinal do ARARAS ≠ decreto de emergência.** Cores e notas apoiam a decisão; não ativam COE, portaria nem emergência sozinhas.
2. **Ausência de dado ≠ risco zero.** Município sem PM2,5, sem leito IndicaSUS ou sem estação de rio pode estar em risco — só faltou medição.
3. **Há produtos diferentes no painel.** Não misture:
   - **Nível operacional** (Verde → Roxa) — “como está agora”, regra de estágio.
   - **Predição ~7 dias** — só **calor projetado** da semana seguinte.
   - **RIT** — **multirisco observado** (calor + fumaça + hidro + EHF + pressão fresca + fragilidade de rede).
   - **IRM** — **capacidade** da rede CNES (alto = melhor); no RIT entra só o inverso (fragilidade).
   - **Prioridade global** — ranking de gestão (0–100), não é o semáforo de alerta.
   - **Cenário epidemiológico / saúde-calor** — **doenças e agravos** (SRAG, arbov, DDA, cardio/renal, fumaça…); não é o RIT.
4. **Ocupação IndicaSUS ≠ pressão SISREG.** São pilares distintos da pressão sobre a rede.

---

## 2. As cinco “leituras” que mais confundem

| Nome no painel | O que responde | Horizonte | O que entra |
|---|---|---|---|
| **Nível** (`nivel`) | Qual estágio operacional do município hoje? | Rodada atual | Vários candidatos (calor, ar, saúde, hidro…); o sistema fica com o **mais grave** |
| **Predição ~7 dias** (`nivel_predicao_7d`) | O calor tende a piorar na semana seguinte? | ~7 dias | **Só térmico projetado** |
| **RIT** (`rit_0_100` / `rit_faixa`) | Qual o pior sinal multirisco observado agora? | Rodada atual | Máximo entre térmico, ar/PM2,5, hidro, EHF, pressão (se fresca) e **fragilidade de rede** |
| **IRM** (`indice_resiliencia_municipal_0_100`) | Quão capaz está a rede CNES? | Rodada atual | Estab/leitos/profissionais/eAB/nebulização (capacidade; alto = melhor) |
| **Prioridade global** (`indice_prioridade_global`) | Quem ligar primeiro na gestão? | Rodada atual | Soma **ponderada** de vigilância, pressão, adaptação, fragilidade e alerta |

Analogia: o **nível** é o semáforo da rua; a **predição 7 dias** é a previsão do tempo só de calor; o **RIT** é “qual alarme está mais alto agora na casa”; o **IRM** é “quão reforçada está a rede de saúde”; a **prioridade** é a lista de quem o plantão liga primeiro.

---

## 3. Classificação por cores (Verde → Roxa)

Usada no **nível operacional**, na **predição ~7 dias**, na **faixa do RIT** e em vários mapas categóricos.

| Cor | Leitura leiga | O que fazer (orientação geral) |
|---|---|---|
| **Verde** | Situação sob controle / habitual | Monitoramento de rotina |
| **Amarela** | Atenção — sinais acima do esperado | Reforçar vigilância e comunicação com a regional |
| **Laranja** | Alerta — pressão climática ou de saúde relevante | Priorizar grupos vulneráveis e rede assistencial |
| **Vermelha** | Resposta intensificada | Mobilização operacional; acompanhar de perto |
| **Roxa** | Situação excepcional | Máxima prioridade técnica; ainda assim ≠ decreto automático |
| **Cinza** | Sem leitura confiável / lacuna | Não interprete como “tudo bem” |

**Pontuação interna do estágio:** verde = 0 · amarela = 1 · laranja = 2 · vermelha = 3 · roxa = 4.

---

## 4. Fontes de dados (de onde vêm os números)

| Família | Exemplos no painel | Fontes típicas |
|---|---|---|
| Clima / calor | Tmáx, UTCI proxy, risco 3 dias, **EHF GeoCalor** | Open-Meteo / ERA5-Land; tabela `star_clima_geocalor_diario` |
| Ar e fogo | PM2,5, IQA, focos 24h/7d | Qualidade do ar / satélite e produtos de queimadas |
| Hidrologia / desastre | Nível de rio, alerta hidro, Cemaden | ANA, Cemaden e alertas oficiais mesclados |
| Assistência | Ocupação de leitos, fila/solicitações, internações por CID | **IndicaSUS** (ocupação + VW_INTERNACAO), **SISREG** (regulação) |
| Epidemiologia | SRAG, arboviroses, DDA, intoxicação/fumaça, SINAN extras, malária | SIVEP, SINAN/DW e bases epidemiológicas do fluxo estadual |
| Mortalidade | Óbitos sensíveis ao calor e cardiorrespiratório/renal | **SIM** (grupos CID — ver seção 4b) |
| Laboratório | Positividade recente | **GAL/LACEN** |
| Rede / território | Capacidade CNES, resiliência, aldeias/quilombos, nebulização APS | CNES, cadastros territoriais, e-SUS (quando disponível e fresco) |
| Adaptação | Riscos AdaptaSUS, índice de adaptação | Matriz AdaptaSUS configurada no ARARAS |

Cada rodada registra **frescor** (quão recente está a fonte). Dado velho pode ser omitido (ex.: pressão no RIT se > 14 dias).

---

## 4b. Agravos e doenças monitorados (além do “só SRAG/dengue”)

O ARARAS **não** se limita a gripe/SRAG e dengue. O painel e o boletim acompanham um **pacote clima–saúde** alinhado ao Plano El Niño / AdaptaSUS. Em linguagem simples:

### Onde olhar no painel

| Onde | O que aparece |
|---|---|
| Aba **Cenário Epidemiológico** | Arboviroses 7d · SINAN extras · intoxicação/fumaça · internações CID · malária/SRAG |
| Aba **SIVEP** / **Sentinela SG** | Série completa de SRAG e síndrome gripal (indicadores MS) |
| Aba **Óbitos / saúde-calor** (quando disponível) | Consolida SIM + SINAN + GAL + SRAG para leitura “calor × saúde” |
| **Índice de pressão (G/A/V)** | IndicaSUS + SISREG + SINAN + SIM (agravos com associação climática) |
| **Boletim semanal** | Cenários (calor, fumaça, hidro) com agravos esperados (ex.: DDA/leptospirose se inundação confirmada) |

### Pacote de doenças / desfechos (leitura leiga)

| Grupo | O que é | Fonte típica | Entra em… |
|---|---|---|---|
| **Arboviroses** | Dengue, chikungunya (Zika quando houver view no DW) | SINAN | Carga em saúde · pressão · Cenário Epidemiológico |
| **SRAG / respiratório** | Síndrome respiratória aguda grave, UTI, óbitos | SIVEP (preferencial); SINAN DW se vazio | Carga · nível · SIVEP |
| **Desidratação / calor direto** | Exaustão, insolação, desidratação (CID E86, E87, T67, X30) | SIM / internações IndicaSUS | Pressão (SIM) · saúde-calor · internações CID |
| **Cardiovascular** | Óbitos/agravos sensíveis ao calor (CID I*) | SIM | Pressão · GeoCalor (RR exploratório) |
| **Respiratório (mortalidade)** | Óbitos CID J* (calor + fumaça/PM2,5) | SIM | Pressão · saúde-calor |
| **Renal** | Lesão aguda / desfechos N17–N19 ligados a desidratação | SIM | Pressão · saúde-calor |
| **Endócrino-metabólico** | Diabetes (E10–E14) quando CID disponível no SIM | SIM | Grupo auxiliar no classificador de óbitos |
| **DDA (diarreia aguda)** | Doença diarreica aguda (CID A09, K52) — seca, estiagem e enchentes | Internações IndicaSUS / vigilância | Internações CID · narrativa hidro no boletim |
| **Intoxicação / fumaça** | Intoxicação exógena ligada a fumaça/queimada/incêndio | SINAN (VW intoxicação) | Sinal de fumaça · Cenário Epidemiológico · gap nebulização |
| **SINAN extras clima** | Hantavirose, animais peçonhentos, SRAG (SINAN), leishmaniose visceral, febre maculosa | SINAN/DW | Cards “extras clima” · enriquecimento municipal |
| **Malária** | Casos recentes (janela DW) | DW / SIVEP malaria | Cards Onda 2 · Cenário Epidemiológico |
| **Laboratório (GAL)** | Positividade recente (contexto, não diagnóstico individual) | GAL/LACEN | Saúde-calor consolidado |
| **Hidro (vigilância condicional)** | DDA, **leptospirose** e traumas se **inundação confirmada** | Narrativa boletim + alertas hidro | Não substitui notificação oficial; aciona vigilância |

Catálogo técnico: `config/monitoramento_agravos_el_nino.yaml` e `config/indice_pressao_semaforo.yaml` (`agravos_clima`).

### Regras que evitam confusão

1. **Nem todo agravo “puxa” o semáforo Verde→Roxa sozinho.** Muitos alimentam **Cenário Epidemiológico**, **pressão G/A/V**, **saúde-calor** ou o **boletim** — sem alterar a fórmula do RIT v1.
2. **Carga em saúde (seção 6.2)** continua com pesos fortes em **SRAG** e **arboviroses** (+ ar e pressão). Os demais agravos aparecem nas abas e no pacote SIM/internações.
3. **Ausência de linha ≠ zero casos.** View do DW vazia, atraso de notificação ou município sem hospital notificante.
4. **Correlação ecológica ≠ causalidade.** GeoCalor (RR) e odds ratio sazonal geram hipótese; não fecham laudo individual.
5. **Leptospirose / DDA pós-cheia** no boletim é **orientação de vigilância** quando o cenário hidro confirma inundação — não inventa incidência estadual.

---

## 5. Como nasce o **nível operacional** (Verde → Roxa)

### Ideia em uma frase

O município recebe vários “votos” de gravidade (calor, fumaça, SRAG, hidro, etc.). O nível final é o **mais alto** entre os votos válidos — não a média.

### Exemplos de candidatos

- Sensação térmica (**UTCI proxy**) e temperatura máxima (**Tmáx**)
- **Risco cumulativo de calor em 3 dias** (três dias quentes pesam mais que um pico isolado)
- Ondas / saturação do solo (quando disponíveis)
- Alertas **INMET**, **Cemaden**, risco **hidro ANA**
- Sinais assistenciais e epidemiológicos (z-scores SRAG/arbovírus, pressão)
- Qualidade do ar / IQA (quando configurado)

Os **limiares numéricos** (ex.: a partir de qual UTCI vira laranja) ficam em `config/settings.yaml` (`limiares_calor`, `limiares_assistenciais`, etc.) e podem ser ajustados pelo CIEVS.

### O que o nível **não** faz

- Não “soma tudo e divide”.
- Não é a predição de 7 dias.
- Não é o RIT (embora o domínio térmico do RIT use a classe atual quando existe).

---

## 6. Indicadores compostos do painel (0–100) e **pesos**

Três notas publicadas na Visão. Cada uma combina componentes **já normalizados**; se faltar um componente, o peso dele é redistribuído entre os disponíveis (completude cai).

### 6.1 Tensão climática

“Quão pesado está o clima (calor/estiagem) neste município?”

| Componente | Peso padrão |
|---|---|
| Risco cumulativo 3 dias | **50%** |
| UTCI (sensação) | **28%** |
| Temperatura máxima | **16%** |
| Umidade seca / estiagem | **6%** |

### 6.2 Carga em saúde

“Quão pressionada está a saúde (doença + ar + rede)?”

| Componente | Peso padrão |
|---|---|
| SRAG | **34%** |
| Arboviroses | **18%** |
| PM2,5 | **10%** |
| Queimadas | **8%** |
| Pressão assistencial | **30%** |

**Nota v1.3:** esta nota composta ainda enfatiza **SRAG + arboviroses**. Desidratação, DDA, intoxicação, SINAN extras, malária e grupos SIM cardiorrespiratório/renal entram sobretudo no **Cenário Epidemiológico**, no **semáforo de pressão (G/A/V)** e na consolidação **saúde-calor** — não “somem” só porque o peso da carga não os lista um a um.

### 6.3 Vigilância integrada

“Prioridade composta para olhar o território.”

| Componente | Peso padrão |
|---|---|
| Tensão climática | **42%** |
| Carga em saúde | **28%** |
| Pressão | **12%** |
| Nível operacional (Verde→Roxa) | **18%** |

Há ainda um **piso mínimo por nível** (ex.: município em Roxa não fica com vigilância “baixa” só por média): verde 0 · amarela 12 · laranja 24 · vermelha 38 · roxa 48 (escala 0–100).

### 6.4 Faixas comuns dos índices 0–100

| Faixa | Intervalo padrão |
|---|---|
| Baixa | até **30** |
| Moderada | até **60** |
| Alta | até **80** |
| Muito alta | **acima de 80** |

---

## 7. Prioridade global (ranking de plantão)

**Não substitui o nível colorido.** Serve para ordenar quem merece contato primeiro.

### Pesos padrão dos pilares

| Pilar | Origem | Peso |
|---|---|---|
| Vigilância | `indice_vigilancia_integrada` | **30%** |
| Pressão | `indice_pressao_saude` | **25%** |
| Adaptação | `indice_adaptacao_climatica` (AdaptaSUS) | **20%** |
| Fragilidade | 100 − resiliência | **15%** |
| Alerta | score/nível de alerta integrado | **10%** |

Pilar ausente → omitido e pesos **renormalizados**. A **completude da prioridade (%)** diz quantos pilares entraram.

Faixas: baixa ≤30 · moderada ≤60 · alta ≤80 · muito alta >80.

---

## 8. Índice de pressão sobre a saúde (semáforo G/A/V)

Combina quatro pilares da rede e da vigilância (pesos padrão do semáforo):

| Pilar | Fonte | Peso padrão |
|---|---|---|
| IndicaSUS | Ocupação de leitos | **30%** |
| SISREG | Fila / solicitações abertas | **20%** |
| SINAN / epidemiológico | Arboviroses, SRAG e demais z-scores / casos 7d sensíveis ao clima | **30%** |
| SIM | Óbitos na janela: calor direto, desidratação, cardio, resp, renal | **20%** |

Leitura do semáforo de pressão (escala 0–100 tipicamente):

- **Verde** até ~39  
- **Amarela** até ~69  
- **Vermelha** acima disso  

Sem hospital notificante no IndicaSUS **não significa risco zero** — use SISREG e o restante do painel.

---

## 9. RIT — Risco Integrado Territorial (multirisco observado)

### Ideia em uma frase

Olhamos seis “alarmes” do território **hoje**. O RIT fica com o **alarme mais alto** (máximo), não a média.

### Domínios

| Domínio | Como vira 0–100 (resumo) |
|---|---|
| **Térmico** | Classe atual Verde→Roxa mapeada (0, 25, 50, 75, 100) ou, se não houver, limiares de UTCI/Tmáx |
| **Ar / PM2,5** | µg/m³: ≥25 → 50; ≥50 → 75; ≥75 → 100 |
| **Hidrologia** | Nível hidro/Cemaden ou situação (estiagem/cheia) mapeada |
| **EHF** | Onda de calor Excess Heat Factor: ≤0 → 0; >0 → ≥70; valores altos → 85–100 |
| **Pressão** | Usa `indice_pressao_saude` **somente se a fonte tiver ≤ 14 dias**; senão o domínio é **omitido** |
| **Fragilidade de rede** | `100 − IRM` (capacidade CNES). IRM alto **não** eleva o RIT; IRM nulo → domínio omitido |

### IRM — Índice de Resiliência Municipal (capacidade)

Produto **paralelo** ao RIT: quanto maior, **melhor** a capacidade assistencial (estabelecimentos, leitos, profissionais, eAB e nebulização CNES, pesos 25/25/20/15/15). Completude < 40% → IRM nulo (não inventa). Distinto do índice de resiliência operacional legado.

### Faixa do RIT (mesma lógica visual da térmica)

| Score RIT | Faixa |
|---|---|
| 0–24 | Verde |
| 25–49 | Amarela |
| 50–69 | Laranja |
| 70–84 | Vermelha |
| 85–100 | Roxa |

### Scorecard (o que aparece em alertas e em “Por que este nível?”)

- Nota geral + faixa  
- **Domínio dominante** (quem “puxou” o RIT)  
- Radar compacto de todos os fatores (ex.: EHF:roxa · Ar:verde · Pressão:omitida)

### O que o RIT **não** é

- Não projeta 7 dias.  
- Não substitui o nível operacional.  
- Não inclui vulnerabilidade cadastral (idosos, gestantes, povos tradicionais) como elevador da nota v1 — isso entra em mapas/narrativa de prioridade.

### Linhagem EHF / IRM → painel e alertas

```
ETL STAR (CDS ou Open-Meteo archive) + DW CNES
        ↓
star_clima_geocalor_diario  (+ densidades CNES / nebulização)
        ↓
refresh_resumo_multirisco (EHF → IRM → RIT → compostos)
        ↓
   ┌────┴────┐
   RIT       Alertas multinível / digest
   Visão     (bloco GeoCalor + IRM + scorecard)
   Mapas
   Boletim
```

- Campos no resumo: `ehf_geocalor`, `intensidade_ehf`, `is_hw_day`, `duracao_onda_ehf_dias`, `data_ehf_geocalor`, `indice_resiliencia_municipal_0_100`, `rit_score_rede`.  
- Antes do digest de alertas e na abertura do painel, o sistema **reaplica** IRM/RIT/compostos.  
- **Não confundir** com a aba do menu chamada “GeoCalor” (risco relativo cardiorrespiratório) — é outro produto.  
- A **onda P95** (`onda_calor_p95_2d`) continua como candidato legado do nível ARARAS; **não substitui** o EHF Fiocruz.

---

## 10. Predição térmica ~7 dias

- Campo principal: `nivel_predicao_7d` (e scores auxiliares de risco preditivo).  
- Responde: “a **classe de calor** tende a subir, manter ou cair na semana seguinte?”  
- **Não inclui** EHF futuro, fumaça, hidro nem pressão na mesma regra de classe.  
- Por isso o boletim e o painel mostram o card **MODELO ~7 DIAS** ao lado do **RIT**.

A **tendência ~7 dias** no painel cruza o nível atual com essa projeção (agravamento / estável / redução) — horizonte operacional da semana, **não** cenário sazonal ASO/El Niño.

---

## 11. Outros indicadores que você vê com frequência

| Indicador | Em uma frase |
|---|---|
| **EHF GeoCalor** | Índice de onda de calor Fiocruz (EHF); aparece na Visão, Mapas e alertas |
| **Risco cumulativo 3 dias** | Acúmulo de calor recente; três dias quentes > um pico isolado |
| **UTCI proxy** | Como o corpo sente o calor (temperatura + umidade + vento) |
| **PM2,5 / IQA** | Partículas finas / qualidade do ar; focos de queimada mostram fogo mesmo sem PM municipal |
| **Vulnerabilidade ao calor** | Idosos, crianças, rural e exposição territorial |
| **Arboviroses 7d** | Pressão recente de dengue/chikungunya (Zika se houver) — não é a temporada inteira |
| **SRAG / SIVEP** | Casos, UTI e óbitos respiratórios graves; Sentinela SG é outro produto (unidades sentinela) |
| **Desidratação / calor (CID)** | E86, E87, T67, X30 — morbimortalidade por exposição ao calor |
| **SIM grupos clima** | Cardio (I*), resp (J*), renal (N*), endócrino (E10–E14) além do calor direto |
| **DDA** | Diarreia aguda (A09/K52) — seca, estiagem e enchentes; internações CID |
| **Intoxicação / fumaça** | SINAN intoxicação exógena filtrada por fumaça/queimada |
| **SINAN extras clima** | Hantavirose, animais peçonhentos, LV, febre maculosa, SRAG (SINAN) |
| **Malária 7d** | Casos recentes no recorte DW (quando enrich ativo) |
| **Internações CID clima** | IndicaSUS/VW_INTERNACAO agrupadas (resp, DDA, desidratação, cardio) |
| **Odds ratio / sazonalidade** | Comparação ecológica mês atual × histórico (não é causalidade individual) |
| **Completude (%)** | Quanto do cálculo pôde usar dado válido nesta rodada |
| **Fumaça sem PM** | Focos de queimada com PM2,5 nulo — não é ar limpo |
| **IRM** | Capacidade CNES 0–100 (alto = melhor); inverso no RIT como fragilidade de rede |
| **Gap fumaça × nebulização** | Sinal de fumaça/intox com nebulizadores CNES = 0 |
| **Pressão × RIT** | Quando a faixa da pressão assistencial diverge da faixa do RIT |
| **Pressão × resiliência** | Pressão assistencial vs faixa do IRM (tensão capacidade × demanda) |
| **Completude Sala** | % de fontes críticas presentes na linha municipal |
| **SISAGUA / Entomologia / Denúncias** | Vigilância ambiental via CSV `ops_*` (lacuna explícita se sem carga) |

---

## 11b. Recomendações e orientações

- O checklist por **nível** (verde→roxa) continua valendo.
- Há recomendações **contextuais** quando o RIT é puxado por ar/EHF/hidro/pressão/rede, quando há onda GeoCalor ativa, persistência roxa ou fumaça sem PM.
- Orientações por persona (CIEVS, APS, regulação, SAF, Visa, territórios) usam a mesma fonte no painel, Telegram e boletim.

---

## 12. Completude, defasagem e “por que sumiu um número?”

1. **Componente faltando** → peso redistribuído; a nota continua, mas a completude cai.  
2. **Pressão no RIT com >14 dias** → domínio omitido (não zera o RIT “na marra”).  
3. **IRM com completude < 40%** → IRM nulo e domínio `rede` omitido (não inventa capacidade).  
4. **Sem leitos IndicaSUS** → ocupação pode aparecer vazia ou “sem hospital”; olhe SISREG.  
5. **Mapa “vazio”** → cobertura parcial da fonte, não ausência de risco.  
6. **Cinza** → não classifique como verde.
7. **PM proxy Open-Meteo** → só se `USE_OPENMETEO_PM_PROXY=true`; marca `fonte_pm25=proxy_openmeteo`.

---

## 13. Onde conferir no próprio sistema

| Onde | O que encontrar |
|---|---|
| Aba **Guia do leitor** | Cores + glossário em linguagem simples |
| Aba **Cálculos** | Pesos atuais de tensão / carga / vigilância |
| Aba **Visão** | Cards, RIT, risco 3d, prioridades (painel interno) |
| Aba **Cenário Epidemiológico** | Arboviroses, extras SINAN, intoxicação, internações CID, malária |
| Aba **SIVEP** / **Sentinela SG** | SRAG e síndrome gripal (série MS) |
| Aba **Fontes e qualidade** | Frescor e cobertura das bases |
| “Por que este nível?” | Motivo do estágio + scorecard RIT |
| ADR técnico | `docs/adr/ADR-RIT-multirisco.md` (detalhe do RIT) |
| Catálogo de agravos | `config/monitoramento_agravos_el_nino.yaml` |

---

## 14. Perguntas frequentes

**O município está Roxa no RIT e Laranja no nível. Errou?**  
Não necessariamente. O RIT pode estar alto por **fumaça, EHF ou rede frágil**, enquanto o estágio operacional ainda pesa outros critérios. São produtos paralelos.

**IRM alto piora o RIT?**  
Não. IRM alto = boa capacidade; no RIT entra só a **fragilidade** (`100 − IRM`).

**A predição 7d está Vermelha e o RIT Verde. Como?**  
A semana seguinte pode projetar calor forte; o RIT olha o **agora** multirisco. Ou o contrário.

**Posso usar só a prioridade global para alertar a população?**  
Não. Para comunicação de risco use o **nível** e os boletins oficiais. A prioridade é ferramenta de **gestão/plantão**.

**Os pesos podem mudar?**  
Sim, por calibragem do CIEVS. O painel (aba Cálculos) mostra os pesos **em vigor** na rodada. Este guia descreve o padrão de setembro/2026 (v1.3).

**Só monitoramos dengue e SRAG?**  
Não. O pacote inclui desidratação/calor, cardio/resp/renal no SIM, DDA, intoxicação/fumaça, SINAN extras, malária e GAL — ver **seção 4b**. A nota “carga em saúde” ainda pesa mais SRAG+arbov; o restante aparece nas abas epidemiológicas e no semáforo de pressão.

**IA do sistema diagnostica paciente?**  
Não. O ARARAS apoia vigilância e gestão; não substitui conduta clínica nem protocolo do MS/SES.

---

## 15. Resumo de uma página (para projetar na Sala)

1. **Nível** = pior estágio entre vários sinais de hoje.  
2. **~7 dias** = só calor projetado.  
3. **RIT** = pior entre calor, ar, hidro, EHF, pressão fresca e fragilidade de rede (máximo).  
4. **IRM** = capacidade CNES (alto = melhor); inverso no domínio rede do RIT.  
5. **Tensão / carga / vigilância** = notas 0–100 com pesos da seção 6 (carga ainda SRAG+arbov-centrada).  
6. **Prioridade global** = ranking ponderado (30/25/20/15/10).  
7. **Pressão saúde** = IndicaSUS + SISREG + SINAN + SIM (agravos clima).  
8. **Doenças monitoradas** = além de SRAG/dengue: desidratação, cardio/resp/renal, DDA, fumaça/intox, extras SINAN, malária (seção 4b).  
9. **Sem dado ≠ sem risco.** **Sinal ≠ decreto.**

---

*Documento gerado para uso institucional SES-MT / CIEVS-MT. Em caso de divergência pontual com a tela, prevalece a configuração ativa da rodada (aba Cálculos + fontes). Contato operacional: canais oficiais do CIEVS-MT.*
