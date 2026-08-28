# -*- coding: utf-8 -*-
"""Relatório semanal El Niño para a sala de situação CIEVS-MT.

Ponto de entrada legado — implementação modular em ``sisclima.engines.boletim_el_nino``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sisclima.core.config import ROOT
from sisclima.engines.boletim_el_nino.builder import build_boletim_semanal, save_boletim
from sisclima.engines.boletim_el_nino.cenario import load_cenario_oficial, semana_iso, semana_sinan
from sisclima.engines.boletim_el_nino.documento import format_markdown
from sisclima.engines.boletim_el_nino.snapshot import snapshot_operacional

OUT_DIR = ROOT / "docs" / "apresentacoes"
CENARIO_PATH = ROOT / "config" / "painel_el_nino.yaml"


def _refresh_fire_metrics_if_stale(resumo):
    """Reconcilia focos AQUA_M-T e detecções multi-satélite antes do boletim."""
    import pandas as pd

    from sisclima.core.config import as_bool, env
    from sisclima.core.db import write_df
    from sisclima.ingestion.inpe_queimadas import load_queimadas_municipais

    if resumo is None or resumo.empty or not as_bool(env("USE_INPE_QUEIMADAS", "true"), True):
        return resumo

    focos = pd.to_numeric(resumo["focos_queimadas_7d"], errors="coerce") if "focos_queimadas_7d" in resumo.columns else pd.Series(dtype=float)
    det = pd.to_numeric(resumo["deteccoes_queimadas_7d"], errors="coerce") if "deteccoes_queimadas_7d" in resumo.columns else pd.Series(dtype=float)
    focos_sum = float(focos.sum()) if focos.notna().any() else 0.0
    det_sum = float(det.sum()) if det is not None and det.notna().any() else 0.0
    stale = (
        "deteccoes_queimadas_7d" not in resumo.columns
        or det.notna().sum() == 0
        or (focos_sum > 0 and det_sum > 0 and abs(focos_sum - det_sum) < 1.0)
        or focos_sum > 5000
    )
    if not stale:
        return resumo

    q = load_queimadas_municipais()
    if q is None or q.empty or "cod_ibge" not in q.columns:
        return resumo
    write_df(q, "queimadas_focos_municipal")
    qcols = [
        c
        for c in (
            "cod_ibge",
            "focos_queimadas_24h",
            "focos_queimadas_7d",
            "deteccoes_queimadas_24h",
            "deteccoes_queimadas_7d",
            "frp_queimadas_7d",
            "nivel_queimadas",
            "dias_sem_chuva_max",
            "satelite_referencia",
        )
        if c in q.columns
    ]
    qm = q[qcols].drop_duplicates("cod_ibge")
    out = resumo.copy()
    out["cod_ibge"] = out["cod_ibge"].astype(str)
    qm["cod_ibge"] = qm["cod_ibge"].astype(str)
    for col in qcols:
        if col != "cod_ibge" and col in out.columns:
            out = out.drop(columns=[col])
    out = out.merge(qm, on="cod_ibge", how="left")
    if out.empty or "nivel" not in out.columns or out["nivel"].notna().sum() == 0:
        return resumo
    write_df(out, "resumo_municipal_atual")
    return out

__all__ = [
    "build_boletim_semanal",
    "save_boletim",
    "format_markdown",
    "load_cenario_oficial",
    "semana_iso",
    "semana_sinan",
    "snapshot_operacional",
    "CENARIO_PATH",
    "OUT_DIR",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Relatório semanal El Niño — sala de situação")
    p.add_argument("--out-dir", default=None, help="Pasta de saída (padrão docs/apresentacoes)")
    p.add_argument("--publico", action="store_true", help="Omite pauta interna da sala")
    p.add_argument("--no-dw", action="store_true", help="Não consultar DW epidemiológico")
    args = p.parse_args(argv)
    from sisclima.core.db import read_table

    resumo = read_table("resumo_municipal_atual")
    resumo = _refresh_fire_metrics_if_stale(resumo)
    out = Path(args.out_dir) if args.out_dir else None
    payload = build_boletim_semanal(resumo, publico=bool(args.publico), try_dw=not args.no_dw, out_dir=out)
    path = save_boletim(payload, out)
    qa = payload.get("qa") or {}
    print(path)
    if qa.get("log"):
        print(qa["log"])
    if qa.get("MAP3_BLOQUEIA_APRESENTAVEL") or any(
        str(i).startswith("MAP3_") for i in (qa.get("issues") or [])
    ):
        print("BLOQUEIO DE PUBLICAÇÃO: QA do Mapa 3 falhou — não gerar versão apresentável.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
