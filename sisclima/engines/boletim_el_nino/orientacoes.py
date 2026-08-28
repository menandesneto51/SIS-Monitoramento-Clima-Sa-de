# -*- coding: utf-8 -*-
"""Orientações operacionais por cenário climático."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL, SELOBS, SELPROJ
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_num, md_table

log = get_logger(__name__)

ORIENTACOES_PATH = ROOT / "config" / "boletim_el_nino_orientacoes.yaml"


def load_orientacoes_config(path: Path | None = None) -> dict[str, Any]:
    target = path or ORIENTACOES_PATH
    try:
        if not target.exists():
            return {}
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Catálogo de orientações indisponível: %s", exc)
        return {}


def _resolve_situacao(snap: dict[str, Any], campo: str | None) -> str:
    if not campo:
        return INDISPONIVEL
    agr = snap.get("agravos_monitorados") or {}
    n = snap.get("n_municipios")
    if campo == "municipios_hidro_alerta":
        hf = snap.get("hydro_facts") or {}
        v = hf.get("low_availability")
        if v is None:
            v = (agr.get("hidrorelacionados") or {}).get("municipios_hidro_alerta")
        if v is None:
            return INDISPONIVEL
        return (
            f"{v} município com sinal hidrológico de baixa disponibilidade no recorte disponível."
            if int(v) == 1
            else f"{v} municípios com sinal hidrológico de baixa disponibilidade no recorte disponível."
        )
    if campo == "municipios_calor_seco":
        v = (agr.get("calor_desidratacao") or {}).get("municipios_calor_seco")
        return f"{v} municípios em condição combinada de calor seco (Tmáx ≥ 37 °C e UR ≤ 30%)." if v is not None else INDISPONIVEL
    if campo == "n_pm25_25":
        v = snap.get("n_pm25_25")
        if v is None:
            return INDISPONIVEL
        return f"{fmt_frac(v, n)} municípios com PM2,5 ≥ 25 µg/m³."
    val = snap.get(campo)
    if val is None:
        return INDISPONIVEL
    return str(val)


def _texto_calor_epidemiologico(snap: dict[str, Any]) -> str:
    n = snap.get("n_municipios")
    n37 = int(snap.get("n_tmax_37") or 0)
    n_utci = int(snap.get("n_utci_32") or 0)
    n_seco = int(
        ((snap.get("agravos_monitorados") or {}).get("calor_desidratacao") or {}).get("municipios_calor_seco")
        or 0
    )
    base = (
        f"Calor: {fmt_int(n37)} municípios apresentaram Tmáx ≥ 37 °C; "
        f"{fmt_int(n_utci)} apresentaram UTCI ≥ 32 °C."
    )
    if n_seco == 0:
        base += (
            " O indicador combinado de calor seco (Tmáx ≥ 37 °C e UR ≤ 30%) "
            "não foi observado nesta rodada."
        )
    else:
        base += (
            f" O indicador combinado de calor seco (Tmáx ≥ 37 °C e UR ≤ 30%) "
            f"foi observado em {fmt_frac(n_seco, n)}."
        )
    return base


def _bloco_cenario_onda_calor(snap: dict[str, Any]) -> str:
    delta = snap.get("delta_projecao") or {}
    n_agr = int(snap.get("n_agravadores") or 0) or (
        int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    )
    n_onda = int(snap.get("n_onda_calor_agravadores") or 0)
    proj = ""
    if n_agr:
        proj = (
            f"\n- Projeção `{SELPROJ}`: entre os {fmt_int(n_agr)} municípios com elevação projetada da "
            f"classificação, {fmt_int(n_onda)} apresentam previsão de onda de calor no horizonte analisado."
        )
    return (
        f"**CENÁRIO: ONDA DE CALOR / CALOR EXTREMO**\n"
        f"- Observado `{SELOBS}`: nenhum município atende simultaneamente ao critério operacional "
        f"Tmáx ≥ 37 °C e UR ≤ 30% nesta rodada.{proj}\n"
        f"- Impactos à saúde: Exaustão pelo calor, desidratação, agravamento cardiovascular e respiratório.\n"
        f"- Ação municipal: Monitorar atendimentos e internações por calor/desidratação.\n"
        f"- Ação SES-MT: Priorizar municípios nas classes vermelha e roxa; apoiar regionais com maior carga térmica."
    )


def _quadro_cenario(cfg: dict[str, Any], snap: dict[str, Any]) -> str:
    acoes = cfg.get("acoes_municipio") or {}
    situacao = _resolve_situacao(snap, cfg.get("situacao_campo"))
    ses = str(cfg.get("acoes_ses") or "—")
    if "{n_crit}" in ses or "vermelho/roxa" in ses:
        n_crit = snap.get("n_vermelha_roxa")
        ses = ses.replace("{n_crit}", str(n_crit) if n_crit is not None else INDISPONIVEL)
    acao_mun = next(iter(acoes.values()), "—") if isinstance(acoes, dict) else "—"
    return f"""
