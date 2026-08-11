# Relatório de Prontidão Institucional — ARARAS MT

<table><tr><td><img src="../assets/branding/araras-mt-logo-horizontal.png" alt="ARARAS MT" width="360"></td><td><img src="../assets/branding/governo-ses-mt-fundo-institucional.png" alt="SES-MT e Governo de Mato Grosso" width="250"></td></tr><tr><td><strong>CIEVS-MT</strong> · <img src="../assets/branding/rede-cievs.png" alt="Rede CIEVS" width="125"></td><td><img src="../assets/branding/vigidesastres.png" alt="Vigidesastres" width="60"></td></tr></table>

**Órgão:** CIEVS / SES-MT
**Sistema:** ARARAS MT (migração de identidade sobre o painel V9)
**Data da avaliação pública:** 11/08/2026
**Objetivo:** Demonstrar robustez operacional dos indicadores e cálculos, apontar pontos fortes e pendências para institucionalização nos servidores da SES.

---

## 1. Sumário executivo

O ARARAS MT possui arquitetura e cobertura funcional para operar como ferramenta de apoio à vigilância integrada no âmbito municipal (142 municípios de MT), com:

- painel Streamlit estável (`/healthz` = 200);
- pipeline de ingestão + enriquecimento + classificação em cinco níveis (verde → roxa);
- índice de pressão por saúde **diferenciado** (não mais flat em 20);
- hidrologia ANA (seca/cheia) com filtro de cotas de barramento;
- rotina diária automatizável (`rotina_diaria_ops.py` / Agendador Windows / Docker);
- deploy documentado via Docker Compose (Postgres + app + pipeline + alertas).

**Veredito para institucionalização:**
**Apto para homologação técnica controlada, mas ainda não apto para produção institucional 24×7.** Na inspeção do painel público em 11/08/2026, a data de referência exibida era 07/08/2026, o backend informado era SQLite e apenas 1 de 12 fontes aparecia como atualizada/aceitável. A migração de identidade não elimina esse bloqueio de dados.

Checklist rápido (inspeção pública de 11/08/2026):

| Critério | Status |
|----------|--------|
| Painel responde | OK, com demora perceptível na inicialização |
| Cobertura territorial exibida | 142 municípios |
| Data de referência | 07/08/2026 — defasada em quatro dias na avaliação |
| Fontes em condição aceitável | 1/12 (8%) |
| Backend exibido | SQLite — contingência, não base oficial de produção |
| Envio de alertas | OFF — estado seguro para homologação |
| VPN/DW 24×7 validada | Não demonstrada no ambiente público |

---

## 2. Escopo validado (indicadores e cálculos)

### 2.1 Arquitetura decisória

O nível municipal segue a regra de **máximo entre componentes** (clima, assistência, leitos, infra, estoque, sentinela, mortalidade, INMET/Cemaden/hidro), implementada em `sisclima/engines/stages.py` e reforçada no alerta integrado (`alerta_integrado_sis_titan`).

```text
nivel_final = max(componentes ativos no município)
```

Cores: **verde < amarela < laranja < vermelha < roxa**.

### 2.2 Inventário de motores (Gold)

| Domínio | Motor | Saídas principais | Validação observada |
|---------|-------|-------------------|---------------------|
| Pressão saúde | `indice_pressao_saude.py` + YAML semáforo | `indice_pressao_saude`, `semaforo_pressao` | Score contínuo 0–100; anti-flat; pilares IndicaSUS/SISREG/SINAN/SIM |
| Estágio operacional | `stages.py` | `nivel`, `score`, `motivos` | Distribuição tipicamente heterogênea (ex.: 95 laranja / 28 vermelha / 4 roxa) |
| Biometeo / TITAN | `biometeo.py` | `met_biometeo` (UTCI proxy, HI, risco 3d) | Alimenta classificação e predição |
| Hidrologia ANA | `hidro_risco.py` + `ana_hidroweb.py` | `hidro_risco_municipal` (`situacao_hidro`) | REST+SOAP; barramento excluído; 13 mun. com seca/cheia no último refresh |
| Alerta integrado | `alerta_integrado.py` | `alerta_integrado_sis_titan` | Une ARARAS + INMET + Cemaden + solo + hidro |
| Predição 7d | `predicao_skill_7d.py` | `predicao_calor_7d_*` | Regra principal + ML auxiliar |
| IndicaSUS / hospital | `hospital.py` + script ocupação | `ocupacao_leitos_pct`, fonte LIVE/CACHE | 142 mun. no snapshot local |
| SISREG | `sisreg.py` | `ops_sisreg_municipio` | Live na VPN; CSV V16 offline |
| CNES | `cnes_ops.py` | `ops_cnes_*` | DW ou fallback |
| Arbovírus / SINAN / SIM | `epidemiology.py` | `epi_*` | DW + bootstrap CSV |
| SIVEP/SRAG | `sivep_ms_indicators.py` | `epi_sivep_*` | Local/DW conforme flags |
| Sentinela SG MS | `sentinela_sg_ms.py` | SG-01…SG-13 | Depende de CSV MS em `data/input/` |
| Solo / ar / queimadas / WASH | enrichment | tabelas `solo_*`, `qualidade_ar_*`, `queimadas_*`, `wash_*` | Fontes públicas + IBGE |
| Alertas multinível | `alertas_multinivel.py` + scheduler | payloads SES/regional/municipal | Envio gated por `.env` |

