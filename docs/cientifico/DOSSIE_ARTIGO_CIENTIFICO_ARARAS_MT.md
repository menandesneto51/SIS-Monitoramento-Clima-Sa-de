# Dossiê técnico-científico — ARARAS MT

**Uso:** material de apoio à escrita de artigo científico (Methods, Results, Discussion).  
**Instituição:** CIEVS-MT / SES-MT.  
**Produto:** ARARAS MT — *Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde*.  
**Escopo territorial:** 142 municípios de Mato Grosso (universo IBGE oficial).  
**Versão deste dossiê:** 2026-08-31 (extraído do código e da documentação operacional do repositório).

> **Nota metodológica para o artigo.** Distinguir sempre: (i) **horizonte sazonal oficial** (Painel El Niño INMET–INPE–ANA–CEMADEN–SGB/CENSIPAM); (ii) **situação observada** na rodada ARARAS; (iii) **projeção operacional ~7 dias** do modelo térmico ARARAS. Associação espacial/temporal **não implica causalidade**.

---

## 1. Resumo executivo (Abstract framing)

O ARARAS MT é um sistema estadual de vigilância integrada clima–saúde que:

1. Ingere séries ambientais, assistenciais e epidemiológicas em escala municipal;
2. Classifica cada município em estágios operacionais de cinco cores (mais cinza = dados insuficientes);
3. Calcula índices compostos de prioridade e de pressão em saúde;
4. Emite alertas multinível (estadual, regional, municipal, Cuiabá) com validação prévia no painel;
5. Produz boletim semanal alinhado à Sala de Situação (Portaria nº 0590/2026/GBSES);
6. Acumula memória histórica diária e semanal para calibração retrospectiva (projeção × observado).

Alinha-se operacionalmente ao **AdaptaSUS** (MS) e ao **Guia de Mudanças Climáticas e Saúde**, com lacunas explícitas (ex.: SAN/SISVAN).

---

## 2. Identidade, governança e alinhamento normativo

| Elemento | Conteúdo |
|----------|----------|
| Nome | ARARAS MT (Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde) |
| Órgão | CIEVS-MT / Secretaria de Estado de Saúde de Mato Grosso (SES-MT) |
| Base normativa da Sala | Portaria nº 0590/2026/GBSES — Sala de Situação em Saúde (El Niño 2026–2027 e extremos climáticos) |
| Papel institucional | O ARARAS **informa e prioriza**; decisões de COE, portarias e comunicação pública permanecem com a gestão |
| Plano El Niño | Registro oficial eletrônico da Sala; 88 indicadores ARARA mapeados; cobranças por e-mail/WhatsApp; SEI = processo administrativo |
| AdaptaSUS | 4 eixos-chave; 6 riscos prioritários; scores municipais `adaptasus_risco_municipal` |
| Atos oficiais (IOMAT) | Decretos/portarias de emergência como **sinal normativo** ≠ ativação automática do Plano |

**Princípio de comunicação:** ocupação hospitalar (IndicaSUS) ≠ pressão hospitalar (SISREG).

---

## 3. Arquitetura técnica (Methods — sistema)

### 3.1 Camadas de dados

1. **Bronze** — ingestão bruta (CSV, API, SQL Server / DW SES).
2. **Silver** — padronização de colunas, datas, chaves IBGE, unidades e tipos de leito.
3. **Gold** — indicadores, classificação de níveis, recomendações e alertas.
4. **Dashboard** — Streamlit (consulta e validação); exportação auxiliar (CSV/Power BI).

### 3.2 Stack operacional

| Componente | Tecnologia / papel |
|------------|-------------------|
| Linguagem | Python (`sisclima`) |
| Painel | Streamlit |
| Banco | PostgreSQL (Docker, produção); SQLite (fallback) |
| Orquestração | Docker Compose (`app`, `db`, `etl-scheduler`, `alerts-scheduler`) |
| ETL | Extração completa preferencialmente **1×/dia** (`ETL_FULL_ONCE_PER_DAY`); health em `logs/etl_scheduler_health.json` |
| Alertas | Scheduler independente, condicionado a ETL recente (`ALERT_REQUIRE_FRESH_ETL`) |

### 3.3 Linhagem de sistemas antecedentes

