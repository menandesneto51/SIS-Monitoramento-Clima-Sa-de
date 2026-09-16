# -*- coding: utf-8 -*-
"""Padrão textual dos alertas municipais ARARAS MT.

Ocupação hospitalar = IndicaSUS (filtros SIEGES).
Pressão hospitalar / assistencial no texto do alerta = SISREG (solicitações/fila).
Pressão por calor permanece indicador climático separado, quando existir.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.branding import PROJECT_DESCRIPTION, SYSTEM_NAME

EMOJI = {
    "cinza": "⚪",
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
}


def _num(x: Any) -> float | None:
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        v = float(pd.to_numeric(x, errors="coerce"))
        if pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def fmt_num(x: Any, dec: int = 1, suffix: str = "") -> str:
    v = _num(x)
    if v is None:
        return "indisponível"
    return f"{v:.{dec}f}{suffix}".replace(".", ",")


def _ind_valor(payload: dict[str, Any], campo: str) -> Any:
    if payload.get(campo) is not None and not (isinstance(payload.get(campo), float) and pd.isna(payload.get(campo))):
        return payload.get(campo)
    for ind in payload.get("indicadores") or []:
        if ind.get("campo") == campo:
            return ind.get("valor")
    return None


def _prioridade_linha(payload: dict[str, Any]) -> str | None:
    """Prioridade epidemiológica: V9 se existir; senão prioridade global; senão omite."""
    v9 = payload.get("nivel_prioridade_v9") or payload.get("nivel_priorizacao_v9")
    score_v9 = _num(payload.get("score_priorizacao_v9") or payload.get("prioridade_v9_score"))
    if v9 is not None and str(v9).strip() and str(v9).strip().lower() not in {"nan", "none", "—", "-"}:
        nivel = str(v9).strip().capitalize()
        if score_v9 is not None:
            return f"- Prioridade epidemiológica V9: {nivel} ({fmt_num(score_v9, 1)}/100)"
        if nivel.lower() != "cinza":
            return f"- Prioridade epidemiológica V9: {nivel}"
        # "cinza" sem score costuma ser default vazio — cai para prioridade global

    faixa = payload.get("faixa_prioridade_global") or payload.get("faixa_prioridade")
    score_g = _num(payload.get("indice_prioridade_global") or payload.get("score_prioridade_global"))
    if score_g is not None or (faixa and str(faixa).strip().lower() not in {"nan", "none", "—", "-", ""}):
        faixa_txt = str(faixa or "—").strip().replace("_", " ")
        if score_g is not None:
            return f"- Prioridade global: {fmt_num(score_g, 1)}/100 · faixa {faixa_txt}"
        return f"- Prioridade global: faixa {faixa_txt}"
    return None


def _iqa_linha(payload: dict[str, Any]) -> str:
    """IQA operacional (score 0–4) + nível qualitativo quando houver."""
    iq = payload.get("iq_ar_score")
    if iq is None or (isinstance(iq, float) and pd.isna(iq)):
        iq = payload.get("iqa")
    if iq is None or (isinstance(iq, float) and pd.isna(iq)):
        iq = _ind_valor(payload, "iq_ar_score")
    nivel = (
        payload.get("qualidade_ar_nivel")
        or _ind_valor(payload, "qualidade_ar_nivel")
        or ""
    )
    nivel_txt = str(nivel).strip().lower()
    if nivel_txt in {"nan", "none", "—", "-", ""}:
        nivel_txt = ""
    score_txt = fmt_num(iq, 1)
    if score_txt == "indisponível":
        return "- IQA/score: indisponível"
    if nivel_txt:
        return f"- IQA/score: {score_txt}/4 · {nivel_txt}"
    return f"- IQA/score: {score_txt}/4"


def _intensidade_ehf_txt(payload: dict[str, Any]) -> str:
    intens = payload.get("intensidade_ehf")
    if intens is None or (isinstance(intens, float) and pd.isna(intens)):
        intens = _ind_valor(payload, "intensidade_ehf")
    txt = str(intens or "").strip()
    if txt.lower() in {"", "none", "nan", "—", "-"}:
        return "—"
    return txt


def linhas_ocupacao_e_pressao_assistencial(payload: dict[str, Any]) -> list[str]:
    """Bloco padrão: ocupação IndicaSUS + pressão SISREG + leitos + nota."""
    ocup = payload.get("ocupacao_leitos_pct", payload.get("ocupacao_pct"))
    if ocup is None:
        ocup = _ind_valor(payload, "ocupacao_leitos_pct")
    fonte = str(payload.get("fonte_ocupacao") or "").strip() or "indisponível"
    leitos_t = payload.get("leitos_total", payload.get("leitos_existentes"))
    leitos_o = payload.get("leitos_ocupados")
    sis_sol = payload.get("kpi_sisreg_solicitacoes", payload.get("sisreg_solicitacoes"))
    if sis_sol is None:
        sis_sol = _ind_valor(payload, "kpi_sisreg_solicitacoes")
    sis_fila = payload.get("kpi_sisreg_fila_h", payload.get("sisreg_fila_h"))
    sis_sem = payload.get("kpi_sisreg_semaforo", payload.get("sisreg_semaforo")) or "indisponível"

    return [
        (
            f"- Ocupação hospitalar IndicaSUS (filtros SIEGES): "
            f"{fmt_num(ocup, 1, '%')} · fonte: {fonte}"
        ),
        (
            f"- Pressão hospitalar SISREG (solicitações): "
            f"{fmt_num(sis_sol, 0)} · "
            f"fila média: {fmt_num(sis_fila, 1, ' h')} · "
            f"semáforo: {sis_sem}"
        ),
        (
            f"- Leitos elegíveis / ocupados: "
            f"{fmt_num(leitos_t, 0)} / {fmt_num(leitos_o, 0)}"
        ),
        "- Nota: ocupação hospitalar (IndicaSUS) ≠ pressão hospitalar (SISREG).",
    ]


def format_alerta_municipal_padrao(payload: dict[str, Any]) -> str:
    """Texto completo do alerta municipal no padrão institucional."""
    mun = str(payload.get("municipio") or payload.get("alvo_nome") or "Município")
    ibge = str(payload.get("cod_ibge") or payload.get("alvo_id") or "—")
    nivel = str(payload.get("nivel_final") or payload.get("nivel") or "cinza").lower().strip()
    if nivel == "amarelo":
        nivel = "amarela"
    if nivel == "vermelho":
        nivel = "vermelha"
    if nivel == "roxo":
        nivel = "roxa"
    emoji = EMOJI.get(nivel, "⚪")
    pred = payload.get("predicao") or {}
    nivel_pred = str(
        payload.get("nivel_predicao_7d")
        or pred.get("nivel_predicao_7d")
        or "cinza"
    ).capitalize()
    nivel_ai = str(payload.get("nivel_alerta_inteligente") or "cinza").capitalize()
    gerado = payload.get("emitido_em") or payload.get("gerado_em") or "—"
    atualizados = payload.get("dados_atualizados_em") or payload.get("data_referencia") or gerado

    lines = [
        f"{emoji} Alerta {SYSTEM_NAME} — {mun} — {nivel.capitalize()}",
        PROJECT_DESCRIPTION,
        f"Dados atualizados em: {atualizados}",
        f"Emitido em: {gerado}",
        "",
        f"Município: {mun}",
        f"Código IBGE: {ibge}",
        "",
        "Síntese operacional:",
        f"- Nível operacional atual: {str(payload.get('nivel_operacional') or nivel).capitalize()}",
        f"- Predição 7 dias: {nivel_pred}",
        (
            f"- RIT (observado multidomínio): "
            f"{fmt_num(payload.get('rit_0_100') or _ind_valor(payload, 'rit_0_100') or (payload.get('rit') or {}).get('rit_0_100'), 0)}/100"
            f" · faixa {(payload.get('rit') or {}).get('rit_faixa') or payload.get('rit_faixa') or _ind_valor(payload, 'rit_faixa') or '—'}"
            f" · paralelo à projeção ~7d (térmica)"
        ),
        f"- Principal influenciador: {(payload.get('rit') or {}).get('explicacao_dominante') or '—'}",
        f"- Alerta inteligente: {nivel_ai}",
    ]
    prio = _prioridade_linha(payload)
    if prio:
        lines.append(prio)
    lines.append(f"- Nível final para comunicação: {nivel.capitalize()}")
    lines.extend(
        [
            "",
            "Indicadores principais:",
            f"- Tmax atual/proxy: {fmt_num(payload.get('tmax') or _ind_valor(payload, 'tmax'), 1, ' °C')}",
            f"- Tmax máxima 7 dias: {fmt_num(payload.get('tmax_pred'), 1, ' °C')}",
            f"- UTCI/proxy atual: {fmt_num(payload.get('utci_proxy') or payload.get('utci') or _ind_valor(payload, 'utci_proxy'), 1)}",
            f"- UTCI/proxy máximo 7 dias: {fmt_num(payload.get('utci_pred'), 1)}",
            f"- Risco cumulativo 3 dias atual: {fmt_num(payload.get('risco_cumulativo_3d') or _ind_valor(payload, 'risco_cumulativo_3d'), 2)}",
            f"- Risco cumulativo 3 dias máximo 7 dias: {fmt_num(payload.get('risco3d_pred'), 2)}",
            f"- PM2.5: {fmt_num(payload.get('pm25_ugm3') or payload.get('pm25') or _ind_valor(payload, 'pm25_ugm3'), 1, ' µg/m³')}",
            _iqa_linha(payload),
            (
                f"- EHF GeoCalor: {fmt_num(payload.get('ehf_geocalor') or payload.get('ehf') or _ind_valor(payload, 'ehf_geocalor'), 2)}"
                f" · intensidade {_intensidade_ehf_txt(payload)}"
                f" · ref. {payload.get('data_ehf_geocalor') or _ind_valor(payload, 'data_ehf_geocalor') or '—'}"
            ),
        ]
    )
    # Scorecard RIT por domínio (ex.: roxa por EHF e verde em PM2,5)
    rit = payload.get("rit") or {}
    dominios = rit.get("dominios") or []
    if dominios:
        lines.append("")
        lines.append("RIT — classificação por domínio:")
        for d in dominios:
            emoji_d = EMOJI.get(str(d.get("faixa") or "").lower(), "⚪")
            if d.get("status") == "valido":
                lines.append(
                    f"- {emoji_d} {d.get('rotulo')}: {fmt_num(d.get('score'), 0)}/100 · {d.get('faixa') or '—'}"
                )
            elif d.get("status") == "omitido_defasagem":
                lines.append(f"- ⚪ {d.get('rotulo')}: omitido por defasagem")
            else:
                lines.append(f"- ⚪ {d.get('rotulo')}: indisponível")
    lines.extend(linhas_ocupacao_e_pressao_assistencial(payload))
    # Pressão por calor fica explícita como clima, não como “assistencial hospitalar”
    pressao_calor = payload.get("pressao_calor_pct")
    if pressao_calor is not None and not (isinstance(pressao_calor, float) and pd.isna(pressao_calor)):
        lines.append(f"- Pressão por calor (painel): {fmt_num(pressao_calor, 1)}")
    lines.append("")

    if payload.get("motivo"):
        lines.append("Motivo técnico resumido:")
        lines.append(str(payload["motivo"])[:1200])
        lines.append("")

    geo_lines = payload.get("geocalor_linhas") or []
    if geo_lines:
        lines.extend(str(x) for x in geo_lines)
        lines.append("")

    recs = payload.get("recomendacoes") or []
    lines.append(f"Recomendações específicas para {mun}:")
    if recs:
        for r in recs:
            lines.append(f"- {r}")
    else:
        lines.append("- Manter monitoramento diário do painel e comunicação com a Vigilância em Saúde/Defesa Civil municipal.")
        lines.append("- Reforçar orientação à população sobre hidratação, evitar exposição ao sol nos horários críticos e reconhecer sinais de agravamento.")
        lines.append("- Orientar APS, urgência e rede assistencial para triagem de idosos, crianças, gestantes, pessoas com doenças crônicas, trabalhadores expostos ao sol e população em situação de rua.")
    lines.append("")
    lines.append("Encaminhamento:")
    lines.append("- Manter monitoramento diário, registrar ações adotadas e comunicar agravamento de cenário à Regional/CIEVS.")
    return "\n".join(lines)