### 2.3 Limiares (auditáveis)

| Onde | O quê |
|------|--------|
| `config/settings.yaml` | Calor, assistência, ar, pesos do painel |
| `config/indice_pressao_semaforo.yaml` | Verde ≤39 / amarela ≤69 / vermelha |
| `config/ana_cotas_referencia_mt.csv` | Cotas absolutas (metadados; limiares oficiais ainda a preencher) |
| `.env` | `ANA_CHUVA_*_MM`, `ALERT_MIN_LEVEL`, flags de fontes |
| Código `hospital.py` | Faixas de ocupação 75/85/95/100% |

### 2.4 Scripts de demonstração / QA

```powershell
.\.venv\Scripts\python.exe scripts\smoke_ops.py
.\.venv\Scripts\python.exe validar_dw_conexao.py
.\.venv\Scripts\python.exe validar_sentinela_ana.py
.\.venv\Scripts\python.exe validar_cemaden_chuva.py
.\.venv\Scripts\python.exe validar_arboviroses.py
.\.venv\Scripts\python.exe validar_sivep_ms.py
.\.venv\Scripts\python.exe validar_pesos_indicadores.py
.\.venv\Scripts\python.exe regenerar_sistema_completo.py
.\.venv\Scripts\python.exe rotina_diaria_ops.py
```

Critérios do smoke: HTTP 200, ≥100 mun. no seed, pressão não flat (~20), hidro sem cota ≥5000 cm.

---

## 3. Pontos fortes (prontos para institucionalizar)

1. **Cobertura estadual municipalizada** — 141/142 municípios com chave IBGE e classificação operacional.
2. **Rastreabilidade** — motivos textuais por município; fontes marcadas (LIVE / CACHE / CSV / ANA_REST / ANA_SOAP).
3. **Robustez offline** — sem VPN o sistema degrada para CSV/cache sem derrubar o painel; com VPN recompõe DW/IndicaSUS/SISREG.
4. **Hidrologia com governança técnica** — SOAP público + REST HidroWeb autenticado; exclusão de cotas de barramento; User-Agent institucional (`ARARAS-Clima-Saude-MT/...`).
5. **Índice de pressão corrigido** — scoring contínuo evita o artefato “todos em 20”.
6. **Empacotamento servidor** — Docker Compose (`db`, `app`, `pipeline`, `alerts-scheduler`); rotina diária e tarefas Windows.
7. **Segurança básica de repositório** — `.env` fora do Git; alertas com `SEND_ALERT_ON_LEVEL_CHANGE=false` por padrão; credenciais ANA só locais.
8. **Alinhamento institucional** — herança TITAN / SENTINELA / AESOP / SIVEP / IndicaSUS / CNES documentada em `docs/ARQUITETURA.md`.
9. **Contraste e usabilidade do painel** — ajustes recentes de legibilidade (fundos azuis).
10. **Caminho Cloud** — seed SQLite + pins ASGI (`starlette==1.3.1`) para evitar 500 no Streamlit Cloud.

---

## 4. Evidências observadas no painel público (11/08/2026)

| Indicador | Evidência |
|-----------|-----------|
| Painel | Carregou e permitiu navegação entre módulos |
| Resumo municipal | 142 municípios exibidos |
| Situação estadual | Roxa; 32 municípios em vermelha/roxa |
| Data de referência | 07/08/2026 |
| Qualidade das fontes | 1/12 em condição aceitável (8%) |
| Backend | SQLite |
| Alertas | Envio OFF |

*Nota:* a situação de risco exibida deve ser lida junto com a qualidade e a atualidade das fontes. **Produção SES deve usar Postgres** (`DATABASE_URL`) e bloquear ou identificar claramente indicadores cuja fonte esteja vencida.

---

## 5. O que precisa ser corrigido / concluído antes do “go-live” pleno

### 5.1 Crítico (bloqueia operação 24×7 plena)