TITAN (clima/biometeorologia), SENTINELA (sinais/rumores), AESOP (pressão assistencial), SIVEP/SRAG, LACEN/GAL, SINAN/SIM, IndicaSUS/CNES.

---

## 4. Fontes de dados (Methods — dados)

| Fonte | Papel no ARARAS | Status típico |
|-------|-----------------|---------------|
| Open-Meteo | Tmáx/Tmín, UR, vento, precipitação, solo; AQ se CAMS ausente | Operacional |
| Copernicus / CAMS | PM2,5 e correlatos (preferencial) | Opcional (credenciais) |
| INMET (Alert-AS) | Avisos oficiais de tempo severo / calor | Operacional no motor; flag configurável |
| INPE / Queimadas | Focos 24h e 7d por município | Operacional |
| CEMADEN | Alertas de desastres | Operacional |
| ANA (telemetria) | Risco hidrológico / chuva local | Operacional; cobertura parcial de estações |
| IndicaSUS / BdSES (filtros SIEGES) | Ocupação de leitos elegíveis | Operacional (rede SES); cobertura municipal parcial |
| SISREG | Solicitações / fila (pressão regulatória) | Operacional |
| CNES | Capacidade, geo, cobertura assistencial | Operacional (DW + API opcional) |
| SINAN (DW) | Agravos / arboviroses | Operacional |
| SIVEP-Gripe | SRAG (casos, UTI, óbitos, vírus) | Parcial (local / DW conforme disponibilidade) |
| SIM (DW) | Óbitos sensíveis a calor / cardiorrespiratório | Operacional quando view disponível |
| IBGE Censo 2022 | Demografia, vulnerabilidade, WASH estrutural | Operacional (WASH) |
| IOMAT | Decretos e portarias de emergência | Curadoria + ingestão |
| SGB | Citado no Painel El Niño oficial | Sem conector ETL municipal dedicado confirmado |
| SISVAN / SAN | Segurança alimentar e nutricional | Lacuna (Fase 2) |

---

## 5. Indicadores climáticos e ambientais

### 5.1 Variáveis principais

| Indicador | Descrição operacional |
|-----------|----------------------|
| Tmáx / Tmín | Temperatura máxima/mínima diária (°C) |
| UR | Umidade relativa média (%) |
| UTCI (proxy) | Estresse térmico; faixas de estágio em `config/settings.yaml` |
| Risco cumulativo 3d | Persistência de calor acima de limiar térmico |
| PM2,5 | Material particulado fino (µg/m³) — CAMS ou Open-Meteo AQ |
| IQA (score operacional) | Classe de qualidade do ar; **não substitui laudo oficial** |
| Focos de calor | INPE (24h / 7d); satélite de referência AQUA_M-T no boletim |
| Precipitação | mm/dia; limiares ANA auxiliares |
| Saturação do solo | Índice 0–100 a partir de umidade volumétrica (não calibrado por pedologia municipal) |
| Hidrologia | Risco estiagem/cheia via estações ANA mapeadas |

### 5.2 Limiares de calor / UTCI (estágio operacional)

**UTCI / proxy** (`limiares_calor.utci`):

| Classe | Limite |
|--------|--------|
| Verde | ≤ 26 °C |
| Amarela | > 26–32 |
| Laranja | > 32–38 |
| Vermelha | > 38–46 |
| Roxa | acima de 46 |

**Fallback por Tmáx** (quando UTCI indisponível): amarela ≥37; laranja ≥39; vermelha ≥41; roxa ≥43 °C.

**Risco cumulativo 3d** (umbral t = 39 °C): amarela ≥3; laranja ≥7; vermelha ≥12; roxa ≥18. Persistência EHF de emergência: ≥5 dias.

### 5.3 Limiares destacados no boletim (atenção sanitária)

| Sinal | Critério operacional |
|-------|----------------------|
| Calor extremo | Tmáx ≥ 37 °C |
| Calor seco | Tmáx ≥ 37 °C **e** UR ≤ 30% |
| Estresse térmico | UTCI ≥ 32 °C (atenção); faixas superiores no estágio |
| Qualidade do ar | PM2,5 ≥ 25 µg/m³ |

### 5.4 Qualidade do ar (estágio AQ)

