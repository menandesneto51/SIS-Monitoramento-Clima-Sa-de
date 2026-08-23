# -*- coding: utf-8 -*-
"""Estoques SES/SAF para o boletim semanal El Niño."""
from __future__ import annotations

from typing import Any

import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL, SELOBS
from sisclima.engines.boletim_el_nino.formatters import fmt_date_pt, fmt_int, fmt_num, md_table
from sisclima.engines.boletim_el_nino.referencias import cite

log = get_logger(__name__)

_LIMIAR_VERMELHA = 3
_LIMIAR_LARANJA = 7
_LIMIAR_AMARELA = 10
_MAX_IDADE_DIAS_ESTOQUE = 14  # além disso: não classificar como situação atual


def _load_idade_maxima_dias() -> int:
    path = ROOT / "config" / "settings.yaml"
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        lim = (cfg.get("limiares_operacionais") or {}).get("estoque_saf") or {}
        return int(lim.get("max_idade_dias", _MAX_IDADE_DIAS_ESTOQUE))
    except Exception:  # noqa: BLE001
        return _MAX_IDADE_DIAS_ESTOQUE


def _load_limiares() -> dict[str, float]:
    path = ROOT / "config" / "settings.yaml"
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        lim = (cfg.get("limiares_operacionais") or {}).get("autonomia_insumos_dias") or {}
        return {
            "vermelha": float(lim.get("vermelha_min", _LIMIAR_VERMELHA)),
            "laranja": float(lim.get("laranja_min", _LIMIAR_LARANJA)),
            "amarela": float(lim.get("amarela_min", _LIMIAR_AMARELA)),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("Limiares estoque indisponíveis: %s", exc)
        return {"vermelha": _LIMIAR_VERMELHA, "laranja": _LIMIAR_LARANJA, "amarela": _LIMIAR_AMARELA}


def _autonomia_calculavel(estoque: Any, consumo: Any) -> float | None:
    """autonomia = estoque / consumo somente se consumo > 0 e estoque numérico."""
    try:
        if consumo is None or pd.isna(consumo) or float(consumo) <= 0:
            return None
        if estoque is None or pd.isna(estoque):
            return None
        return float(estoque) / float(consumo)
    except (TypeError, ValueError):
        return None


def _classificar_autonomia(dias: float | None, lim: dict[str, float]) -> str:
    if dias is None or (isinstance(dias, float) and pd.isna(dias)):
        return "nao_classificada"
    if dias == float("inf"):
        return "verde"
    d = float(dias)
    if d < lim["vermelha"]:
        return "vermelha"
    if d < lim["laranja"]:
        return "laranja"
    if d < lim["amarela"]:
        return "amarela"
    return "verde"


def build_estoque_saf_section(estoque: pd.DataFrame | None) -> dict[str, Any]:
    """Resume autonomia de insumos para SAF/SES com validação de consumo."""
    citacao = cite("ses_estoque_saf")
    if estoque is None or estoque.empty:
        return {
            "disponivel": False,
            "resumo_md": (
                f"Estoques estratégicos SES/SAF **indisponíveis nesta rodada**. "
                f"Avaliar conferência junto à Assistência Farmacêutica {citacao}."
            ),
            "tabela_md": INDISPONIVEL,
            "data_referencia": None,
        }

    df = estoque.copy()
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        data_ref = df["data"].max()
        df = df[df["data"] == data_ref].copy()
    else:
        data_ref = pd.NaT

    lim = _load_limiares()
    idade_max = _load_idade_maxima_dias()
    latest = df.sort_values(["municipio", "item"]) if "municipio" in df.columns else df

    if "estoque_total" not in latest.columns:
        return {
            "disponivel": False,
            "resumo_md": f"Base de estoque incompleta para cálculo de autonomia {citacao}.",
            "tabela_md": INDISPONIVEL,
            "data_referencia": str(data_ref.date()) if pd.notna(data_ref) else None,
        }

    idade_dias = None
    defasado = False
    if pd.notna(data_ref):
        idade_dias = int((pd.Timestamp.today().normalize() - pd.Timestamp(data_ref).normalize()).days)
        defasado = idade_dias > idade_max

    cons_col = "consumo_medio_diario" if "consumo_medio_diario" in latest.columns else None
    autos: list[float | None] = []
    classes: list[str] = []
    for _, row in latest.iterrows():
        cons = row.get(cons_col) if cons_col else None
        dias = _autonomia_calculavel(row.get("estoque_total"), cons)
        autos.append(dias)
        # Se defasado: não classificar como situação atual
        classes.append("nao_avaliavel_defasagem" if defasado else _classificar_autonomia(dias, lim))
    latest = latest.copy()
    latest["_autonomia"] = autos
    latest["classe_autonomia"] = classes

    n_calc = int(sum(1 for a in autos if a is not None))
    n_nao = int(len(autos) - n_calc)
    data_txt = fmt_date_pt(data_ref) if pd.notna(data_ref) else "—"
    n_mun = latest["municipio"].nunique() if "municipio" in latest.columns else len(latest)
    n_itens = latest["item"].nunique() if "item" in latest.columns else 0

    if defasado:
        # Conta "históricos" com autonomia baixa apenas para orientar validação
        hist_crit = 0
        for a in autos:
            if a is not None and a < lim["laranja"]:
                hist_crit += 1
        alerta = (
            f"> **Atenção — última atualização da base de estoque: {data_txt}.**\n"
            f"> Os valores devem ser confirmados no sistema oficial antes de qualquer decisão operacional.\n"
            f"> **Status atual: NÃO AVALIÁVEL POR DEFASAGEM** "
            f"(carga com {fmt_int(idade_dias)} dias; limite institucional {fmt_int(idade_max)} dias)."
        )
        resumo = (
            f"{alerta}\n\n"
            f"Última informação disponível: **{data_txt}** — dado desatualizado para avaliação da situação corrente {citacao}. "
            f"Cobertura cadastral na carga: **{fmt_int(n_mun)}** municípios · **{fmt_int(n_itens)}** itens. "
            f"**{fmt_int(hist_crit)}** registros que apresentavam autonomia crítica na última carga disponível "
            "e requerem validação no sistema oficial. "
            "Não se classifica ruptura atual nem ranking operacional com esta carga. "
            "O detalhamento municipal/item permanece no **painel operacional** e em anexo interno, "
            "fora do corpo principal deste boletim."
        )
        return {
            "disponivel": True,
            "defasado": True,
            "resumo_md": resumo,
            "tabela_md": (
                "_Detalhamento de registros históricos omitido do corpo principal "
                "(consultar painel / anexo interno após validação no sistema oficial)._"
            ),
            "titulo_tabela": "Última situação registrada — sujeita a validação",
            "data_referencia": data_txt,
            "n_municipios": n_mun,
            "n_criticos": 0,
            "n_vermelha": 0,
            "n_historicos_criticos": hist_crit,
            "n_calculaveis": n_calc,
            "n_nao_calculaveis": n_nao,
            "n_exibidos": 0,
            "limiares": lim,
            "idade_dias": idade_dias,
        }

    alerta_defasagem = (
        f"> **Atenção — última atualização da base de estoque: {data_txt}.** "
        "Os valores devem ser confirmados no sistema oficial antes de qualquer decisão operacional."
    )

    if n_calc == 0:
        resumo = (
            f"{alerta_defasagem}\n\n"
            f"Estoques SES/SAF — última carga **{data_txt}** {citacao}. "
            f"Cobertura cadastral: **{fmt_int(n_mun)}** municípios · **{fmt_int(n_itens)}** itens. "
            "A ausência de **consumo médio diário válido** impede o cálculo de autonomia em dias "
            "e a classificação de risco de desabastecimento nesta rodada. "
            "Os registros disponíveis exigem conferência pela Assistência Farmacêutica, "
            "sem interpretação automática de ruptura."
        )
        return {
            "disponivel": True,
            "defasado": False,
            "resumo_md": resumo,
            "tabela_md": "_Autonomia não calculável nesta rodada (consumo médio indisponível ou inválido)._",
            "titulo_tabela": "Registros selecionados de autonomia crítica",
            "data_referencia": data_txt,
            "n_municipios": n_mun,
            "n_criticos": 0,
            "n_vermelha": 0,
            "n_calculaveis": 0,
            "n_nao_calculaveis": n_nao,
            "n_exibidos": 0,
            "n_total_criticos": 0,
            "limiares": lim,
        }

    crit = latest[latest["classe_autonomia"].isin({"vermelha", "laranja"})].copy()
    crit = crit.sort_values("_autonomia", ascending=True, na_position="last")
    n_crit = int(len(crit))
    n_verm = int((latest["classe_autonomia"] == "vermelha").sum())
    exibidos = crit.head(20)

    rows = []
    for _, row in exibidos.iterrows():
        dias = row.get("_autonomia")
        dias_txt = fmt_num(dias, 1, " d") if dias is not None else "não calculável"
        cons = row.get(cons_col) if cons_col else None
        rows.append(
            [
                str(row.get("municipio") or "—"),
                str(row.get("item") or "—"),
                dias_txt,
                str(row.get("classe_autonomia") or "—"),
                fmt_int(row.get("estoque_total")),
                fmt_num(cons, 0) if cons is not None and not pd.isna(cons) and float(cons) > 0 else INDISPONIVEL,
            ]
        )
    n_exib = len(rows)

    resumo = (
        f"{alerta_defasagem}\n\n"
        f"Autonomia de insumos críticos da Assistência Farmacêutica — última carga **{data_txt}** {citacao}. "
        f"Cobertura: **{fmt_int(n_mun)}** municípios · **{fmt_int(n_itens)}** itens · "
        f"**{fmt_int(n_calc)}** combinações com autonomia calculável. "
        f"**{fmt_int(n_crit)}** registros que apresentavam autonomia crítica na última carga disponível "
        "e requerem validação no sistema oficial "
        f"(autonomia < {lim['laranja']:.0f} dias; crítica < {lim['vermelha']:.0f} dias), "
        f"das quais **{fmt_int(n_verm)}** em autonomia crítica. "
    )
    if n_nao:
        resumo += (
            f"**{fmt_int(n_nao)}** registros sem consumo médio válido não foram classificados. "
        )
    resumo += (
        "O indicador orienta conferência pela Assistência Farmacêutica e **não confirma ruptura** "
        "sem validação no sistema oficial de estoques."
    )
    if n_crit > n_exib:
        resumo += f" Exibidos **{fmt_int(n_exib)}** de **{fmt_int(n_crit)}** registros."

    tab_prefix = "### Última situação registrada — sujeita a validação\n\n"
    if n_crit > n_exib:
        tab_prefix += f"_Exibidos {fmt_int(n_exib)} de {fmt_int(n_crit)} registros._\n\n"

    tab = tab_prefix + md_table(
        ["Município", "Insumo", "Autonomia", "Classe", "Estoque", "Consumo médio/d"],
        rows,
        vazio="_Nenhum item abaixo do limiar laranja entre as combinações calculáveis._",
    )

    return {
        "disponivel": True,
        "defasado": False,
        "resumo_md": resumo,
        "tabela_md": tab,
        "titulo_tabela": "Última situação registrada — sujeita a validação",
        "data_referencia": data_txt,
        "n_municipios": n_mun,
        "n_criticos": n_crit,
        "n_vermelha": n_verm,
        "n_calculaveis": n_calc,
        "n_nao_calculaveis": n_nao,
        "n_exibidos": n_exib,
        "n_total_criticos": n_crit,
        "limiares": lim,
    }
