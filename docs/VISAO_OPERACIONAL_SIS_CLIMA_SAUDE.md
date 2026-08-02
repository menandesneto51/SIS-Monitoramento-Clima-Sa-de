# -*- coding: utf-8 -*-
"""Visão operacional do SIS Clima-Saúde MT (CIEVS/SES-MT).

Documento vivo: o que o sistema deve entregar a gestores e ao setor saúde.
"""

## 1. Propósito

Produzir **insights climáticos e de saúde** em escala estadual/municipal,
com **análises estatísticas** e **alertas multinível** acionáveis, e um
**painel único** para consulta e validação antes de qualquer disparo externo.

## 2. Bloco clima / ambiente (insights)

| Fonte | Papel no SIS |
|-------|----------------|
| Open-Meteo | Tmáx/Tmín, umidade, vento, precipitação, **solo** |
| Copernicus / CAMS | Qualidade do ar (PM2,5 e correlatos), quando credenciais OK |
| INMET | Alertas oficiais de tempo severo / calor |
| Cemaden | Alertas de desastres (wsAlertas2) |
| ANA | Risco hidrológico / telemetria |

Saída no painel: abas **Clima/TITAN**, **Qualidade do ar**, **Cemaden/ANA**, mapas cloropléticos.

## 3. Bloco saúde (indicadores)

| Base | Indicadores-alvo |
|------|------------------|
| SINAN | Agravos sensíveis ao clima (incl. arboviroses) — incidência, tendência |
| SIVEP / Sentinela | SRAG — incidência, letalidade, UTI, vírus |
| IndicaSUS / CNES | Ocupação hospitalar e pressão assistencial |
| SISREG | Fila / tempo de espera / solicitações (`ops_sisreg_municipio`) |
| SIM | Óbitos relacionados a calor / cardiorrespiratório (contagens e taxas quando população disponível) |

Saída: abas **Assistência** (índice de pressão), **Arboviroses**, **SIVEP**, **Sentinela**, **GeoCalor**, **Operacional**.

### 3.1 Índice de pressão — semáforo G/A/V

Motor: `sisclima/engines/indice_pressao_saude.py` · Config: `config/indice_pressao_semaforo.yaml` · Painel: aba **Assistência**.

| Pilar | Fonte | Semáforo (exemplo) |
|-------|-------|--------------------|
| IndicaSUS | ocupação de leitos | verde <80% · amarela 80–89% · vermelha ≥90% |
| SISREG | fila (h) / solicitações | quando a tabela existir; senão pilar omitido |
| SINAN | arbovírus 7d, z-score, SRAG, agravos calor | limiares de casos/z-score |
| SIM | óbitos CID sensíveis ao calor | 0 / 1–2 / ≥3 na janela |

Cada KPI traz: **valor atual**, **predição ~7d**, **tendência** (↑ alta / → estável / ↓ queda) e cor **verde / amarela / vermelha**.  
O índice composto (0–100) renormaliza pesos pelos pilares disponíveis.  
**Distinto** do nível operacional de 5 cores (verde→roxa).

Agravos monitorados têm evidência climática citada no YAML (OMS, IPCC AR6, AdaptaSUS/MS).

## 4. Análises estatísticas

| Família | Status no SIS | Uso |
|---------|---------------|-----|
| Incidência / letalidade / mortalidade | Parcial → expandir | Epidemiologia descritiva |
| Correlação clima–saúde | Existe (Spearman/lags) | Priorização ecológica |
| Odds Ratio | Existe | Associação exposição×desfecho |
| Sazonalidade | Existe | Picos mensais / SE |
| Predição ~7 dias (nowcasting operacional) | Existe | Semana seguinte |
| Forecasting sazonal (mensal/trimestral) | Externo (boletins) | Não confundir com pred 7d |
| Nowcasting epidemiológico avançado | Lacuna documentada | Roadmap |

## 5. Alertas em 4 níveis

Motor: `sisclima/engines/alertas_multinivel.py` · Painel: aba **Alertas** · Digest: `sisclima/alerts/digest.py`.

| Escopo | Destinatário | Situação |
|--------|--------------|----------|
| **estadual** | Canal central CIEVS (`ALERT_EMAIL_TO` + `TELEGRAM_CHAT_ID`) | **Ativo** — único escopo enviado ao CIEVS/notifica |
| **regional** | Contatos da regional na planilha | Gerado/gravado; envio com `ALERT_FANOUT_ENABLED` + CSV |
| **municipal** | Contatos do município na planilha | Idem |
| **cuiaba** | Vigidesastre Cuiabá na planilha | Idem (IBGE 5103403) |

Cada boletim inclui:
- ícone de nível (🟢🟡🟠🔴🟣);
- indicadores climáticos + saúde + assistência;
- bloco de **predição ~7d**;
- orientações operacionais (SES por setor; regional/municipal por público);
- fontes e carimbo de geração;
- prévia no painel **antes** do envio.

Modelo de contatos: `config/contatos_alertas.exemplo.csv` → `data/input/contatos_alertas.csv`.  
Flag segura: `SEND_ALERT_ON_LEVEL_CHANGE=false` até validação.  
Agendador diário: serviço Docker `alerts-scheduler` (`ALERT_INTERVAL_HOURS=24`), independente do notebook.

## 6. Painel de consulta e validação

Entrada: `streamlit_app.py` → `app_v9.py`.

- Navegação horizontal por abas (sem menu lateral confuso).
- Mapas por **shapefile** municipal.
- Ajudante de interpretação (justificativa em linguagem de plantão).
- Auditoria de tabelas na aba Alertas / Inteligência.
- Código **legível** (sem ofuscação) — política rede SES.

## 7. Lacunas conscientes (roadmap)

1. Nowcasting epidemiológico formal e forecasting sazonal integrado (hoje: boletins oficiais).
2. Preencher e homologar a planilha `contatos_alertas.csv` (regionais/municípios/Vigidesastre) para liberar `ALERT_FANOUT_ENABLED`.
3. Séries Galileo/SIM/GeoCalor completas na base Postgres em todas as rodadas.
4. Templates HTML ricos com ícones estáticos para e-mail institucional.
5. Integração SISREG → popular `ops_sisreg_municipio` (contrato em `sql/ops_sisreg_municipio_contrato.sql`).
6. WASH/SAN AdaptaSUS com fonte estadual (SNIS/SES) — demografia IBGE × exposição já cobre o KPI de vulnerabilidade populacional.

## 8. Princípio de operação

> O SIS **informa e prioriza**; a **decisão** de ativar COE, portarias ou comunicação pública permanece com a gestão (SES/SMS/regionais), apoiada pelo Plano de Contingência seca/estiagem.