**CENÁRIO: {cfg.get('nome', '—')}**
- Situação: {situacao}
- Impactos à saúde: {cfg.get('repercussao', '—')}
- Ação municipal: {acao_mun}
- Ação SES-MT: {ses}
"""


def orientacoes_por_cenario(snap: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    cfg = config or load_orientacoes_config()
    cenarios = cfg.get("cenarios") or []
    if not cenarios:
        return "_Catálogo de orientações indisponível nesta rodada._"
    blocos = []
    for c in cenarios:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").lower()
        nome = str(c.get("nome") or "").lower()
        if cid == "onda_calor" or "onda de calor" in nome:
            blocos.append(_bloco_cenario_onda_calor(snap))
            continue
        if "inund" in cid or "chuva_intensa" in cid or "enxurr" in nome:
            hf = snap.get("hydro_facts") or {}
            n_flood = int(hf.get("flood_risk_high") or 0)
            cob = hf.get("coverage")
            n_est = hf.get("state_total") or snap.get("n_municipios")
            if n_flood > 0:
                cob_txt = fmt_frac(cob, n_est) if cob is not None and n_est else INDISPONIVEL
                mun_txt = "1 município" if n_flood == 1 else f"{n_flood} municípios"
                blocos.append(
                    "**CENÁRIO: CHUVA INTENSA / ENXURRADAS / INUNDAÇÕES**\n"
                    f"- Situação: foi identificado sinal de risco elevado de inundação em {mun_txt} "
                    f"no recorte hidrológico disponível. A cobertura hidrológica corresponde a apenas "
                    f"{cob_txt}; portanto, o achado deve ser interpretado como sinal localizado e não "
                    "permite caracterização do cenário estadual.\n"
                    "- Ação: monitorar o alerta local; articular o município e a Regional de Saúde; "
                    "se o evento for confirmado, acionar a vigilância de DDA, leptospirose e traumas."
                )
            else:
                cob_txt = fmt_frac(cob, n_est) if cob is not None and n_est else INDISPONIVEL
                blocos.append(
                    "**CENÁRIO: CHUVA INTENSA / ENXURRADAS / INUNDAÇÕES**\n"
                    "- Situação: não foi identificado sinal de risco elevado de inundação no recorte "
                    f"hidrológico disponível (cobertura: {cob_txt}). A cobertura parcial não permite "
                    "caracterização do cenário estadual.\n"
                    "- Se houver alerta oficial ou ocorrência municipal, acionar vigilância de DDA, "
                    "leptospirose e traumas."
                )
            continue
        blocos.append(_quadro_cenario(c, snap))
    return "\n".join(blocos)


def matriz_clima_saude_acao(snap: dict[str, Any]) -> str:
    """Blocos por cenário — evita tabela larga de seis colunas."""
    if not snap.get("disponivel"):
        return f"_{INDISPONIVEL}_"

    n = snap.get("n_municipios")
    niveis = snap.get("niveis") or {}
    n25 = snap.get("n_pm25_25")
    blocos: list[str] = []

    if niveis.get("roxa") or niveis.get("vermelha"):
        blocos.append(
            "**Calor extremo**\n"
            "- Nível atual: classes vermelha e roxa\n"
            "- Impactos potenciais: desidratação e agravamento cardiorrespiratório\n"
            "- Insumos a revisar: soluções de reidratação oral e insumos de suporte conforme protocolos\n"
            "- Ação municipal: avaliar capacidade assistencial e comunicação de risco\n"
            "- Ação SES-MT: apoiar regionais prioritárias"
        )
    if n25:
        blocos.append(
            "**Fumaça e qualidade do ar**\n"
            f"- Situação: {fmt_frac(n25, n)} municípios com PM2,5 ≥ 25 µg/m³\n"
            "- Impactos potenciais: agravamento de doenças respiratórias\n"
            "- Insumos a revisar: insumos respiratórios conforme protocolo\n"
            "- Ação municipal: orientar redução de exposição e monitorar SRAG conforme protocolos\n"
            "- Ação SES-MT: consolidar casos e orientar regionais"
        )
    if not blocos:
        return "_Sem cenário prioritário para matriz nesta rodada._"
    return "\n\n".join(blocos)


def impactos_potenciais_saude(config: dict[str, Any] | None = None, snap: dict[str, Any] | None = None) -> str:
    cfg = config or load_orientacoes_config()
    items = cfg.get("impactos_saude") or []
    snap = snap or {}
    if not items:
        return md_table(
            ["Cenário / exposição", "Agravos a monitorar", "Indicadores"],
            [["—", "—", "—"]],
        )
    rows_out: list[list[str]] = []
    for i in items:
        if not isinstance(i, dict):
            continue
        ev = str(i.get("evento") or "")
        if ("chuva" in ev.lower() or "inund" in ev.lower()) and not snap.get("evidencia_inundacao"):
            continue
        rows_out.append(
            [
                f"{i.get('evento', '—')} / {i.get('exposicao', '—')}",
                str(i.get("agravos", "—")),
                str(i.get("indicadores", "—")),
            ]
        )
    tabela = md_table(["Cenário / exposição", "Agravos a monitorar", "Indicadores"], rows_out)
    hf = snap.get("hydro_facts") or {}
    n_flood = int(hf.get("flood_risk_high") or 0)
    if n_flood > 0:
        cob = hf.get("coverage")
        n_est = hf.get("state_total") or snap.get("n_municipios")
        mun_txt = "1 município" if n_flood == 1 else f"{n_flood} municípios"
        tabela += (
            f"\n\n> **Cenário hidrológico de inundação:** sinal localizado em {mun_txt} "
            f"no recorte hidrológico disponível (cobertura {fmt_frac(cob, n_est)}). "
            "Não caracteriza cenário estadual. Se o evento for confirmado, monitorar DDA, leptospirose e traumas."
        )
    return tabela
