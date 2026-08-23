# -*- coding: utf-8 -*-
"""Mapas estáticos atual × projeção 7d para o boletim."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]
LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#e6b800",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#5b21b6",
}


def normalize_cod_ibge(series):
    import pandas as pd

    return series.astype(str).str.extract(r"(\d{7})", expand=False)


def geojson_file_candidates():
    from pathlib import Path

    from sisclima.core.config import ROOT

    rel = [
        Path("data/processed/municipios_mt_2025_simplificado.geojson"),
        Path("data/processed/municipios_mt_2025.geojson"),
        Path("data/raw/ibge/malha_municipios_mt.geojson"),
        Path("data/geo/municipios_mt/MT_Municipios_2025.geojson"),
    ]
    return [ROOT / p for p in rel]

_NIVEL_LABEL = {
    "verde": "Verde",
    "amarela": "Amarelo",
    "laranja": "Laranja",
    "vermelha": "Vermelho",
    "roxa": "Roxo",
    "cinza": "Sem classificação",
}


def _load_gdf():
    try:
        import geopandas as gpd
    except ImportError:
        log.warning("geopandas indisponível para mapas do boletim")
        return None

    for path in geojson_file_candidates():
        if path.exists():
            try:
                return gpd.read_file(path)
            except Exception as exc:  # noqa: BLE001
                log.warning("Falha ao ler geojson %s: %s", path, exc)
    return None


def _prep_merge(gdf, resumo: pd.DataFrame) -> pd.DataFrame | None:
    if gdf is None or resumo is None or resumo.empty:
        return None
    cod_col = next(
        (c for c in ("CD_MUN", "cod_ibge", "codarea", "GEOCODIGO", "codarea") if c in gdf.columns),
        None,
    )
    if cod_col is None:
        return None
    g = gdf.copy()
    g["_cod"] = normalize_cod_ibge(g[cod_col])
    r = resumo.copy()
    if "cod_ibge" not in r.columns:
        return None
    r["_cod"] = normalize_cod_ibge(r["cod_ibge"])
    merged = g.merge(r, on="_cod", how="left")
    for col in ("nivel", "nivel_predicao_7d"):
        if col in merged.columns:
            merged[col] = merged[col].astype(str).str.lower().str.strip()
            merged.loc[~merged[col].isin(LEVEL_ORDER), col] = "cinza"
        else:
            merged[col] = "cinza"
    return merged


def _plot_panel(ax, gdf, col: str, panel_label: str) -> None:
    import matplotlib.patches as mpatches

    for nivel in LEVEL_ORDER:
        sub = gdf[gdf[col] == nivel]
        color = LEVEL_COLOR_MAP.get(nivel, "#cccccc")
        if not sub.empty:
            sub.plot(ax=ax, color=color, edgecolor="#666666", linewidth=0.2)
    ax.set_axis_off()
    # Apenas rótulo (a)/(b) — título oficial fica no markdown acima da figura
    ax.text(0.02, 0.98, panel_label, transform=ax.transAxes, fontsize=11, fontweight="bold", va="top")
    handles = [
        mpatches.Patch(color=LEVEL_COLOR_MAP.get(k, "#ccc"), label=_NIVEL_LABEL.get(k, k))
        for k in ["verde", "amarela", "laranja", "vermelha", "roxa"]
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=7, frameon=True)


def export_maps(resumo: pd.DataFrame, out_dir: Path, *, data_ref: str = "") -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    gdf_base = _load_gdf()
    merged = _prep_merge(gdf_base, resumo)
    if merged is None:
        return {"disponivel": False, "motivo": "Malha municipal ou resumo indisponível."}

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return {"disponivel": False, "motivo": "matplotlib indisponível."}

    fig, axes = plt.subplots(1, 2, figsize=(12, 6), dpi=150)
    _plot_panel(axes[0], merged, "nivel", "(a)")
    _plot_panel(axes[1], merged, "nivel_predicao_7d", "(b)")
    fig.tight_layout()
    path_ab = out_dir / "mapa_atual_projecao_7d.png"
    fig.savefig(path_ab, bbox_inches="tight")
    plt.close(fig)

    # Mapa delta
    def _delta_row(row) -> str:
        from sisclima.engines.stages import STAGE_ORDER

        a = STAGE_ORDER.get(str(row.get("nivel", "")).lower().strip())
        p = STAGE_ORDER.get(str(row.get("nivel_predicao_7d", "")).lower().strip())
        if a is None or p is None or a < 0 or p < 0:
            return "indisponivel"
        d = p - a
        if d > 1:
            return "aumento_2plus"
        if d == 1:
            return "aumento_1"
        if d == 0:
            return "estabilidade"
        return "melhora"

    merged["delta_class"] = merged.apply(_delta_row, axis=1)
    delta_colors = {
        "melhora": "#15803d",
        "estabilidade": "#d1d5db",
        "aumento_1": "#f97316",
        "aumento_2plus": "#7f1d1d",
        "indisponivel": "#f3f4f6",
    }
    counts = merged["delta_class"].value_counts().to_dict()
    n_ok = int((merged["delta_class"] != "indisponivel").sum())
    fig2, ax2 = plt.subplots(figsize=(6, 6), dpi=150)
    for cls, color in delta_colors.items():
        sub = merged[merged["delta_class"] == cls]
        if not sub.empty:
            sub.plot(ax=ax2, color=color, edgecolor="#666666", linewidth=0.2)
    ax2.set_axis_off()
    # Sem título interno — título oficial no markdown
    import matplotlib.patches as mpatches

    def _pct(k: str) -> str:
        v = int(counts.get(k, 0))
        if n_ok <= 0:
            return f"{v}"
        return f"{v} ({100.0 * v / n_ok:.1f}%)".replace(".", ",")

    handles = [
        mpatches.Patch(color=c, label=l)
        for l, c in [
            (f"Melhora — {_pct('melhora')}", delta_colors["melhora"]),
            (f"Estabilidade — {_pct('estabilidade')}", delta_colors["estabilidade"]),
            (f"Aumento de 1 nível — {_pct('aumento_1')}", delta_colors["aumento_1"]),
            (f"Aumento de 2+ níveis — {_pct('aumento_2plus')}", delta_colors["aumento_2plus"]),
        ]
    ]
    ax2.legend(handles=handles, loc="lower left", fontsize=7)
    path_delta = out_dir / "mapa_delta_7d.png"
    fig2.savefig(path_delta, bbox_inches="tight")
    plt.close(fig2)

    return {
        "disponivel": True,
        "mapa_atual_projecao": str(path_ab),
        "mapa_delta": str(path_delta),
        "delta_counts": {k: int(counts.get(k, 0)) for k in ("melhora", "estabilidade", "aumento_1", "aumento_2plus")},
        "delta_n": n_ok,
    }