Amarela ≥15; laranja ≥25; vermelha ≥50; roxa ≥75 µg/m³ (PM2,5).

### 5.5 Ocupação no estágio assistencial

Amarela ≥75%; laranja ≥85%; vermelha ≥95%; roxa ≥100% — **somente** com ocupação válida; `SEM_LEITOS_INDICASUS` não entra como zero inventado.

---

## 6. Classificação municipal de risco (estágio ARARAS)

### 6.1 Escala de cores

| Nível | Ordem | Interpretação operacional (boletim) |
|-------|-------|-------------------------------------|
| Cinza | −1 | Dados insuficientes (anti falso-verde) |
| Verde | 0 | Situação favorável; monitoramento de rotina |
| Amarela | 1 | Atenção; acompanhar evolução |
| Laranja | 2 | Alerta; preparação proporcional |
| Vermelha | 3 | Alerta elevado; revisar capacidade assistencial |
| Roxa | 4 | Situação excepcional; mobilização proporcional |

### 6.2 Regra decisória

O nível final do município é o **máximo** entre candidatos de domínio:

```text
nivel_final = max(
  nivel_clima, nivel_assistencia, nivel_leitos, nivel_infra,
  nivel_estoque, nivel_sentinela, nivel_mortalidade, nivel_inmet
  [, qualidade do ar, hidrologia, … conforme candidatos ativos]
)
```

**Anti falso-verde:** sem bloco climático **e** assistencial válidos → **cinza**.

Implementação: `sisclima/engines/stages.py` · limiares: `config/settings.yaml`.

---

## 7. Projeção operacional ~7 dias (risco térmico projetado)

**Objetivo:** estimar a classe municipal para aproximadamente sete dias — **nowcasting operacional**, distinto da previsão climática sazonal.

**Composição:** máximo entre quatro componentes térmicos (sem soma/média — anti-redundância).

| Componente | Variável | Pontuação |
|------------|----------|-----------|
| Intensidade | Tmáx máxima prevista na janela | ≥34→25; ≥37→50; ≥40→75; ≥42→100 |
| Estresse térmico | UTCI máximo previsto | ≥32→25; ≥36→50; ≥40→75; ≥44→100 |
| Persistência | Risco cumulativo máx. 7d | ≥3→25; ≥7→50; ≥12→75; ≥18→100 |
| Onda de calor | Dias com onda prevista | ≥1→40; ≥2→60; ≥3→80; ≥4→100 |

**Classes do score 0–100:** 0–24 verde; 25–49 amarela; 50–69 laranja; 70–84 vermelha; 85–100 roxa.

**Fora do cálculo da classe nesta versão:** fumaça, fogo, hidrologia e pressão assistencial (contextos concomitantes).

Motor: `sisclima/engines/predicao_skill_7d.py`.  
Validação retrospectiva: pares previsto × observado (`acerto_tol1` ±1 nível) + export semanal `hist_boletim_rodada_semanal`.

---

## 8. Índices compostos (não confundir)

### 8.1 Índice de prioridade global (painel)

Pesos default (renormalizados se pilar ausente):

| Pilar | Peso |
|-------|------|
| Vigilância | 0,30 |
| Pressão | 0,25 |
| Adaptação | 0,20 |
| Fragilidade (100 − resiliência) | 0,15 |
| Alerta | 0,10 |

Faixas: baixa ≤30; moderada ≤60; alta ≤80; crítica acima.

### 8.2 Índice de preparação clima–saúde (boletim)

Normalização por **percentil municipal 0–100**; pesos:

| Componente | Peso |
|------------|------|
| Prioridade operacional (`indice_prioridade_global`) | 30% |
| Exposição ambiental | 25% |
| Pressão assistencial | 25% |
| Vulnerabilidade | 20% |

Faixas: Acompanhamento &lt;35; Moderada 35–&lt;55; Alta 55–&lt;75; Crítica ≥75.  
A **classe climática ARARAS não entra** no índice.

### 8.3 Índice de pressão em saúde (semáforo G/A/V)

