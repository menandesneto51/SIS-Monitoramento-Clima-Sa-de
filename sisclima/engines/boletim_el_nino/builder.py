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
from sisclima.engines.boletim_el_nino.classificacao import build_current_municipal_classification
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
        classes_araras=snap.get("niveis") or {},
        n_municipios=snap.get("n_municipios"),
    )
    blob_alerta = " ".join(
        str(alertas.get(k) or "")
        for k in ("inmet_sintese_md", "inmet_vigentes_md", "inmet_futuros_md", "cemaden_md")
    ).lower()
    snap["evidencia_inundacao"] = bool((snap.get("hydro_facts") or {}).get("flood_risk_high")) or any(
        tok in blob_alerta
        for tok in ("chuva intensa", "inund", "enxurr", "alagamento", "cheia", "tempestade severa")
    )
    estoque_saf = build_estoque_saf_section(estoque_df)

    assets_dir = dest / f"_assets_{semana['rotulo'].replace(' ', '_').replace('/', '-')}"
    data_ref = str(snap.get("data_referencia") or "")
    cmc = build_current_municipal_classification(resumo_enriched, data_hora_rodada=data_ref or None)
    snap["CURRENT_MUNICIPAL_CLASSIFICATION"] = {
        "disponivel": cmc.get("disponivel"),
        "n": cmc.get("n"),
        "counts_atual": cmc.get("counts_atual"),
        "counts_proj": cmc.get("counts_proj"),
        "classification_hash": cmc.get("classification_hash"),
        "data_hora_rodada": cmc.get("data_hora_rodada"),
        "MAP_REGEN_REQUIRED": True,
    }
    snap["REPORT_FACTS"] = {
        "current_total": cmc.get("n"),
        "current_classes": cmc.get("counts_atual"),
        "projected_classes": cmc.get("counts_proj"),
        "classification_hash": cmc.get("classification_hash"),
        "n_municipios": snap.get("n_municipios"),
        "niveis": snap.get("niveis"),
        "niveis_projecao_7d": snap.get("niveis_projecao_7d"),
        "delta_projecao": snap.get("delta_projecao"),
        "delta_n_comparavel": snap.get("delta_n_comparavel"),
        "hydro_facts": snap.get("hydro_facts"),
    }
    maps = export_maps(
        resumo_enriched,
        assets_dir,
        data_ref=data_ref,
        cmc=cmc,
    )
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
                dc = maps["delta_counts"]
                snap["n_agravadores"] = int(dc.get("aumento_1") or 0) + int(dc.get("aumento_2plus") or 0)
            n_tot = snap.get("n_municipios")
            if n_tot is not None:
                snap["delta_sem_pareamento"] = max(0, int(n_tot) - int(maps["delta_n"]))
        if maps.get("map1_counts"):
            rf = snap.setdefault("REPORT_FACTS", {})
            rf["map1_classes"] = maps["map1_counts"]
            rf["map1_classification_hash"] = maps.get("classification_hash")

    prontidao = compute_prontidao(resumo_enriched)
    snap["prontidao"] = prontidao
    territorios = build_territorios(
        resumo_enriched,
        assets_dir=assets_dir,
        data_ref=data_ref,
        cmc=cmc,
    )
    mapa_terr = (territorios.get("mapa") or {})
    if mapa_terr.get("disponivel") and mapa_terr.get("mapa_territorios"):
        p = Path(str(mapa_terr["mapa_territorios"]))
        try:
            maps["mapa_territorios"] = p.relative_to(dest).as_posix()
        except ValueError:
            maps["mapa_territorios"] = p.name
        maps["territorio_disponivel"] = True
        maps["mapa3_qa"] = mapa_terr.get("qa") or {}
        maps["mapa3_ok_publicacao"] = bool(mapa_terr.get("ok_publicacao"))
        rf = snap.setdefault("REPORT_FACTS", {})
        rf["map3_classes"] = mapa_terr.get("counts_atual") or (mapa_terr.get("qa") or {}).get("map3_counts")
        rf["map3_classification_hash"] = mapa_terr.get("classification_hash")
        rf["MAP3_QA"] = mapa_terr.get("qa") or {}
    else:
        maps["territorio_disponivel"] = False
        maps["mapa3_ok_publicacao"] = False
        maps["mapa3_qa"] = mapa_terr.get("qa") or {}

    snap["rodada_em_pt"] = semana.get("gerado_em_pt") or semana.get("gerado_em")
    snap["determinantes_projecao_md"] = quadro_determinantes_projecao(
        resumo_enriched, predicao, snap=snap
    )

    try:
        from sisclima.engines.serie_historica_ambiente import resumo_serie_ambiente_boletim
        from sisclima.engines.obitos_clima_contexto import resumo_obitos_clima

        amb = resumo_serie_ambiente_boletim()
        snap["serie_ambiente_md"] = str(amb.get("markdown") or "")
        snap["serie_ambiente_ok"] = bool(amb.get("ok"))
        ob = resumo_obitos_clima()
        snap["obitos_clima_md"] = str(ob.get("markdown_boletim") or "")
        snap["obitos_metodologia_md"] = str(ob.get("metodologia_md") or "")
        snap["obitos_clima_ok"] = bool(ob.get("ok"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Série ambiental / óbitos clima indisponíveis no boletim: %s", exc)
        snap.setdefault("serie_ambiente_md", "")
        snap.setdefault("obitos_clima_md", "")
        snap.setdefault("obitos_metodologia_md", "")

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
            "maps": maps,
            "cmc": cmc,
        },
    )
    # Bloqueio de publicação do Mapa 3
    m3qa = mapa_terr.get("qa") or {}
    if not mapa_terr.get("ok_publicacao"):
        for flag in (
            "MAP3_STALE_ERROR",
            "MAP3_CLASS_DISTRIBUTION_ERROR",
            "MAP3_FILE_CREATED_THIS_RUN",
            "MAP3_CLASSIFICATION_HASH_MATCH",
            "MAP3_MUNICIPAL_DIFF_COUNT",
        ):
            if flag in m3qa:
                qa.setdefault("issues", []).append(f"{flag}={m3qa.get(flag)}")
        qa["ok"] = False
        qa["MAP3_BLOQUEIA_APRESENTAVEL"] = True

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
        "cmc": cmc,
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
