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
    nivel_v9 = str(payload.get("nivel_prioridade_v9") or "cinza").capitalize()
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
        f"- Alerta inteligente: {nivel_ai}",
        f"- Prioridade epidemiológica V9: {nivel_v9}",
        f"- Nível final para comunicação: {nivel.capitalize()}",
        "",
        "Indicadores principais:",
        f"- Tmax atual/proxy: {fmt_num(payload.get('tmax') or _ind_valor(payload, 'tmax'), 1, ' °C')}",
        f"- Tmax máxima 7 dias: {fmt_num(payload.get('tmax_pred'), 1, ' °C')}",
        f"- UTCI/proxy atual: {fmt_num(payload.get('utci_proxy') or payload.get('utci') or _ind_valor(payload, 'utci_proxy'), 1)}",
        f"- UTCI/proxy máximo 7 dias: {fmt_num(payload.get('utci_pred'), 1)}",
        f"- Risco cumulativo 3 dias atual: {fmt_num(payload.get('risco_cumulativo_3d') or _ind_valor(payload, 'risco_cumulativo_3d'), 2)}",
        f"- Risco cumulativo 3 dias máximo 7 dias: {fmt_num(payload.get('risco3d_pred'), 2)}",
        f"- PM2.5: {fmt_num(payload.get('pm25_ugm3') or payload.get('pm25') or _ind_valor(payload, 'pm25_ugm3'), 1, ' µg/m³')}",
        f"- IQA/score: {fmt_num(payload.get('iq_ar_score') or payload.get('iqa'), 1)}",
    ]
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