| Pilar | Fonte | Peso (exemplo) | Semáforo ilustrativo |
|-------|-------|----------------|----------------------|
| IndicaSUS | Ocupação de leitos | 0,30 | Verde &lt;80%; amarela 80–89%; vermelha ≥90% |
| SISREG | Fila / solicitações | 0,20 | Conforme YAML |
| SINAN | Agravos / z-score / calor | 0,30 | Limiares de casos/z-score |
| SIM | Óbitos CID sensíveis | 0,20 | 0 / 1–2 / ≥3 na janela |

Composto 0–100: verde ≤39; amarela ≤69; vermelha ≥70.  
**Distinto** do estágio de cinco cores.

Cada KPI pode carregar valor atual, predição ~7d e tendência (↑/→/↓).

---

## 9. Sinais hospitalares e regulação

| Conceito | Fonte | Interpretação |
|----------|-------|---------------|
| Ocupação hospitalar | IndicaSUS / BdSES (filtros SIEGES) | % de leitos ocupados — só municípios com leitos elegíveis |
| Pressão hospitalar | SISREG | Fila e solicitações — demanda territorial |

**Regras de qualidade:**

- Sem leitos elegíveis → `fonte_ocupacao = SEM_LEITOS_INDICASUS`; ocupação nula (**não** inventar média estadual).
- SISREG **nunca** é mapeado para `% ocupação`.
- Agregação por regional de saúde: % **ponderado por leitos**; municípios SEM_LEITOS contam na cobertura, mas não no denominador do %.
- UTI por regional: pendente de mapeamento confiável de `TipoLeito`.

Filtros SIEGES (resumo): SituacaoAtual ≠ Bloqueado; Tipo SUS Habilitado/Não Habilitado; TipoLeito ≠ Pronto Atendimento; exclusão UPA/PA/unidade mista (lista institucional).

---

## 10. Bloco epidemiológico

| Base | Indicadores-alvo |
|------|------------------|
| SINAN | Agravos sensíveis ao clima; arboviroses (incidência, tendência 7d) |
| SIVEP | SRAG: casos, UTI, óbitos, letalidade, incidência, z-score, vírus; indicadores MS SRAG-01…SRAG-12 |
| SIM | Óbitos com CID associados epidemiologicamente a extremos térmicos (T67, X30, E86/E87, capítulos I/J/N, etc.) — **associação ecológica**, não causalidade individual |
| IndicaSUS (DW internação) | Internações por grupos clima (respiratório/alérgico, desidratação/calor, DDA, cardio); janela 7d ou competência mensal |

Catálogo de agravos El Niño: `config/monitoramento_agravos_el_nino.yaml` (evidência OMS/IPCC/AdaptaSUS citada no YAML).

---

## 11. Sistema de alertas multinível

### 11.1 Escopos

| Escopo | Destinatário típico | Situação |
|--------|---------------------|----------|
| Estadual (SES/CIEVS) | Canal central (`ALERT_EMAIL_TO`, `TELEGRAM_CHAT_ID`) | Ativo |
| Regional | Contatos da regional (planilha homologada) | Fan-out com flag |
| Municipal | SMS / contatos municipais aprovados | Fan-out com flag |
| Cuiabá | Vigidesastre Cuiabá (IBGE 5103403) | Específico |

### 11.2 Canais

E-mail, Telegram; WhatsApp (múltiplos provedores) — frequentemente desligado até homologação.

### 11.3 Controles de segurança operacional

- Prévia no painel **antes** do envio;
- Fingerprint (hash) para evitar reenvio idêntico;
- Cooldown do digest;
- Exigência de ETL recente (`ALERT_REQUIRE_FRESH_ETL`, janela tipicamente até ~30 h com ETL diária);
- Níveis mínimos para push (configurável: laranja/vermelha/roxa);
- `SEND_ALERT_ON_LEVEL_CHANGE=false` em homologação;
- Fan-out só para contatos `APROVADO` / `ativo=1`.

Conteúdo típico do alerta: ícone de nível; indicadores clima + saúde + assistência; bloco de predição ~7d; orientações; fontes e carimbo de geração.  
Padrão municipal: `sisclima/alerts/municipal_padrao.py`.

---

## 12. Boletim semanal El Niño / Sala de Situação

### 12.1 Propósito

Instrumento operacional da Sala: fotografia da semana + projeção ~7d + priorização territorial + encaminhamentos. **Não substitui** boletins oficiais de meteorologia/clima.

