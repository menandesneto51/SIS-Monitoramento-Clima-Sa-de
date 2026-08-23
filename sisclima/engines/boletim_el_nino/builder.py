# -*- coding: utf-8 -*-
"""Orquestração da geração do boletim semanal El Niño."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.alertas_oficiais import build_alertas_oficiais
from sisclima.engines.boletim_el_nino.cenario import load_cenario_oficial, semana_iso
from sisclima.engines.boletim_el_nino.determinantes_projecao import quadro_determinantes_projecao
from sisclima.engines.boletim_el_nino.documento import format_markdown
from sisclima.engines.boletim_el_nino.estoque_saf import build_estoque_saf_section
from sisclima.engines.boletim_el_nino.maps import export_maps
from sisclima.engines.boletim_el_nino.prontidao import compute_prontidao
from sisclima.engines.boletim_el_nino.qa import run_qa
from sisclima.engines.boletim_el_nino.referencias import format_referencias_bibliograficas, refs_usadas_boletim
from sisclima.engines.boletim_el_nino.snapshot import merge_predicao_7d, snapshot_operacional
from sisclima.engines.boletim_el_nino.territorios import build_territorios
from sisclima.engines.monitoramento_agravos_el_nino import aggregate_agravos_el_nino, merge_agravos_monitorados

log = get_logger(__name__)

OUT_DIR = ROOT / "docs" / "apresentacoes"


def build_boletim_semanal(
    resumo: pd.DataFrame,
    *,
    hoje: date | None = None,
    publico: bool = False,
    try_dw: bool = True,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    cenario = load_cenario_oficial()
    semana = semana_iso(hoje)
    dest = out_dir or OUT_DIR

    predicao = None
    try:
        from sisclima.core.db import read_table

        predicao = read_table("predicao_calor_7d_municipal_v6")
    except Exception as exc:  # noqa: BLE001
        log.warning("Predição 7d indisponível: %s", exc)

    resumo_enriched = merge_predicao_7d(resumo, predicao)
    snap = snapshot_operacional(resumo_enriched)
    ref = hoje or date.today()

    try:
        dw_agravos = aggregate_agravos_el_nino(ref=ref, try_dw=try_dw)
    except Exception as exc:  # noqa: BLE001
        log.warning("Agregação DW agravos El Niño falhou: %s", exc)
        dw_agravos = None
    snap["agravos_monitorados"] = merge_agravos_monitorados(
        snap.get("agravos_monitorados") or {},
        dw_agravos,
    )

    alertas_df = None
    cemaden_df = None
    titan_df = None
    estoque_df = None
    try:
        from sisclima.core.db import read_table

        alertas_df = read_table("inmet_alertas")
        cemaden_df = read_table("cemaden_alertas")
        titan_df = read_table("alerta_integrado_sis_titan")
        estoque_df = read_table("ops_estoque_autonomia")
    except Exception as exc:  # noqa: BLE001
        log.warning("Tabelas operacionais indisponíveis: %s", exc)

    alertas = build_alertas_oficiais(
        semana,
        hoje=ref,
        consulta_em=datetime.now(),
        inmet_db=alertas_df,
        cemaden_db=cemaden_df,
        titan_db=titan_df,
        fetch_live=True,
    )
    estoque_saf = build_estoque_saf_section(estoque_df)

    assets_dir = dest / f"_assets_{semana['rotulo'].replace(' ', '_').replace('/', '-')}"
    maps = export_maps(resumo_enriched, assets_dir, data_ref=str(snap.get("data_referencia") or ""))
    if maps.get("disponivel"):
        for key in ("mapa_atual_projecao", "mapa_delta"):
            if maps.get(key):
                p = Path(str(maps[key]))
                try:
                    maps[key] = p.relative_to(dest).as_posix()
                except ValueError:
                    maps[key] = p.name
        # Alinha denominador textual ao universo cartográfico (malha com N polígonos)
        if maps.get("delta_n") is not None:
            snap["delta_n_comparavel"] = int(maps["delta_n"])
            if maps.get("delta_counts"):
                snap["delta_projecao"] = dict(maps["delta_counts"])
            n_tot = snap.get("n_municipios")
            if n_tot is not None:
                snap["delta_sem_pareamento"] = max(0, int(n_tot) - int(maps["delta_n"]))

    prontidao = compute_prontidao(resumo_enriched)
    snap["prontidao"] = prontidao
    territorios = build_territorios(
        resumo_enriched,
        assets_dir=assets_dir,
        data_ref=str(snap.get("data_referencia") or ""),
    )
    mapa_terr = (territorios.get("mapa") or {})
    if mapa_terr.get("disponivel") and mapa_terr.get("mapa_territorios"):
        p = Path(str(mapa_terr["mapa_territorios"]))
        try:
            maps["mapa_territorios"] = p.relative_to(dest).as_posix()
        except ValueError:
            maps["mapa_territorios"] = p.name
        maps["territorio_disponivel"] = True
    else:
        maps["territorio_disponivel"] = False

    snap["determinantes_projecao_md"] = quadro_determinantes_projecao(
        resumo_enriched, predicao, snap=snap
    )

    refs_abnt = format_referencias_bibliograficas(ref_ids=refs_usadas_boletim(), acesso_em=ref)
    md = format_markdown(
        cenario,
        semana,
        snap,
        alertas=alertas,
        estoque_saf=estoque_saf,
        maps=maps,
        prontidao=prontidao,
        territorios=territorios,
        referencias=refs_abnt,
        publico=publico,
    )
    qa = run_qa(
        md,
        snap,
        refs=refs_abnt,
        extra={
            "territorios": territorios,
            "prontidao": prontidao,
            "alertas": alertas,
            "estoque_saf": estoque_saf,
        },
    )

    return {
        "semana": semana,
        "cenario": cenario,
        "snapshot": snap,
        "inmet": alertas,
        "alertas": alertas,
        "estoque_saf": estoque_saf,
        "referencias": refs_abnt,
        "maps": maps,
        "prontidao": prontidao,
        "territorios": territorios,
        "qa": qa,
        "markdown": md,
        "arquivo": f"Boletim_ElNino_{semana['rotulo'].replace(' ', '_').replace('/', '-')}.md",
    }


def save_boletim(payload: dict[str, Any], out_dir: Path | None = None) -> Path:
    dest_dir = out_dir or OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / str(payload.get("arquivo") or "Boletim_ElNino_semanal.md")
    path.write_text(str(payload.get("markdown") or ""), encoding="utf-8")
    qa = payload.get("qa") or {}
    if qa.get("log"):
        qa_path = path.with_suffix(".qa.log")
        qa_path.write_text(str(qa["log"]), encoding="utf-8")
    return path