| # | Pendência | Ação recomendada | Responsável sugerido |
|---|-----------|------------------|----------------------|
| C1 | Acesso contínuo à rede SES (DW `10.15.1.50`, IndicaSUS `10.15.0.222`, SISREG `10.15.1.71`) | Firewall/VPN + conta serviço somente leitura | STI + CIEVS |
| C2 | Postgres oficial no servidor (não depender só do seed SQLite) | `docker compose up -d db` + `DATABASE_URL` | STI |
| C3 | Credenciais de serviço (não pessoais) no `.env` do servidor | Trocar usuários pessoais por conta institucional | STI + gestores de sistemas |
| C4 | Agendamento confiável da rotina | `alerts-scheduler` + `rotina_diaria_ops` / tarefas Windows | STI + CIEVS |
| C5 | Atualidade e cobertura insuficientes no painel público (1/12 fontes) | Reprocessar fontes, registrar timestamps e impedir publicação de síntese sem dados mínimos | STI + CIEVS + responsáveis pelas fontes |

### 5.2 Importante (qualidade dos alertas)

| # | Pendência | Ação |
|---|-----------|------|
| I1 | Cotas absolutas ANA ainda sem limiares oficiais no CSV | Preencher `cota_seca_cm` / `cota_alerta_cm` / `cota_emergencia_cm` com réguas ANA/Defesa Civil |
| I2 | YAML do pilar SISREG ainda marca `pendente_integracao` | Atualizar status no YAML após homologação com a Central |
| I3 | INMET sem URL padrão | Definir `INMET_ALERTS_URL` ou processo CSV oficial |
| I4 | Sentinela SG depende de CSV MS | Formalizar carga periódica em `data/input/` |
| I5 | Predição 7d com skill ML ainda auxiliar | Homologar métricas antes de uso decisório exclusivo |
| I6 | Alinhar `requirements-docker.txt` (Streamlit 1.57) ao pin Cloud (1.60 + starlette 1.3.1) | Evitar regressão GZip no servidor |

### 5.3 Desejável (maturidade)

| # | Pendência |
|---|-----------|
| D1 | Ambiente `.env.producao.example` versionado (sem segredos) |
| D2 | Monitoramento (healthcheck HTTP + alerta se pipeline falhar) |
| D3 | Backup Postgres + retenção de `logs/` e `alertas_enviados` |
| D4 | Treinamento SOP da sala de situação (já há checklists no painel) |
| D5 | Homologação formal dos pesos do painel (`validar_pesos_indicadores.py`) com gestão |

---

## 6. Matriz de prontidão por domínio

| Domínio | Pronto piloto | Pronto produção 24×7 | Observação |
|---------|---------------|----------------------|------------|
| Painel Streamlit | Sim | Sim (com Postgres) | |
| Clima Open-Meteo / Cemaden | Sim | Sim | HTTPS público |
| ANA hidro | Sim | Sim* | *cotas absolutas pendentes |
| Índice pressão | Sim | Sim* | *requer IndicaSUS/SISREG live ideais |
| DW SINAN/SIM/GAL/CNES | Parcial | Condicional | VPN |
| Alertas e-mail/Telegram | Código pronto | Não até governança | Flag false por padrão |
| Predição 7d | Sim (apoio) | Apoio, não único critério | |
| Sentinela SG MS | Parcial | Condicional | CSV MS |

---

## 7. Recomendação à direção CIEVS / SES

1. **Aprovar piloto institucional** no servidor SES (leitura + painel interno), com STI seguindo o documento `docs/STI_IMPLANTACAO_SERVIDOR_SES.md`.
2. **Manter envio automático de alertas desligado** até checklist SOP + lista oficial de destinatários.
3. **Agendar sprint de 2–4 semanas** para: conta serviço SQL, cotas ANA, alinhamento Docker pins, backup Postgres.
4. **Revalidar mensalmente** com `scripts/smoke_ops.py` + `validar_dw_conexao.py` + amostragem de 5 municípios críticos.

---

## 8. Referências internas

- `docs/ARQUITETURA.md`
- `docs/OPERACAO.md`
- `docs/DOCKER_BASE_UNICA.md`
- `docs/SENTINELA_SG_E_ANA.md`
- `docs/STI_IMPLANTACAO_SERVIDOR_SES.md` *(pacote técnico STI)*
- `docs/IDENTIDADE_VISUAL_ARARAS_MT.md`
- `config/indice_pressao_semaforo.yaml`, `config/settings.yaml`
- `scripts/smoke_ops.py`, `rotina_diaria_ops.py`, `regenerar_sistema_completo.py`

---

*Documento gerado para subsidiar institucionalização. Não substitui parecer formal da STI nem auditoria de segurança da informação da SES.*