### 12.2 Calendário

Semana epidemiológica **SINAN** (domingo a sábado; 1ª semana contém 4 de janeiro) — não usar ISO week.

### 12.3 Estrutura documental (seções)

1. Leitura executiva  
2. Cenário El Niño  
3. Cenário sazonal (Brasil → Amazônia Legal → MT)  
4. Situação atual MT (observado)  
5. Projeção operacional ~7d  
6. Mapas atual × projetado  
7. Alertas INMET / CEMADEN  
8. Recursos hídricos / seca  
9. Fogo e qualidade do ar  
10. Impactos potenciais à saúde  
11. Priorização territorial e acesso (inclui IndicaSUS × SISREG e ocupação por regional)  
12. Orientações por cenário  
13. Estoques / assistência farmacêutica  
14. Recomendações oficiais aos estados/municípios  
15. Encaminhamentos (24–48 h / até próxima Sala / próximas semanas)  
16. Notas metodológicas e glossário  
17. Conclusão e tendência  
18. Referências (NBR 6023)

### 12.4 Evolução com memória (roadmap científico)

- Export automático `Rodada_Semanal` / `hist_boletim_rodada_semanal`;
- Validação projeção × observado;
- Detecção de excesso de SRAG (baseline) — prioridade epidemiológica;
- Internações CID IndicaSUS estáveis na janela operacional.

---

## 13. Memória histórica e validação do modelo

| Artefato | Conteúdo |
|----------|----------|
| `hist_clima_municipal_diario` | Tmáx, Tmín, UTCI, UR, precipitação, risco 3d, PM2,5 por município/dia |
| `hist_saude_municipal_diario` | SRAG / arbovírus / dengue / chik / zika |
| `hist_boletim_rodada_semanal` | Por SE × município: classes atual/projetada + indicadores da rodada |
| Skill de predição | Pares previsto × observado; acerto com tolerância ±1 nível |
| Script | `scripts/exportar_rodada_semanal.py` → CSV em `data/output/boletim/` |

O snapshot operacional diário permanece *replace*; as tabelas `hist_*` acumulam série.

---

## 14. AdaptaSUS — matriz de riscos

| Risco prioritário MS | Cobertura ARARAS | Indicadores-chave |
|----------------------|------------------|-------------------|
| Extremos de temperatura | Forte | Tmáx, Tmín, UTCI, risco 3d, exposição vulnerável |
| Poluição atmosférica | Parcial | PM2,5, risco ar/queimadas |
| Vetoriais / zoonoses | Parcial | Arboviroses 7d, risco vetorial climático |
| Extremos de precipitação | Parcial | Precipitação, CEMADEN, ANA |
| WASH | Parcial (Censo) | Cobertura água, déficit esgoto, índice WASH |
| SAN | Ausente | — |

Eixos AdaptaSUS: (1) padrões de morbimortalidade; (2) demanda nos serviços; (3) interrupção de serviços; (4) emergência em saúde pública.

---

## 15. Análises estatísticas disponíveis

| Família | Status | Uso |
|---------|--------|-----|
| Incidência / letalidade / mortalidade | Parcial | Epidemiologia descritiva |
| Correlação clima–saúde (Spearman / lags) | Existe | Priorização ecológica |
| Odds ratio | Existe | Associação exposição × desfecho |
| Sazonalidade | Existe | Picos mensais / SE |
| Predição ~7d (nowcasting) | Existe | Semana seguinte |
| Forecasting sazonal | Externo (Painel El Niño) | Não confundir com pred 7d |
| Excesso (Farrington / P-score) | Roadmap | SRAG / mortalidade |

---

## 16. Limitações (Discussion — honesto)

1. Cobertura IndicaSUS parcial (nem todos os 142 municípios têm leitos elegíveis no recorte SIEGES).
2. Não se inventa ocupação estadual nem fallback que mascara ausência de dado.
3. SIVEP oficial pode estar ausente no DW; casos não são inventados.
4. Hidrologia baseada em subset de estações ANA — não extrapolar ao estado inteiro.
5. Solo: tipológico, não calibrado por município.
6. CAMS opcional; AQ frequentemente via Open-Meteo.
7. Fan-out municipal/regional depende de planilha homologada.
8. Predição 7d ≠ previsão sazonal; IQA ≠ laudo oficial; associação ≠ causalidade.
9. SAN/SISVAN ausentes; WASH estrutural (Censo), não SNIS operacional.
10. Internações CID dependem de conectividade DW/rede SES.
11. Estoques farmacêuticos: validar no sistema oficial SAF (carga pode estar defasada).
12. Documentos legados que citam “141 municípios” estão desatualizados frente ao universo 142.

