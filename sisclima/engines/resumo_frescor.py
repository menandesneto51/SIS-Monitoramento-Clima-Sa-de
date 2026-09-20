# -*- coding: utf-8 -*-
"""Frescor do resumo — pred 7d + EHF → IRM → RIT → compostos.

Garante a mesma ordem usada no enrich operacional antes de alertas, boletim e painel.
Não altera a regra de ``nivel`` operacional; apenas anexa/reaplica ``nivel_predicao_7d``
a partir de ``predicao_calor_7d_municipal_v6`` quando disponível.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _merge_predicao_no_resumo(work: pd.DataFrame) -> pd.DataFrame:
    """Anexa colunas de predição ~7d no resumo (join por cod_ibge)."""
    try:
        from sisclima.core.db import read_table, table_exists
        from sisclima.engines.boletim_el_nino.snapshot import merge_predicao_7d

        if not table_exists("predicao_calor_7d_municipal_v6"):
            return work
        pred = read_table("predicao_calor_7d_municipal_v6")
        if pred is None or pred.empty:
            return work
        return merge_predicao_7d(work, pred)
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor: merge pred 7d falhou: %s", exc)
        return work


def refresh_resumo_multirisco(
    resumo: pd.DataFrame | None,
    *,
    inject_ehf: bool = True,
    merge_predicao: bool = True,
    persist: bool = False,
) -> pd.DataFrame:
    """Aplica pred 7d (opcional) → EHF → IRM → RIT → compostos no resumo.

    Parameters
    ----------
    inject_ehf
        Junta EHF GeoCalor antes do RIT (recomendado para alertas/boletim).
    merge_predicao
        Anexa ``nivel_predicao_7d`` e features da tabela de predição.
    persist
        Se True, grava ``resumo_municipal_atual`` após o enrich.
    """
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    work = resumo.copy()
    meta: dict[str, Any] = {"ok": True, "steps": []}

    try:
        from sisclima.ingestion.regionais_ses import aplicar_regionais_ses

        work = aplicar_regionais_ses(work)
        meta["steps"].append("regionais_ses")
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor: regionais SES falhou: %s", exc)

    if merge_predicao:
        before = "nivel_predicao_7d" in work.columns
        work = _merge_predicao_no_resumo(work)
        if "nivel_predicao_7d" in work.columns:
            meta["steps"].append("predicao_7d")
        elif before:
            meta["steps"].append("predicao_7d_kept")

    if inject_ehf:
        try:
            from sisclima.engines.ehf_geocalor import inject_ehf_geocalor

            # data_ref=None → snapshot ancora em ontem (observado), não no max forecast
            work = inject_ehf_geocalor(work, prefer_geocalor=True, data_ref=None)
            meta["steps"].append("ehf")
        except Exception as exc:  # noqa: BLE001
            log.warning("Frescor: inject EHF falhou: %s", exc)

    try:
        from sisclima.engines.indice_resiliencia_municipal import enrich_indice_resiliencia

        work = enrich_indice_resiliencia(work)
        meta["steps"].append("irm")
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor: IRM falhou: %s", exc)

    try:
        from sisclima.engines.rit_multirisco import enrich_rit_multirisco

        work = enrich_rit_multirisco(work)
        meta["steps"].append("rit")
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor: RIT falhou: %s", exc)

    try:
        from sisclima.engines.indicadores_compostos import enrich_indicadores_compostos

        work = enrich_indicadores_compostos(work)
        meta["steps"].append("compostos")
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor: compostos falharam: %s", exc)

    if persist:
        try:
            from sisclima.core.db import write_df

            write_df(work, "resumo_municipal_atual")
            meta["persisted"] = True
        except Exception as exc:  # noqa: BLE001
            log.warning("Frescor: persistência falhou: %s", exc)
            meta["persisted"] = False

    work.attrs["multirisco_frescor"] = meta
    return work


def load_resumo_fresco(*, persist: bool = False) -> pd.DataFrame:
    """Lê ``resumo_municipal_atual`` e reaplica pred/IRM/RIT/compostos (+ EHF)."""
    from sisclima.core.db import read_table, table_exists

    if not table_exists("resumo_municipal_atual"):
        return pd.DataFrame()
    base = read_table("resumo_municipal_atual")
    return refresh_resumo_multirisco(base, inject_ehf=True, merge_predicao=True, persist=persist)


def sync_resumo_para_consumidores(*, persist: bool = True) -> dict[str, Any]:
    """Sincroniza resumo fresco para painel, alertas e boletim (sem ETL completa)."""
    out = load_resumo_fresco(persist=persist)
    meta = dict(out.attrs.get("multirisco_frescor") or {})
    meta["n_municipios"] = 0 if out is None or out.empty else len(out)
    meta["tem_nivel"] = bool(out is not None and not out.empty and "nivel" in out.columns)
    meta["tem_pred_7d"] = bool(out is not None and not out.empty and "nivel_predicao_7d" in out.columns)
    meta["tem_irm"] = bool(
        out is not None and not out.empty and "indice_resiliencia_municipal_0_100" in out.columns
    )
    meta["tem_rit"] = bool(out is not None and not out.empty and "rit_0_100" in out.columns)
    if out is not None and not out.empty and "nivel_predicao_7d" in out.columns:
        meta["n_pred_7d"] = int(out["nivel_predicao_7d"].notna().sum())
    if out is not None and not out.empty and "indice_resiliencia_municipal_0_100" in out.columns:
        meta["n_irm"] = int(pd.to_numeric(out["indice_resiliencia_municipal_0_100"], errors="coerce").notna().sum())
    return meta
