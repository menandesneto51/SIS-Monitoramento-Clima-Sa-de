# -*- coding: utf-8 -*-
"""Ajudante de interpretação do painel (padrão Meningites: guia + justificativa + IA opcional)."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd
import streamlit as st


def _fmt(x, nd: int = 1) -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return "—"
        if pd.isna(x):
            return "—"
        if isinstance(x, (int, np.integer)) or (isinstance(x, float) and float(x).is_integer() and nd == 0):
            return f"{int(float(x)):,}".replace(",", ".")
        return f"{float(x):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(x)


def guide_card(titulo: str, bullets: list[str]) -> str:
    body = "<br/>".join(f"• {b}" for b in bullets)
    return f'<div class="guide-card"><b>{titulo}</b><br/><br/>{body}</div>'


def _fecho(txt: str) -> str:
    return (
        txt
        + "\n\n> Texto de apoio à vigilância. **Validar com a equipe CIEVS** antes de comunicação oficial. "
        "Associação/correlação ≠ causalidade. TITAN = camada climática/alertas oficiais incorporada ao SIS. "
        "Padrão de leitura alinhado ao painel de Meningites (guia + achados + o que não concluir)."
    )


def _bloco(titulo: str, linhas: list[str]) -> str:
    body = "\n".join(linhas) if linhas else "- —"
    return f"### {titulo}\n\n{body}\n"


GUIDE_EXECUTIVO = guide_card(
    "Como ler a Visão executiva",
    [
        "<b>Nível operacional</b>: semáforo estadual (Verde→Roxa) pelo município mais crítico.",
        "<b>Prioridade global</b>: nota 0–100 que soma vigilância + pressão saúde + AdaptaSUS + fragilidade + alerta.",
        "<b>Alerta integrado SIS+TITAN</b>: une estágio SIS com INMET, Cemaden, solo e hidro.",
        "<b>Não é boletim oficial</b>: use como priorização de plantão e valide no território.",
    ],
)

GUIDE_CLIMA_TITAN = guide_card(
    "Como ler Clima / TITAN",
    [
        "<b>Calor</b>: Tmax, UTCI proxy e risco cumulativo 3 dias — calor que ‘acumula’.",
        "<b>Solo</b>: índice 0–100 de saturação (Open-Meteo). Alta/crítica ≠ saturação de leitos.",
        "<b>Alertas oficiais</b>: INMET + Cemaden + ANA — APIs públicas, sem scrapers ofuscados.",
        "<b>Integração</b>: o SIS incorpora o TITAN; o nível integrado aparece também na aba Alertas.",
    ],
)

GUIDE_ALERTAS = guide_card(
    "Como ler Alertas integrados",
    [
        "<b>Alerta integrado</b>: max(SIS, INMET, Cemaden, solo, hidro, calor TITAN).",
        "<b>Componente dominante</b>: qual camada puxou o nível (ex.: titan_inmet, sis_estagio).",
        "<b>SOP</b>: envio externo fica desligado por padrão até validar a prévia.",
        "<b>Fila municipal</b>: priorize laranja+ e municípios com vários componentes ativos.",
    ],
)

GUIDE_SAZONAL_OR = guide_card(
    "Como ler Sazonalidade / OR",
    [
        "<b>Índice sazonal</b>: mês acima de 1 = historicamente mais crítico.",
        "<b>OR ecológico</b>: chance relativa entre municípios mais vs menos expostos — não é causalidade individual.",
        "<b>Lags</b>: correlação clima→desfecho em 0–14 dias (exploratório).",
        "<b>Método</b>: alinhado ao painel de Meningites (sazonalidade + OR), adaptado a clima–saúde.",
    ],
)

GUIDE_OPERACIONAL = guide_card(
    "Como ler Operacional / CNES",
    [
        "<b>Capacidade CNES</b>: leitos/estabelecimentos por população (DW ou fallback ocupação).",
        "<b>Resiliência</b>: capacidade de resposta (livres + estoque + infra + busca + comunicação).",
        "<b>Com CNES</b>: capacidade de leitos = 60% livres + 40% capacidade instalada.",
        "<b>Lacunas</b>: equipamentos/profissionais podem estar vazios se o DW não trouxer o campo.",
    ],
)

GUIDE_ADAPTASUS = guide_card(
    "Como ler AdaptaSUS / Guia MS",
    [
        "<b>Seis riscos</b>: calor, ar/queimadas, vetorial, precipitação, pressão na rede, WASH (lacuna).",
        "<b>Índice de adaptação</b>: 0–100 — pressão relativa dos riscos AdaptaSUS cobertos.",
        "<b>Orientação</b>: texto operacional por risco dominante.",
        "<b>WASH/SAN</b>: ausência de fonte ≠ risco zero — lacuna explícita.",
    ],
)

GUIDE_ASSISTENCIA = guide_card(
    "Como ler Assistência / pressão",
    [
        "<b>Semáforo G/A/V</b>: pressão IndicaSUS + SISREG + SINAN + SIM (≠ nível Verde→Roxa).",
        "<b>Tendência 7d</b>: ↑ piora · → estável · ↓ melhora na previsão de pressão.",
        "<b>Pilares</b>: ocupação, fila/regulação, arbovírus/SRAG, óbitos sensíveis ao calor.",
        "<b>GAL/SIM/série</b>: positividade e óbitos apoiam leitura, não substituem boletim oficial.",
    ],
)

GUIDE_MAPAS = guide_card(
    "Como ler Mapas",
    [
        "<b>Camadas</b>: nível, prioridade, pressão, UTCI, vigilância — escolha uma pergunta por vez.",
        "<b>Hover</b>: confira motivo e tendência antes de escalar.",
        "<b>Filtros</b>: Regional/Município no topo restringem o mapa.",
        "<b>Sem polígono</b>: pontos lat/lon ainda são válidos para priorização.",
    ],
)

GUIDE_AR = guide_card(
    "Como ler Qualidade do ar",
    [
        "<b>PM2.5</b>: proxy Copernicus/CAMS — cruze com SRAG e sintomas respiratórios.",
        "<b>Queimadas</b>: picos de PM2.5 + AdaptaSUS ar elevam prioridade de plantão.",
        "<b>Lacuna</b>: ausência de estação local ≠ ar limpo.",
    ],
)

GUIDE_INTEL = guide_card(
    "Como ler Inteligência",
    [
        "<b>Predição ~7d</b>: tendência de calor/risco — não é forecast de setembro.",
        "<b>Alerta inteligente</b>: combina estágio atual com piora prevista.",
        "<b>Modelagem V9</b>: status/lags/priorização — use como apoio, valide no território.",
    ],
)

GUIDE_CORR = guide_card(
    "Como ler Correlação clima–saúde",
    [
        "<b>|ρ| Spearman</b>: força da associação ecológica municipal.",
        "<b>Scatter</b>: gere hipóteses; não prove causalidade individual.",
        "<b>n≥12</b>: pares com poucos municípios são instáveis.",
    ],
)

GUIDE_ARBO = guide_card(
    "Como ler Arboviroses",
    [
        "<b>Casos 7d</b>: pressão recente — cruze com calor/chuva.",
        "<b>Incidência / z-score</b>: compara municípios no mesmo recorte.",
        "<b>Não projeta temporada</b>: janela curta ≠ tendência anual.",
    ],
)

GUIDE_SIVEP = guide_card(
    "Como ler SIVEP/SRAG",
    [
        "<b>Casos e óbitos</b>: SRAG hospitalar alinhada ao MS/SVSA.",
        "<b>Vírus / lab</b>: cobertura laboratorial e circulação viral.",
        "<b>Cruze</b>: qualidade do ar e calor podem coincidir com picos.",
    ],
)

GUIDE_SENTINELA = guide_card(
    "Como ler Sentinela SG",
    [
        "<b>SG-01…SG-13</b>: indicadores de unidades sentinela (metas MS).",
        "<b>Ausência de dado</b>: ≠ ausência de gripe — checar alimentação das unidades.",
        "<b>Circulação viral</b>: use junto com SIVEP para o quadro respiratório.",
    ],
)

GUIDE_GEOCALOR = guide_card(
    "Como ler GeoCalor",
    [
        "<b>RR por lag 0–7</b>: associação ondas de calor × desfechos cardiorrespiratórios.",
        "<b>Exploratório</b>: não é laudo causal individual.",
        "<b>Status</b>: se a série diária faltar, o bloco mostra lacuna explícita.",
    ],
)

GUIDE_HIDRO = guide_card(
    "Como ler Cemaden / ANA",
    [
        "<b>Cemaden</b>: alertas oficiais de risco (inundação, deslizamento, seca).",
        "<b>ANA</b>: telemetria / risco hidrológico municipal.",
        "<b>Cruze</b>: chuva Open-Meteo + nível operacional do município.",
    ],
)

GUIDE_VIGIBARRAGENS = guide_card(
    "Como ler VigiBarragens",
    [
        "<b>ZAS</b>: Zona de Autossalvamento — população a jusante exposta ao rompimento.",
        "<b>CRI / DPA</b>: Categoria de Risco e Dano Potencial Associado (SIGBM/ANM).",
        "<b>NE1/NE2/NE3</b>: nível de emergência → laranja/vermelha/roxa no SIS.",
        "<b>Cruze</b>: com chuva (Cemaden/ANA) e capacidade assistencial do município.",
    ],
)

GUIDE_GEO = guide_card(
    "Como ler Geografia",
    [
        "<b>Cadastro</b>: IBGE, regional, população, lat/lon.",
        "<b>Shapefile</b>: status da malha — inconsistência quebra mapas.",
        "<b>Vulnerabilidade</b>: índice territorial ao calor no mapa.",
    ],
)

GUIDE_CALC = guide_card(
    "Como ler Cálculos",
    [
        "<b>Transparência</b>: limiares, pesos e o que entra no nível/prioridade.",
        "<b>settings.yaml</b>: mudanças alteram índices na próxima rodada.",
        "<b>Use</b>: antes de questionar ‘por que ficou vermelho?’.",
    ],
)


def narrativa_executivo(resumo: pd.DataFrame, alerta_int: pd.DataFrame | None = None) -> str:
    if resumo is None or resumo.empty:
        return _fecho("Sem resumo municipal nesta rodada.")
    n = len(resumo)
    niveis = resumo["nivel"].value_counts().to_dict() if "nivel" in resumo.columns else {}
    crit = int((pd.to_numeric(resumo.get("score"), errors="coerce").fillna(0) >= 2).sum()) if "score" in resumo.columns else 0

    olhar = [
        "- Cruze **nível Verde→Roxa**, **prioridade global** e **alerta integrado** antes de escalar plantão.",
        "- Cards do topo: tensão climática, carga saúde e vigilância — contexto estadual da rodada.",
    ]
    achados = [
        f"- Municípios no recorte: **{_fmt(n, 0)}**.",
        f"- Laranja ou mais (score≥2): **{_fmt(crit, 0)}**.",
        f"- Distribuição de nível SIS: {', '.join(f'{k}={v}' for k, v in list(niveis.items())[:6]) or '—'}.",
    ]
    if "indice_prioridade_global" in resumo.columns:
        p = pd.to_numeric(resumo["indice_prioridade_global"], errors="coerce")
        alta = 0
        if "faixa_prioridade_global" in resumo.columns:
            alta = int(resumo["faixa_prioridade_global"].isin(["alta", "muito alta"]).sum())
        achados.append(
            f"- Prioridade global: média **{_fmt(p.mean(), 0)}** · máx **{_fmt(p.max(), 0)}** · "
            f"alta/muito alta: **{alta}** municípios."
        )
        top_p = resumo.sort_values("indice_prioridade_global", ascending=False).head(3)
        if not top_p.empty and "municipio" in top_p.columns:
            nomes = ", ".join(
                f"{r.get('municipio')} ({_fmt(r.get('indice_prioridade_global'), 0)})"
                for _, r in top_p.iterrows()
            )
            achados.append(f"- Top prioridade global: {nomes}.")
    if "indice_saturacao_solo" in resumo.columns:
        sm = pd.to_numeric(resumo["indice_saturacao_solo"], errors="coerce")
        achados.append(f"- Saturação do solo média: **{_fmt(sm.mean(), 0)}** (máx {_fmt(sm.max(), 0)}).")
    if alerta_int is not None and not alerta_int.empty and "nivel_alerta_integrado" in alerta_int.columns:
        ai = alerta_int["nivel_alerta_integrado"].value_counts().to_dict()
        top = alerta_int.sort_values("score_alerta_integrado", ascending=False).head(3)
        achados.append(f"- Alerta integrado SIS+TITAN: {', '.join(f'{k}={v}' for k, v in ai.items())}.")
        if not top.empty:
            nomes = ", ".join(f"{r.get('municipio')} ({r.get('nivel_alerta_integrado')})" for _, r in top.iterrows())
            achados.append(f"- Prioridade imediata (alerta): {nomes}.")

    nao = [
        "- Prioridade global **não substitui** o nível operacional nem SOP de envio de alertas.",
        "- Correlação clima–saúde / OR ≠ causalidade individual.",
        "- Predição ~7 dias não é cenário sazonal de setembro.",
    ]
    prox = [
        "- Abrir mapa/Alertas nos municípios do top prioridade e validar IndicaSUS/SISREG no território.",
        "- Se completude da prioridade estiver baixa, completar pilares (pressão, resiliência, alerta) antes de comunicar.",
    ]
    txt = (
        "**Justificativa (Visão executiva)**\n\n"
        + _bloco("O que olhar", olhar)
        + _bloco("Achados desta rodada", achados)
        + _bloco("O que não concluir", nao)
        + _bloco("Próximo passo", prox)
    )
    return _fecho(txt)


def narrativa_clima_titan(resumo: pd.DataFrame, solo: pd.DataFrame | None = None) -> str:
    olhar = [
        "- Priorize UTCI, risco cumulativo 3d e saturação do solo juntos — um isolado engana.",
        "- Alertas INMET/Cemaden/ANA são oficiais; o SIS só os incorpora.",
    ]
    lines = []
    if resumo is not None and not resumo.empty:
        if "utci_proxy" in resumo.columns:
            u = pd.to_numeric(resumo["utci_proxy"], errors="coerce")
            lines.append(f"- UTCI proxy máx: **{_fmt(u.max())}**; média **{_fmt(u.mean())}**.")
        if "risco_cumulativo_3d" in resumo.columns:
            r = pd.to_numeric(resumo["risco_cumulativo_3d"], errors="coerce")
            lines.append(f"- Risco cumulativo 3d máx: **{_fmt(r.max())}**.")
        if "indice_saturacao_solo" in resumo.columns:
            s = pd.to_numeric(resumo["indice_saturacao_solo"], errors="coerce")
            alta = int((s >= 70).sum())
            lines.append(f"- Solo: média **{_fmt(s.mean(), 0)}**; municípios alta/crítica (≥70): **{alta}**.")
    if solo is not None and not solo.empty and "classe_saturacao_solo" in solo.columns:
        vc = solo["classe_saturacao_solo"].value_counts().to_dict()
        lines.append(f"- Classes de solo: {', '.join(f'{k}={v}' for k, v in vc.items())}.")
    if not lines:
        lines.append("- Sem série climática/solo nesta rodada — rode o enrichment com USE_OPENMETEO=true.")
    nao = [
        "- Solo saturado ≠ leitos saturados.",
        "- Proxy UTCI não substitui medição biométrica oficial.",
    ]
    prox = ["- Cruzar municípios com UTCI/risco altos na aba Alertas e na prioridade global."]
    txt = (
        "**Justificativa (Clima/TITAN)**\n\n"
        + _bloco("O que olhar", olhar)
        + _bloco("Achados desta rodada", lines)
        + _bloco("O que não concluir", nao)
        + _bloco("Próximo passo", prox)
    )
    return _fecho(txt)


def narrativa_alertas(alerta_int: pd.DataFrame, resumo: pd.DataFrame | None = None) -> str:
    if alerta_int is None or alerta_int.empty:
        return _fecho("Sem tabela de alerta integrado. Rode completar_sistema_operacional.py.")
    vc = alerta_int["nivel_alerta_integrado"].value_counts().to_dict() if "nivel_alerta_integrado" in alerta_int.columns else {}
    dom = alerta_int["componente_dominante"].value_counts().head(5).to_dict() if "componente_dominante" in alerta_int.columns else {}
    n_laranja = int((pd.to_numeric(alerta_int.get("score_alerta_integrado"), errors="coerce").fillna(0) >= 2).sum())
    olhar = [
        "- Veja nível integrado + componente dominante + motivo antes de acionar SOP.",
        "- Fila municipal: laranja+ primeiro; cruze com prioridade global quando disponível.",
    ]
    lines = [
        f"- Municípios com alerta integrado: **{_fmt(len(alerta_int), 0)}**.",
        f"- Laranja ou mais: **{_fmt(n_laranja, 0)}**.",
        f"- Níveis: {', '.join(f'{k}={v}' for k, v in vc.items()) or '—'}.",
        f"- Componentes dominantes: {', '.join(f'{k}={v}' for k, v in dom.items()) or '—'}.",
    ]
    if resumo is not None and not resumo.empty and "indice_prioridade_global" in resumo.columns:
        top = resumo.sort_values("indice_prioridade_global", ascending=False).head(5)
        lines.append(
            "- Top prioridade global no recorte: "
            + ", ".join(f"{r.get('municipio')} ({_fmt(r.get('indice_prioridade_global'), 0)})" for _, r in top.iterrows())
            + "."
        )
    top = (
        alerta_int.sort_values("score_alerta_integrado", ascending=False).head(5)
        if "score_alerta_integrado" in alerta_int.columns
        else alerta_int.head(5)
    )
    for _, r in top.iterrows():
        lines.append(
            f"- **{r.get('municipio')}**: {r.get('nivel_alerta_integrado')} "
            f"(domina `{r.get('componente_dominante')}`) — {r.get('motivo_integrado')}"
        )
    nao = [
        "- Envio Telegram/e-mail fica OFF até validar prévia (`SEND_ALERT_ON_LEVEL_CHANGE`).",
        "- Alerta integrado ≠ confirmação de surto epidemiológico.",
    ]
    prox = ["- Revisar SOP e checklist da aba Alertas para os 5 primeiros da fila."]
    txt = (
        "**Justificativa (Alertas SIS+TITAN)**\n\n"
        + _bloco("O que olhar", olhar)
        + _bloco("Achados desta rodada", lines)
        + _bloco("O que não concluir", nao)
        + _bloco("Próximo passo", prox)
    )
    return _fecho(txt)


def _narr(
    titulo: str,
    olhar: list[str],
    achados: list[str],
    nao: list[str] | None = None,
    prox: list[str] | None = None,
) -> str:
    txt = (
        f"**Justificativa ({titulo})**\n\n"
        + _bloco("O que olhar", olhar)
        + _bloco("Achados desta rodada", achados or ["- Sem dados nesta rodada."])
        + _bloco("O que não concluir", nao or ["- Associação/correlação ≠ causalidade individual."])
        + _bloco("Próximo passo", prox or ["- Validar com a equipe CIEVS no território."])
    )
    return _fecho(txt)


def narrativa_assistencia(resumo: pd.DataFrame, pressao_state: dict | None = None) -> str:
    ps = pressao_state or {}
    olhar = [
        "- Semáforo G/A/V e tendência 7d antes de olhar ocupação isolada.",
        "- Cruzar vermelhos de pressão com prioridade global e alerta integrado.",
    ]
    achados = []
    if resumo is not None and not resumo.empty and "indice_pressao_saude" in resumo.columns:
        p = pd.to_numeric(resumo["indice_pressao_saude"], errors="coerce")
        achados.append(f"- Índice de pressão médio: **{_fmt(p.mean())}** (máx {_fmt(p.max())}).")
    if ps:
        achados.append(
            f"- Semáforo estadual: verde **{ps.get('n_verde', 0)}** · amarela **{ps.get('n_amarela', 0)}** · "
            f"vermelha **{ps.get('n_vermelha', 0)}**."
        )
        achados.append(
            f"- Tendência pressão 7d: ↑{ps.get('n_subindo', 0)} · →{ps.get('n_estavel', 0)} · ↓{ps.get('n_descendo', 0)}."
        )
        achados.append(f"- Cobertura SISREG no recorte: **{ps.get('sisreg_cobertura', 0)}** municípios.")
    if "semaforo_pressao" in (resumo.columns if resumo is not None else []):
        top = resumo.sort_values("indice_pressao_saude", ascending=False).head(3)
        if not top.empty and "municipio" in top.columns:
            achados.append(
                "- Top pressão: "
                + ", ".join(f"{r.get('municipio')} ({_fmt(r.get('indice_pressao_saude'))})" for _, r in top.iterrows())
                + "."
            )
    return _narr(
        "Assistência",
        olhar,
        achados,
        [
            "- Semáforo G/A/V ≠ nível operacional Verde→Roxa.",
            "- Proxy IndicaSUS/SISREG não substitui censo/fila oficial do dia.",
        ],
        ["- Abrir IndicaSUS/SISREG nos vermelhos e cruzar com Alertas."],
    )


def narrativa_mapas(resumo: pd.DataFrame) -> str:
    olhar = ["- Escolha uma camada (nível, prioridade, pressão) e pergunte ‘onde agir primeiro?’."]
    achados = [f"- Municípios no mapa/recorte: **{_fmt(len(resumo) if resumo is not None else 0, 0)}**."]
    if resumo is not None and not resumo.empty and "nivel" in resumo.columns:
        vc = resumo["nivel"].value_counts().to_dict()
        achados.append(f"- Níveis: {', '.join(f'{k}={v}' for k, v in vc.items())}.")
    if resumo is not None and not resumo.empty and "indice_prioridade_global" in resumo.columns:
        top = resumo.sort_values("indice_prioridade_global", ascending=False).head(3)
        achados.append(
            "- Top prioridade no mapa: "
            + ", ".join(f"{r.get('municipio')} ({_fmt(r.get('indice_prioridade_global'), 0)})" for _, r in top.iterrows())
            + "."
        )
    return _narr("Mapas", olhar, achados, prox=["- Abrir Visão executiva / Alertas nos top 3 do mapa."])


def narrativa_ar(resumo: pd.DataFrame, aq: pd.DataFrame | None = None) -> str:
    olhar = ["- PM2.5 alto + SRAG/Sentinela sobe prioridade respiratória de plantão."]
    achados = []
    if resumo is not None and not resumo.empty and "pm25_ugm3" in resumo.columns:
        p = pd.to_numeric(resumo["pm25_ugm3"], errors="coerce")
        achados.append(f"- PM2.5 médio (resumo): **{_fmt(p.mean())}** µg/m³ (máx {_fmt(p.max())}).")
        n = int(p.notna().sum())
        achados.append(f"- Municípios com PM2.5 no resumo: **{n}**.")
    if aq is not None and not aq.empty:
        achados.append(f"- Linhas qualidade do ar: **{_fmt(len(aq), 0)}**.")
    if not achados:
        achados.append("- Sem PM2.5 nesta rodada — ative Copernicus/CAMS no pipeline.")
    return _narr(
        "Qualidade do ar",
        olhar,
        achados,
        ["- Proxy satélite ≠ medição de estação local."],
        ["- Cruzar top PM2.5 com SIVEP e AdaptaSUS (ar/queimadas)."],
    )


def narrativa_operacional(resumo: pd.DataFrame, ops: pd.DataFrame | None = None) -> str:
    olhar = ["- Baixa resiliência + alta prioridade operacional = território a reforçar."]
    achados = []
    if resumo is not None and not resumo.empty and "indice_resiliencia" in resumo.columns:
        r = pd.to_numeric(resumo["indice_resiliencia"], errors="coerce")
        achados.append(f"- Resiliência média: **{_fmt(r.mean())}** (mín {_fmt(r.min())}).")
    if ops is not None and not ops.empty:
        achados.append(f"- Linhas CNES/ops: **{_fmt(len(ops), 0)}**.")
        if "indice_capacidade_cnes" in ops.columns:
            c = pd.to_numeric(ops["indice_capacidade_cnes"], errors="coerce")
            achados.append(f"- Capacidade CNES média: **{_fmt(c.mean())}**.")
    if not achados:
        achados.append("- Capacidade CNES/estoque ainda parcial nesta rodada.")
    return _narr(
        "Operacional",
        olhar,
        achados,
        ["- Lacuna de equipamentos no DW ≠ zero equipamentos no município."],
        ["- Priorizar municípios com baixa resiliência e pressão vermelha."],
    )


def narrativa_adaptasus(resumo: pd.DataFrame) -> str:
    olhar = ["- Risco dominante + índice de adaptação 0–100 orientam o pacote AdaptaSUS."]
    achados = []
    if resumo is not None and not resumo.empty and "indice_adaptacao_climatica" in resumo.columns:
        a = pd.to_numeric(resumo["indice_adaptacao_climatica"], errors="coerce")
        achados.append(f"- Adaptação média: **{_fmt(a.mean())}** (máx {_fmt(a.max())}).")
    if resumo is not None and not resumo.empty and "risco_adaptasus_dominante" in resumo.columns:
        vc = resumo["risco_adaptasus_dominante"].astype(str).value_counts().head(5).to_dict()
        achados.append(f"- Riscos dominantes: {', '.join(f'{k}={v}' for k, v in vc.items())}.")
    if not achados:
        achados.append("- Scores AdaptaSUS ainda não preenchidos no resumo.")
    return _narr(
        "AdaptaSUS",
        olhar,
        achados,
        ["- WASH sem fonte = lacuna, não risco zero."],
        ["- Abrir ranking AdaptaSUS e cruzar com Alertas."],
    )


def narrativa_inteligencia(resumo: pd.DataFrame, pred: pd.DataFrame | None = None) -> str:
    olhar = ["- Predição 7d + tendência ↑ marcam municípios a vigiar na semana."]
    achados = []
    if pred is not None and not pred.empty:
        achados.append(f"- Municípios com predição 7d: **{_fmt(len(pred), 0)}**.")
    if resumo is not None and not resumo.empty and "tendencia_7d" in resumo.columns:
        vc = resumo["tendencia_7d"].astype(str).str.lower().value_counts().to_dict()
        achados.append(f"- Tendências: {', '.join(f'{k}={v}' for k, v in vc.items())}.")
    if resumo is not None and not resumo.empty and "indice_vigilancia_integrada" in resumo.columns:
        v = pd.to_numeric(resumo["indice_vigilancia_integrada"], errors="coerce")
        achados.append(f"- Vigilância integrada média: **{_fmt(v.mean())}**.")
    if not achados:
        achados.append("- Sem predição/tendência nesta rodada — rode o enrichment.")
    return _narr(
        "Inteligência",
        olhar,
        achados,
        ["- Predição 7d ≠ cenário sazonal de setembro."],
        ["- Listar ↑ tendência e abrir Alertas / Visão executiva."],
    )


def narrativa_correlacao(corr: pd.DataFrame) -> str:
    olhar = ["- Foque pares com |ρ| alto e n adequado; depois o scatter."]
    achados = []
    if corr is not None and not corr.empty:
        achados.append(f"- Pares na tabela: **{_fmt(len(corr), 0)}**.")
        rho_col = next((c for c in ["abs_spearman", "spearman", "rho"] if c in corr.columns), None)
        if rho_col:
            top = corr.copy()
            top[rho_col] = pd.to_numeric(top[rho_col], errors="coerce").abs()
            top = top.sort_values(rho_col, ascending=False).head(3)
            for _, r in top.iterrows():
                achados.append(
                    f"- {_fmt(r.get(rho_col))}: {r.get('exposicao', r.get('var_x', '?'))} × "
                    f"{r.get('desfecho', r.get('var_y', '?'))}."
                )
    else:
        achados.append("- Sem pares suficientes (mín. ~12 municípios com dados válidos).")
    return _narr(
        "Correlação",
        olhar,
        achados,
        ["- Correlação ecológica ≠ causalidade clínica."],
        ["- Hipóteses fortes → validar em Sazonalidade/OR e no território."],
    )


def narrativa_arbo(arbo_mun: pd.DataFrame) -> str:
    olhar = ["- Casos 7d + incidência; cruze top municípios com calor/chuva."]
    achados = []
    if arbo_mun is not None and not arbo_mun.empty:
        achados.append(f"- Municípios: **{_fmt(arbo_mun['cod_ibge'].nunique() if 'cod_ibge' in arbo_mun.columns else len(arbo_mun), 0)}**.")
        if "casos_arbovirus_7d" in arbo_mun.columns:
            s = pd.to_numeric(arbo_mun["casos_arbovirus_7d"], errors="coerce").fillna(0)
            achados.append(f"- Casos arbovírus 7d (soma): **{_fmt(s.sum(), 0)}**.")
            top = arbo_mun.assign(_c=s).sort_values("_c", ascending=False).head(3)
            if "municipio" in top.columns:
                achados.append(
                    "- Top 7d: "
                    + ", ".join(f"{r.get('municipio')} ({_fmt(r.get('_c'), 0)})" for _, r in top.iterrows())
                    + "."
                )
    else:
        achados.append("- Tabelas de arboviroses ainda vazias nesta rodada.")
    return _narr("Arboviroses", olhar, achados, prox=["- Cruzar top com Clima/TITAN e Assistência."])


def narrativa_sivep(daily: pd.DataFrame) -> str:
    olhar = ["- Casos/óbitos SRAG e cobertura lab.; compare com ar e calor."]
    achados = []
    if daily is not None and not daily.empty:
        casos = pd.to_numeric(daily.get("casos_srag"), errors="coerce").fillna(0).sum() if "casos_srag" in daily.columns else 0
        obitos = pd.to_numeric(daily.get("obitos"), errors="coerce").fillna(0).sum() if "obitos" in daily.columns else 0
        achados.append(f"- Casos SRAG (série): **{_fmt(casos, 0)}** · óbitos **{_fmt(obitos, 0)}**.")
        if "municipio" in daily.columns:
            achados.append(f"- Municípios na série: **{_fmt(daily['municipio'].nunique(), 0)}**.")
    else:
        achados.append("- Sem série SIVEP nesta rodada.")
    return _narr("SIVEP", olhar, achados, prox=["- Abrir Qualidade do ar e Sentinela SG em paralelo."])


def narrativa_sentinela(agregado: pd.DataFrame) -> str:
    olhar = ["- Metas SG e circulação viral nas unidades sentinela."]
    achados = [
        f"- Linhas agregadas: **{_fmt(len(agregado) if agregado is not None else 0, 0)}**."
        if agregado is not None and not agregado.empty
        else "- Sem agregado Sentinela nesta rodada — verificar alimentação das unidades."
    ]
    return _narr("Sentinela SG", olhar, achados)


def narrativa_geocalor(geo: pd.DataFrame, status: str | None = None) -> str:
    olhar = ["- RR por lag: picos em 0–3 dias sugerem efeito agudo de calor."]
    achados = []
    if geo is not None and not geo.empty:
        achados.append(f"- Linhas GeoCalor: **{_fmt(len(geo), 0)}**.")
        if "municipio" in geo.columns:
            achados.append(f"- Municípios: **{_fmt(geo['municipio'].nunique(), 0)}**.")
    else:
        achados.append("- Tabela GeoCalor vazia ou status insuficiente nesta rodada.")
    if status:
        achados.append(f"- Status operacional: `{status}`.")
    return _narr(
        "GeoCalor",
        olhar,
        achados,
        ["- RR exploratório ≠ laudo causal individual."],
        ["- Se status insuficiente, completar série diária e rerodar consolidação."],
    )


def narrativa_hidro(cemaden: pd.DataFrame, ana: pd.DataFrame | None = None) -> str:
    olhar = ["- Alertas Cemaden abertos + risco ANA + chuva no município."]
    achados = [
        f"- Alertas Cemaden: **{_fmt(len(cemaden) if cemaden is not None else 0, 0)}**.",
    ]
    if ana is not None and not ana.empty:
        achados.append(f"- Municípios risco ANA: **{_fmt(len(ana), 0)}**.")
    return _narr("Cemaden/ANA", olhar, achados, prox=["- Cruzar com alerta integrado e solo saturado."])


def narrativa_vigibarragens(barragens: pd.DataFrame, risco: pd.DataFrame | None = None) -> str:
    olhar = [
        "- Barragens de mineração cadastradas (SIGBM/ANM) e população exposta na ZAS.",
        "- Nível de emergência (NE1/NE2/NE3) eleva o nível operacional do município.",
    ]
    n_barr = len(barragens) if barragens is not None else 0
    achados = [f"- Barragens monitoradas: **{_fmt(n_barr, 0)}**."]
    if risco is not None and not risco.empty:
        achados.append(f"- Municípios com exposição: **{_fmt(len(risco), 0)}**.")
        if "populacao_zas_total" in risco.columns:
            pop = pd.to_numeric(risco["populacao_zas_total"], errors="coerce").fillna(0).sum()
            achados.append(f"- População estimada na ZAS: **{_fmt(pop, 0)}** hab.")
        if "n_em_emergencia" in risco.columns:
            emerg = int(pd.to_numeric(risco["n_em_emergencia"], errors="coerce").fillna(0).sum())
            if emerg:
                achados.append(f"- Barragens em emergência (NE2/NE3): **{_fmt(emerg, 0)}**.")
    return _narr(
        "VigiBarragens",
        olhar,
        achados,
        nao=["- Cadastro/amostra ≠ inspeção de segurança; confirme com ANM/Defesa Civil."],
        prox=["- Cruzar ZAS com plano de contingência e leitos do município a jusante."],
    )


def narrativa_geo(resumo: pd.DataFrame, status: str = "") -> str:
    olhar = ["- Validar IBGE/regional antes de confiar no mapa."]
    achados = [f"- Municípios no cadastro/recorte: **{_fmt(len(resumo) if resumo is not None else 0, 0)}**."]
    if status:
        achados.append(f"- Status shapefile: {status}")
    if resumo is not None and not resumo.empty:
        n_xy = int(pd.to_numeric(resumo.get("lat"), errors="coerce").notna().sum()) if "lat" in resumo.columns else 0
        achados.append(f"- Com lat/lon: **{n_xy}**.")
    return _narr("Geografia", olhar, achados)


def narrativa_calculos() -> str:
    return _narr(
        "Cálculos",
        ["- Consulte limiares e pesos antes de questionar um nível."],
        [
            "- Esta aba documenta a metodologia (settings + fórmulas).",
            "- Prioridade global, pressão G/A/V e nível Verde→Roxa são camadas distintas.",
        ],
        ["- Mudar YAML sem rerodar enrichment não atualiza a base."],
        ["- Após ajuste metodológico, rode enrichment e valide Visão executiva."],
    )


def narrativa_sazonal_or(or_df: pd.DataFrame, mensal: pd.DataFrame) -> str:
    olhar = [
        "- Índice sazonal > 1 e OR significativos (p&lt;0,05) são sinais de priorização, não causalidade.",
        "- Método espelha o painel de Meningites (sazonalidade + OR ecológico).",
    ]
    lines = []
    if mensal is not None and not mensal.empty and "indice_sazonal" in mensal.columns:
        top = mensal.sort_values("indice_sazonal", ascending=False).head(1)
        if not top.empty:
            lines.append(f"- Mês de pico sazonal: **{top.iloc[0].get('mes_rotulo')}** (índice {_fmt(top.iloc[0].get('indice_sazonal'))}).")
    if or_df is not None and not or_df.empty:
        sig = int(pd.to_numeric(or_df.get("significativo_005"), errors="coerce").fillna(0).astype(int).sum()) if "significativo_005" in or_df.columns else 0
        lines.append(f"- Pares OR calculados: **{_fmt(len(or_df), 0)}**; significativos (p&lt;0,05): **{sig}**.")
        or_col = "or" if "or" in or_df.columns else None
        best = or_df.sort_values(or_col, ascending=False).head(1) if or_col else or_df.head(1)
        if not best.empty:
            lines.append(
                f"- Maior OR: **{best.iloc[0].get('exposicao')} → {best.iloc[0].get('desfecho')}** "
                f"(OR={_fmt(best.iloc[0].get('or'))})."
            )
    if not lines:
        lines.append("- Sem tabelas OR/sazonalidade nesta rodada.")
    nao = [
        "- OR ecológico municipal ≠ risco individual.",
        "- Sazonalidade histórica não substitui nowcasting da semana.",
    ]
    prox = ["- Cruzar pares OR significativos com municípios em prioridade global alta."]
    txt = (
        "**Justificativa (Sazonalidade/OR)**\n\n"
        + _bloco("O que olhar", olhar)
        + _bloco("Achados desta rodada", lines)
        + _bloco("O que não concluir", nao)
        + _bloco("Próximo passo", prox)
    )
    return _fecho(txt)


def _maybe_enrich_llm(base_txt: str, session_key: str) -> str:
    """Camada opcional de IA (mesmo endpoint do boletim). Só se o usuário marcar e USE_LLM_REPORT=true."""
    use = st.session_state.get(f"llm_interp_{session_key}", False)
    if not use:
        return base_txt
    try:
        from sisclima.ai.report_generator import maybe_llm_report

        ctx = {
            "aba": session_key,
            "instrucao": (
                "Reescreva em português claro para plantão CIEVS, sem inventar números. "
                "Preserve os achados; acrescente só leitura operacional (o que olhar / próximo passo)."
            ),
            "texto_base": base_txt[:6000],
        }
        extra = maybe_llm_report(ctx)
        if extra:
            return base_txt + "\n\n### Narrativa IA (revisar antes de usar)\n\n" + extra
        return base_txt + "\n\n_IA não disponível nesta rodada (USE_LLM_REPORT / LLM_API_*). Mantido texto determinístico._"
    except Exception as exc:  # noqa: BLE001
        return base_txt + f"\n\n_Assistente IA indisponível: {exc}_"


def render_interpretacao(
    session_key: str,
    guide_html: str,
    build_narr: Callable[[], str],
    titulo: str = "Ajudante CIEVS — justificativa e insights (padrão Meningites)",
) -> None:
    """Padrão Meningites: guia sempre visível + narrativa automática + IA opcional + download."""
    st.markdown(guide_html, unsafe_allow_html=True)
    st.markdown(f"#### {titulo}")
    st.caption(
        "Texto determinístico com o que olhar · achados · o que não concluir · próximo passo. "
        "Marque IA só se USE_LLM_REPORT estiver ativo — números não são inventados."
    )
    c1, c2 = st.columns([2, 1])
    with c1:
        gerar = st.button("Gerar / atualizar texto justificativo", key=f"btn_interp_{session_key}")
    with c2:
        st.checkbox(
            "Incluir narrativa IA (opcional)",
            key=f"llm_interp_{session_key}",
            help="Requer USE_LLM_REPORT=true e LLM_API_URL/KEY no ambiente. Nunca inventa indicadores.",
        )
    if gerar or f"narr_{session_key}" not in st.session_state:
        base = build_narr()
        st.session_state[f"narr_{session_key}"] = _maybe_enrich_llm(base, session_key)
    elif st.session_state.get(f"llm_interp_{session_key}") and st.button(
        "Aplicar IA ao texto atual", key=f"btn_llm_{session_key}"
    ):
        base = build_narr()
        st.session_state[f"narr_{session_key}"] = _maybe_enrich_llm(base, session_key)

    txt = st.session_state.get(f"narr_{session_key}") or build_narr()
    with st.container():
        st.markdown(txt)
    st.download_button(
        "Baixar justificativa (.md)",
        data=txt,
        file_name=f"sis_justificativa_{session_key}.md",
        mime="text/markdown",
        key=f"dl_interp_{session_key}",
    )
