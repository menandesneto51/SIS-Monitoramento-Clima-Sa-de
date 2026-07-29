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
    titulo: str = "Justificativa dos achados (assistente CIEVS)",
) -> None:
    """Padrão Meningites: guia sempre visível + narrativa sob demanda + IA opcional + download."""
    st.markdown(guide_html, unsafe_allow_html=True)
    st.markdown(f"#### {titulo}")
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
