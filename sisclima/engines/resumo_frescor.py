# -*- coding: utf-8 -*-
"""Frescor do resumo multirisco — IRM → RIT → compostos.

Garante a mesma ordem usada no enrich operacional antes de alertas, boletim e painel.
Não altera ``nivel`` nem ``nivel_predicao_7d``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def refresh_resumo_multirisco(
    resumo: pd.DataFrame | None,
    *,
    inject_ehf: bool = True,
    persist: bool = False,
) -> pd.DataFrame:
    """Aplica EHF (opcional) → IRM → RIT → indicadores compostos no resumo.

    Parameters
    ----------
    inject_ehf
        Junta EHF GeoCalor antes do RIT (recomendado para alertas/boletim).
    persist
        Se True, grava ``resumo_municipal_atual`` após o enrich.
    """
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    work = resumo.copy()
    meta: dict[str, Any] = {"ok": True, "steps": []}

    if inject_ehf:
        try:
            from sisclima.engines.ehf_geocalor import inject_ehf_geocalor

            work = inject_ehf_geocalor(work, prefer_geocalor=True)
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
    """Lê ``resumo_municipal_atual`` e reaplica IRM/RIT/compostos (+ EHF)."""
    from sisclima.core.db import read_table, table_exists

    if not table_exists("resumo_municipal_atual"):
        return pd.DataFrame()
    base = read_table("resumo_municipal_atual")
    return refresh_resumo_multirisco(base, inject_ehf=True, persist=persist)
