# -*- coding: utf-8 -*-
"""Figuras do boletim: série climática, gráficos de classe e mapa de vulneráveis."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

LEVEL_ORDER = ("verde", "amarela", "laranja", "vermelha", "roxa", "cinza")
LEVEL_COLOR = {
    "verde": "#16803c",
    "amarela": "#e6b800",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#5b21b6",
    "cinza": "#6b7280",
}


def _save(fig, path: Path) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao salvar figura %s: %s", path, exc)
        return None
    finally:
        try:
            import matplotlib.pyplot as plt

            plt.close(fig)
        except Exception:  # noqa: BLE001
            pass


def export_serie_climatica(
    out_dir: Path,
    *,
    ano_inicio: int = 2020,
) -> dict[str, Any]:
    """Série mensal estadual de Tmáx (média e máxima) desde ano_inicio ou início disponível."""
    from sisclima.engines.serie_historica_ambiente import serie_clima_estado

    clima = serie_clima_estado()
    meta: dict[str, Any] = {"disponivel": False, "path": None, "inicio": None, "fim": None}
    if clima is None or clima.empty or "data" not in clima.columns:
        return meta
    df = clima.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])
    df = df[df["data"].dt.year >= ano_inicio]
    if df.empty:
        return meta
    df["ym"] = df["data"].dt.to_period("M").dt.to_timestamp()
    col_med = "tmax_media" if "tmax_media" in df.columns else None
    col_max = "tmax_max" if "tmax_max" in df.columns else None
    if not col_med and "tmax" in df.columns:
        col_med = "tmax"
    if not col_med:
        return meta
    agg: dict[str, tuple[str, str]] = {"tmax_med": (col_med, "mean")}
    if col_max:
        agg["tmax_ext"] = (col_max, "max")
    g = df.groupby("ym", as_index=False).agg(**agg)
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível para série climática: %s", exc)
        return meta

    fig, ax = plt.subplots(figsize=(9.2, 3.6), dpi=160)
    ax.plot(g["ym"], g["tmax_med"], color="#1351B4", lw=1.8, label="Tmáx média estadual (°C)")
    if "tmax_ext" in g.columns:
        ax.plot(g["ym"], g["tmax_ext"], color="#dc2626", lw=1.2, alpha=0.85, label="Tmáx máxima estadual (°C)")
    ax.axhline(37, color="#d97706", ls="--", lw=1, label="Referência operacional 37 °C")
    ax.set_ylabel("Temperatura (°C)")
    ax.set_title("Série climática operacional — Tmáx estadual (mensal)")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    path = out_dir / "serie_climatica_tmax.png"
    saved = _save(fig, path)
    if not saved:
        return meta
    meta.update(
        {
            "disponivel": True,
            "path": saved,
            "inicio": str(df["data"].min().date()),
            "fim": str(df["data"].max().date()),
            "n_meses": int(len(g)),
        }
    )
    return meta


def export_grafico_classes(
    niveis: dict[str, Any] | None,
    out_dir: Path,
    *,
    titulo: str = "Distribuição municipal por classe ARARAS",
    nome: str = "grafico_classes_araras.png",
) -> dict[str, Any]:
    counts = {k: int((niveis or {}).get(k) or 0) for k in LEVEL_ORDER}
    labels = [k for k, v in counts.items() if v > 0]
    vals = [counts[k] for k in labels]
    if not vals:
        return {"disponivel": False}
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}
    fig, ax = plt.subplots(figsize=(7.2, 3.4), dpi=160)
    colors = [LEVEL_COLOR.get(k, "#999") for k in labels]
    bars = ax.bar([k.title() for k in labels], vals, color=colors, edgecolor="#1a1a1a", linewidth=0.4)
    ax.bar_label(bars, padding=2, fontsize=8)
    ax.set_ylabel("Municípios")
    ax.set_title(titulo)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis="y", alpha=0.25)
    path = out_dir / nome
    saved = _save(fig, path)
    return {"disponivel": bool(saved), "path": saved, "counts": counts}


def export_grafico_esus_por_classe(
    por_classe: list[dict[str, Any]] | None,
    out_dir: Path,
) -> dict[str, Any]:
    """Barras de idosos/gestantes por classe — prefere agregação direta da tabela municipal."""
    from sisclima.core.db import read_table

    rows = [r for r in (por_classe or []) if isinstance(r, dict)]
    df = read_table("ops_esus_aps_municipal")
    if df is not None and not df.empty and "classe_araras" in df.columns:
        work = df.copy()
        work["classe"] = work["classe_araras"].astype(str).str.lower().str.strip()
        for c in ("idoso_60mais", "gestante"):
            if c not in work.columns:
                work[c] = 0
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)
        mun_col = next((c for c in ("cod_ibge", "codigo_ibge", "ibge", "municipio") if c in work.columns), None)
        if mun_col:
            grp = (
                work.groupby("classe", as_index=False)
                .agg(
                    idoso_60mais=("idoso_60mais", "sum"),
                    gestante=("gestante", "sum"),
                    municipios=(mun_col, "nunique"),
                )
            )
        else:
            grp = (
                work.groupby("classe", as_index=False)
                .agg(idoso_60mais=("idoso_60mais", "sum"), gestante=("gestante", "sum"))
            )
        rows = grp.to_dict(orient="records")
    if not rows:
        return {"disponivel": False}
    ordem = [c for c in LEVEL_ORDER if any(str(r.get("classe") or "").lower() == c for r in rows)]
    if not ordem:
        ordem = [str(r.get("classe") or "").lower() for r in rows]
    idx = {c: i for i, c in enumerate(ordem)}
    rows = sorted(rows, key=lambda r: idx.get(str(r.get("classe") or "").lower(), 99))
    labels = [str(r.get("classe") or "—").title() for r in rows]
    idosos = [int(r.get("idoso_60mais") or 0) for r in rows]
    gest = [int(r.get("gestante") or 0) for r in rows]
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}
    x = np.arange(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(8.0, 3.6), dpi=160)
    ax.bar(x - w / 2, idosos, w, color="#1351B4", label="Idosos 60+ (cadastro)")
    ax.bar(x + w / 2, gest, w, color="#e87722", label="Gestantes (cadastro)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Pessoas (cadastro APS)")
    ax.set_title("Vulneráveis na APS por classe ARARAS")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis="y", alpha=0.25)
    path = out_dir / "grafico_esus_vulneraveis_classe.png"
    saved = _save(fig, path)
    return {"disponivel": bool(saved), "path": saved}


def export_mapa_vulneraveis(
    resumo: pd.DataFrame,
    out_dir: Path,
    *,
    data_ref: str = "",
    cmc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mapa: classe ARARAS + aldeias/quilombos + idosos/gestantes (e-SUS) em municípios críticos."""
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {"disponivel": False, "path": None}
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from sisclima.core.db import read_table
        from sisclima.engines.boletim_el_nino.classificacao import build_current_municipal_classification
        from sisclima.engines.boletim_el_nino.maps import LEVEL_COLOR_MAP, LEVEL_ORDER as LO, _load_gdf, _prep_merge
        from sisclima.engines.boletim_el_nino.territorios import (
            _centroides_municipais,
            _coords_plot,
            _load_vigibarragens,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Mapa vulneráveis indisponível: %s", exc)
        return {**meta, "motivo": str(exc)}

    if cmc is None or not cmc.get("disponivel"):
        cmc = build_current_municipal_classification(resumo, data_hora_rodada=data_ref or None)
    if not cmc.get("disponivel"):
        return {**meta, "motivo": "classificação indisponível"}
    merged = _prep_merge(_load_gdf(), cmc.get("resumo_for_maps") if cmc.get("resumo_for_maps") is not None else resumo)
    if merged is None:
        return {**meta, "motivo": "malha indisponível"}

    esus = read_table("ops_esus_aps_municipal")
    if esus is not None and not esus.empty:
        e = esus.copy()
        ibge_col = next((c for c in ("cod_ibge", "codigo_ibge", "ibge", "cod6") if c in e.columns), None)
        if ibge_col:
            e["cod6"] = e[ibge_col].astype(str).str.replace(r"\D", "", regex=True).str[:6]
            keep = [c for c in ("idoso_60mais", "gestante", "asma", "acamado") if c in e.columns]
            e = e[["cod6"] + keep]
            m = merged.copy()
            src = "cod_ibge" if "cod_ibge" in m.columns else next(
                (c for c in ("codigo_ibge", "CD_MUN", "cod6") if c in m.columns), None
            )
            if src:
                m["cod6"] = m[src].astype(str).str.replace(r"\D", "", regex=True).str[:6]
                merged = m.merge(e, on="cod6", how="left")
    for c in ("idoso_60mais", "gestante"):
        if c not in merged.columns:
            merged[c] = 0

    pts, _mun = _load_vigibarragens()
    centroids = _centroides_municipais(merged)
    ald, qui, _ = _coords_plot(pts, centroids)

    fig, ax = plt.subplots(figsize=(8.8, 8.8), dpi=160)
    for nivel in LO:
        sub = merged[merged["nivel"] == nivel]
        if not sub.empty:
            sub.plot(ax=ax, color=LEVEL_COLOR_MAP.get(nivel, "#ccc"), edgecolor="#4a4a4a", linewidth=0.25, alpha=0.7)

    crit = merged[merged["nivel"].isin(["vermelha", "roxa"])].copy()
    if not crit.empty and "geometry" in crit.columns:
        crit["cx"] = crit.geometry.centroid.x
        crit["cy"] = crit.geometry.centroid.y
        idoso = pd.to_numeric(crit.get("idoso_60mais"), errors="coerce").fillna(0)
        gest = pd.to_numeric(crit.get("gestante"), errors="coerce").fillna(0)
        # bolhas proporcionais (escala visual, não incidência)
        s_id = (20 + 80 * (idoso / max(float(idoso.max()), 1.0))).clip(20, 120)
        s_ge = (16 + 60 * (gest / max(float(gest.max()), 1.0))).clip(16, 90)
        ax.scatter(crit["cx"], crit["cy"], s=s_id, c="#1351B4", alpha=0.35, edgecolors="#0b2c5c", linewidths=0.4, zorder=4)
        ax.scatter(crit["cx"], crit["cy"], s=s_ge, c="#e87722", alpha=0.4, edgecolors="#9a4a0c", linewidths=0.4, zorder=5)

    if not ald.empty:
        ax.scatter(ald["lon"], ald["lat"], s=36, c="#00E5FF", marker="^", edgecolors="#003344", linewidths=0.6, zorder=6)
    if not qui.empty:
        ax.scatter(qui["lon"], qui["lat"], s=42, c="#FFD600", marker="o", edgecolors="#1a1a1a", linewidths=0.7, zorder=7)

    handles = [
        mpatches.Patch(color=LEVEL_COLOR_MAP[n], label=n.title())
        for n in LO
        if n in set(merged["nivel"].astype(str).str.lower())
    ]
    handles.extend(
        [
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#1351B4", markersize=9, label="Idosos 60+ (APS, críticos)"),
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#e87722", markersize=8, label="Gestantes (APS, críticos)"),
            plt.Line2D([0], [0], marker="^", color="w", markerfacecolor="#00E5FF", markeredgecolor="#003344", markersize=8, label="Aldeia indígena"),
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#FFD600", markeredgecolor="#1a1a1a", markersize=8, label="Quilombo / presença municipal"),
        ]
    )
    ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.92)
    ax.set_axis_off()
    ax.set_title("Classificação ARARAS e populações vulneráveis (indígenas, quilombolas, idosos e gestantes)")
    path = out_dir / "mapa_vulneraveis_araras.png"
    saved = _save(fig, path)
    if not saved:
        return meta
    meta.update({"disponivel": True, "path": saved, "n_criticos": int(len(crit))})
    return meta


def relpath_fig(path: str | Path | None, dest: Path) -> str:
    if not path:
        return ""
    p = Path(str(path))
    try:
        return p.relative_to(dest).as_posix()
    except ValueError:
        return p.name