---

## 17. Sugestão de estrutura do artigo

| Seção IMRaD | Conteúdo deste dossiê |
|-------------|----------------------|
| **Introduction** | El Niño / extremos em MT; CIEVS; lacuna de sistemas com memória e validação; AdaptaSUS |
| **Methods — Setting** | 142 municípios; Portaria 0590/2026; Sala de Situação |
| **Methods — System** | Arquitetura bronze–gold; fontes; ETL diário; painel Streamlit |
| **Methods — Indicators** | Limiares §§5–6; índices §8; hospitalares §9; epidemiológicos §10 |
| **Methods — Model** | Estágio max-candidatos; risco térmico projetado 7d |
| **Methods — Alerts & bulletin** | Multinível; SE SINAN; boletim |
| **Methods — Validation** | hist_*; proj × obs; skill ±1 nível |
| **Results** | Distribuição de classes; cobertura IndicaSUS; acurácia retrospectiva (quando série ≥4–6 SE); casos de uso Sala |
| **Discussion** | Limitações §16; calibração de limiares; excesso SRAG como próximo passo; generalização |
| **Conclusion** | De “fotografia da semana” a sistema com memória e aprendizado |

---

## 18. Referências operacionais internas (para Methods)

- `docs/ARQUITETURA.md`
- `docs/VISAO_OPERACIONAL_SIS_CLIMA_SAUDE.md`
- `docs/ALINHAMENTO_ADAPTASUS_MS.md`
- `docs/PLANO_EL_NINO_SALA_SITUACAO.md`
- `docs/PLANO_OCUPACAO_HIBRIDA.md`
- `docs/INDICADORES_MS_SIVEP.md`
- `config/settings.yaml`
- `config/indice_pressao_semaforo.yaml`
- `config/adaptasus_riscos.yaml`
- `config/painel_el_nino.yaml`
- `sisclima/engines/stages.py`
- `sisclima/engines/predicao_skill_7d.py`
- `sisclima/engines/indice_pressao_saude.py`
- `sisclima/engines/boletim_el_nino/`
- `sisclima/alerts/`
- `sisclima/reporting/quadro_risco_pressao.py`
- `sisclima/reporting/rodada_semanal.py`
- `sisclima/ingestion/historico_incremental.py`

### Referências externas típicas (NBR 6023 — completar no artigo)

- OMS / IPCC AR6 (saúde e extremos)
- AdaptaSUS — Plano Setorial de Saúde (MS)
- Guia de Mudanças Climáticas e Saúde (MS)
- Guia de Vigilância Integrada covid-19/influenza e vírus respiratórios (MS/SVSA, 2024)
- Painel El Niño 2026–2027 (INMET/INPE/ANA/CEMADEN/SGB/CENSIPAM et al.)
- Portaria nº 0590/2026/GBSES (SES-MT)

---

## 19. Checklist do que o artigo **pode afirmar** com base no sistema

- [x] Escopo estadual municipal completo (142)
- [x] Classificação multicritério com regra de máximo
- [x] Separação IndicaSUS × SISREG
- [x] Projeção térmica 7d com componentes e faixas documentadas
- [x] Alertas multinível com validação prévia
- [x] Boletim alinhado à Sala / Portaria 0590
- [x] Memória histórica e pipeline de validação proj × obs
- [x] Alinhamento AdaptaSUS com lacunas explícitas
- [ ] Acurácia retrospectiva numérica estadual (requer série acumulada de SE)
- [ ] Excesso de SRAG tipo Farrington (ainda roadmap)
- [ ] UTI por regional IndicaSUS (mapeamento TipoLeito pendente)
- [ ] Cobertura hidrológica plena do estado

---

*Documento gerado a partir do repositório operacional ARARAS MT. Atualizar limiares e coberturas conforme a versão em produção citada no artigo.*
