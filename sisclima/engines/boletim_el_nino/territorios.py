# -*- coding: utf-8 -*-
"""Camada territorial — aldeias e quilombos do Vigibarragens + risco ARARAS."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_plural, md_table
from sisclima.engines.boletim_el_nino.referencias import cite
from sisclima.ingestion.vigibarragens import CATEGORIA_ALDEIA, CATEGORIA_QUILOMBO

log = get_logger(__name__)

_NIVEIS_CRITICOS = {"vermelha", "roxa"}


def _cod7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


def _load_vigibarragens() -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        from sisclima.core.db import read_table, table_exists

        pts = read_table("vigibarragens_populacoes") if table_exists("vigibarragens_populacoes") else pd.DataFrame()
        mun = read_table("vigibarragens_municipal") if table_exists("vigibarragens_municipal") else pd.DataFrame()
        return pts if pts is not None else pd.DataFrame(), mun if mun is not None else pd.DataFrame()
    except Exception as exc:  # noqa: BLE001
        log.warning("Vigibarragens indisponível: %s", exc)
        return pd.DataFrame(), pd.DataFrame()


def _merge_risco(resumo: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty or "cod_ibge" not in resumo.columns:
        return pd.DataFrame()
    cols = [
        c
        for c in (
            "cod_ibge",
            "municipio",
            "regional_saude",
            "nivel",
            "nivel_predicao_7d",
            "tmax",
            "pm25_ugm3",
            "focos_queimadas_7d",
            "focos_7d",
            "situacao_hidro",
        )
        if c in resumo.columns
    ]
    r = resumo[cols].copy()
    r["_cod"] = _cod7(r["cod_ibge"])
    return r.dropna(subset=["_cod"]).drop_duplicates("_cod")


def _exposição(row: pd.Series | dict) -> str:
    """Exposição específica — risco integrado não é exposição."""
    parts: list[str] = []
    try:
        tmax = row.get("tmax")
        if tmax is not None and float(tmax) >= 37:
            parts.append("calor")
    except (TypeError, ValueError):
        pass
    try:
        pm25 = row.get("pm25_ugm3")
        if pm25 is not None and float(pm25) >= 25:
            parts.append("fumaça/PM2,5")
    except (TypeError, ValueError):
        pass
    try:
        focos = row.get("focos_queimadas_7d", row.get("focos_7d"))
        if focos is not None and float(focos) >= 1:
            parts.append("fogo")
    except (TypeError, ValueError):
        pass
    hidro = str(row.get("situacao_hidro") or "").lower()
    if hidro.startswith("seca_"):
        parts.append("baixa disponibilidade hídrica")
    if len(parts) >= 2:
        return "múltiplas exposições (" + ", ".join(parts) + ")"
    if parts:
        return parts[0]
    return "sem exposição específica destacada além do risco integrado"


def _articulacao(categoria: str) -> str:
    if categoria == CATEGORIA_ALDEIA:
        return "SMS, Regional, DSEI/SESAI, FUNAI"
    if categoria == CATEGORIA_QUILOMBO:
        return "SMS, Regional, organizações quilombolas locais"
    return "SMS, Regional"


def _nivel_pt(v: Any) -> str:
    s = str(v or "—").strip().lower()
    mapa = {
        "verde": "Verde",
        "amarela": "Amarela",
        "laranja": "Laranja",
        "vermelha": "Vermelha",
        "roxa": "Roxa",
        "cinza": "Cinza",
    }
    return mapa.get(s, str(v or "—").title() if v else "—")


def _quadro_aldeias_municipal(mun_crit: pd.DataFrame, limite: int = 20) -> list[list[str]]:
    """Agrega aldeias por município crítico — sem coluna Tipo."""
    if mun_crit.empty or "n_aldeias" not in mun_crit.columns:
        return []
    work = mun_crit[pd.to_numeric(mun_crit["n_aldeias"], errors="coerce").fillna(0) > 0].copy()
    if work.empty:
        return []
    work = work.sort_values("n_aldeias", ascending=False)
    rows: list[list[str]] = []
    for _, row in work.head(limite).iterrows():
        rows.append(
            [
                str(row.get("municipio") or "—"),
                fmt_int(row.get("n_aldeias")),
                _nivel_pt(row.get("nivel")),
                _nivel_pt(row.get("nivel_predicao_7d")),
                _exposição(row),
            ]
        )
    return rows


def _quadro_quilombos(pts: pd.DataFrame, risco: pd.DataFrame, *, limite: int = 30) -> list[list[str]]:
    """Lista comunidades quilombolas certificadas — sem coluna Tipo."""
    if pts.empty or risco.empty:
        return []
    work = pts[pts["categoria"] == CATEGORIA_QUILOMBO].copy()
    if work.empty:
        return []
    work["_cod"] = _cod7(work["cod_ibge"])
    joined = work.merge(risco, on="_cod", how="inner", suffixes=("", "_r"))
    if joined.empty:
        return []
    joined = joined[joined["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
    joined = joined.sort_values(["municipio", "nome"], ascending=[True, True])
    rows: list[list[str]] = []
    for _, row in joined.head(limite).iterrows():
        rows.append(
            [
                str(row.get("nome") or "—")[:70],
                str(row.get("municipio") or row.get("municipio_r") or "—"),
                _nivel_pt(row.get("nivel")),
                _nivel_pt(row.get("nivel_predicao_7d")),
                _exposição(row),
            ]
        )
    return rows


def _centroides_municipais(merged) -> dict[str, tuple[float, float]]:
    """IBGE 7 dígitos -> (lon, lat) do ponto representativo do município."""
    out: dict[str, tuple[float, float]] = {}
    if merged is None or merged.empty or "geometry" not in merged.columns:
        return out
    for _, row in merged.iterrows():
        cod = str(row.get("_cod") or "").strip()
        geom = row.get("geometry")
        if not cod or geom is None:
            continue
        try:
            pt = geom.representative_point()
            out[cod] = (float(pt.x), float(pt.y))
        except Exception:  # noqa: BLE001
            continue
    return out


def _coords_plot(pts: pd.DataFrame, centroids: dict[str, tuple[float, float]]) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Aldeias com lat/lon; quilombos com lat/lon ou centróide municipal (jitter leve)."""
    import numpy as np

    if pts is None or pts.empty:
        return pd.DataFrame(), pd.DataFrame(), 0

    ald = pts[pts["categoria"] == CATEGORIA_ALDEIA].copy()
    qui = pts[pts["categoria"] == CATEGORIA_QUILOMBO].copy()

    if not ald.empty and "lat" in ald.columns and "lon" in ald.columns:
        ald = ald.dropna(subset=["lat", "lon"])
    else:
        ald = pd.DataFrame()

    n_centroid = 0
    if qui.empty:
        return ald, pd.DataFrame(), 0

    rows = []
    for i, row in qui.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        try:
            if lat is not None and lon is not None and pd.notna(lat) and pd.notna(lon):
                rows.append({**row.to_dict(), "lon": float(lon), "lat": float(lat), "_via_centroid": False})
                continue
        except (TypeError, ValueError):
            pass
        m = _cod7(pd.Series([row.get("cod_ibge")]))
        cod = str(m.iloc[0] if len(m) else "") if m is not None else ""
        if cod in ("", "nan", "None"):
            cod = ""
        if cod and cod in centroids:
            lon_c, lat_c = centroids[cod]
            # jitter estável por índice para não empilhar no mesmo ponto
            j = (hash(str(row.get("nome") or i)) % 1000) / 1000.0
            ang = 2 * np.pi * j
            r = 0.04 + 0.03 * ((hash(str(i)) % 100) / 100.0)
            rows.append(
                {
                    **row.to_dict(),
                    "lon": lon_c + r * np.cos(ang),
                    "lat": lat_c + r * np.sin(ang),
                    "_via_centroid": True,
                }
            )
            n_centroid += 1
    qui_plot = pd.DataFrame(rows) if rows else pd.DataFrame()
    return ald, qui_plot, n_centroid


def export_mapa_territorios(
    resumo: pd.DataFrame,
    pts: pd.DataFrame,
    out_dir: Path,
    *,
    data_ref: str = "",
) -> dict[str, Any]:
    """Mapa de risco ARARAS com pontos de aldeias e quilombos (coordenadas Vigibarragens)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from sisclima.engines.boletim_el_nino.maps import LEVEL_COLOR_MAP, LEVEL_ORDER, _load_gdf, _prep_merge, _NIVEL_LABEL
    except Exception as exc:  # noqa: BLE001
        log.warning("Mapa territorial indisponível: %s", exc)
        return {"disponivel": False}

    merged = _prep_merge(_load_gdf(), resumo)
    if merged is None:
        return {"disponivel": False}

    centroids = _centroides_municipais(merged)
    ald, qui, n_qui_centroid = _coords_plot(pts, centroids)

    fig, ax = plt.subplots(figsize=(8.5, 8.5), dpi=160)
    # Fundo municipal mais claro para contraste com marcadores
    for nivel in LEVEL_ORDER:
        sub = merged[merged["nivel"] == nivel]
        if not sub.empty:
            sub.plot(ax=ax, color=LEVEL_COLOR_MAP.get(nivel, "#ccc"), edgecolor="#4a4a4a", linewidth=0.25, alpha=0.72)

    # Halo branco atrás + marcador colorido (legibilidade sobre vermelho/roxo)
    if not ald.empty:
        ax.scatter(
            ald["lon"],
            ald["lat"],
            s=55,
            c="white",
            marker="^",
            alpha=1.0,
            linewidths=0,
            zorder=5,
        )
        ax.scatter(
            ald["lon"],
            ald["lat"],
            s=36,
            c="#00E5FF",
            marker="^",
            edgecolors="#003344",
            linewidths=0.6,
            alpha=0.95,
            zorder=6,
            label="Aldeias FUNAI",
        )
    if not qui.empty:
        ax.scatter(
            qui["lon"],
            qui["lat"],
            s=70,
            c="white",
            marker="s",
            alpha=1.0,
            linewidths=0,
            zorder=5,
        )
        ax.scatter(
            qui["lon"],
            qui["lat"],
            s=48,
            c="#FFD600",
            marker="s",
            edgecolors="#1a1a1a",
            linewidths=0.8,
            alpha=0.98,
            zorder=7,
            label="Município com quilombo certificado",
        )

    ax.set_axis_off()
    # Sem título interno — título oficial no markdown acima da figura
    handles = [
        mpatches.Patch(color=LEVEL_COLOR_MAP.get(k, "#ccc"), label=_NIVEL_LABEL.get(k, k))
        for k in ["verde", "amarela", "laranja", "vermelha", "roxa"]
    ]
    handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="^",
            color="w",
            markerfacecolor="#00E5FF",
            markeredgecolor="#003344",
            markersize=10,
            label="Aldeia (FUNAI)",
        )
    )
    handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="s",
            color="w",
            markerfacecolor="#FFD600",
            markeredgecolor="#1a1a1a",
            markersize=9,
            label="Município com quilombo certificado (localização municipal aproximada)",
        )
    )
    ax.legend(handles=handles, loc="lower left", fontsize=7, frameon=True, framealpha=0.92)
    path = out_dir / "mapa_territorios_tradicionais.png"
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return {
        "disponivel": True,
        "mapa_territorios": str(path),
        "quilombos_via_centroid": n_qui_centroid,
        "n_aldeias_plot": int(len(ald)),
        "n_quilombos_plot": int(len(qui)),
    }


def _quadro_cobertura_rede() -> tuple[str, str]:
    """Territórios em município vermelho/roxo e longe da APS ou do hospital."""
    try:
        from sisclima.engines.cobertura_territorio import load_cobertura
    except Exception:
        return INDISPONIVEL, ""
    cob = load_cobertura()
    nota = (
        "km e minutos de trajeto viário (OSRM, sem trânsito em tempo real) até CNES com coordenada oficial; "
        "se a rota falhar, usa linha reta (sem minutos). Centroide municipal não entra no cálculo. "
        "Exposição climática do município não significa ausência de UBS."
    )
    if cob is None or cob.empty:
        return (
            "_Sem cálculo de cobertura território–CNES nesta rodada (sem pontos com lat/lon oficial)._",
            nota,
        )
    work = cob.copy()
    if "nivel" in work.columns:
        work = work[work["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
    if "longe_rede" in work.columns:
        work = work[work["longe_rede"].fillna(False)]
    if work.empty:
        return (
            "_Nenhum território georreferenciado em município vermelho/roxo classificado como longe da APS (>30 km de trajeto) "
            "ou do hospital/UPA (>50 km de trajeto) nesta rodada._",
            nota,
        )
    work = work.sort_values(["km_aps", "km_hospital"], ascending=False, na_position="last")
    rows: list[list[str]] = []
    for _, row in work.head(25).iterrows():
        rows.append(
            [
                str(row.get("nome") or "—")[:60],
                str(row.get("categoria") or "—"),
                str(row.get("municipio") or "—"),
                _nivel_pt(row.get("nivel")),
                fmt_int(row.get("km_aps")) if pd.notna(row.get("km_aps")) else INDISPONIVEL,
                fmt_int(row.get("min_aps")) if pd.notna(row.get("min_aps")) else INDISPONIVEL,
                fmt_int(row.get("km_hospital")) if pd.notna(row.get("km_hospital")) else INDISPONIVEL,
                fmt_int(row.get("min_hospital")) if pd.notna(row.get("min_hospital")) else INDISPONIVEL,
            ]
        )
    headers = ["Território", "Categoria", "Município", "Risco", "km APS", "min APS", "km hospital", "min hospital"]
    return md_table(headers, rows, vazio=INDISPONIVEL), nota


def build_territorios(resumo: pd.DataFrame, *, assets_dir: Path | None = None, data_ref: str = "") -> dict[str, Any]:
    """Cruza aldeias/quilombos Vigibarragens com classificação de risco municipal."""
    pts, mun = _load_vigibarragens()
    cite_v = cite("vigibarragens")
    risco = _merge_risco(resumo)

    n_ald = int((pts["categoria"] == CATEGORIA_ALDEIA).sum()) if not pts.empty and "categoria" in pts.columns else 0
    n_qui = int((pts["categoria"] == CATEGORIA_QUILOMBO).sum()) if not pts.empty and "categoria" in pts.columns else 0
    n_ald_geo = int(pts.loc[pts["categoria"] == CATEGORIA_ALDEIA, ["lat", "lon"]].dropna().shape[0]) if n_ald else 0
    n_qui_geo = int(pts.loc[pts["categoria"] == CATEGORIA_QUILOMBO, ["lat", "lon"]].dropna().shape[0]) if n_qui else 0

    ti_status = "OK" if n_ald > 0 else "PENDENTE"
    qui_status = "OK" if n_qui > 0 else "PENDENTE"

    # Municípios com território em vermelho/roxo
    mun_crit: pd.DataFrame = pd.DataFrame()
    if not mun.empty and not risco.empty:
        m = mun.copy()
        m["_cod"] = _cod7(m["cod_ibge"])
        mun_crit = m.merge(risco, on="_cod", how="inner", suffixes=("", "_r"))
        mun_crit = mun_crit[mun_crit["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS)]
        n_a = pd.to_numeric(mun_crit["n_aldeias"], errors="coerce").fillna(0) if "n_aldeias" in mun_crit.columns else 0
        n_q = pd.to_numeric(mun_crit["n_quilombos"], errors="coerce").fillna(0) if "n_quilombos" in mun_crit.columns else 0
        mun_crit = mun_crit[(n_a > 0) | (n_q > 0)]
        if "n_aldeias" in mun_crit.columns:
            mun_crit = mun_crit.sort_values(["n_aldeias", "n_quilombos"], ascending=False)

    rows_ti = _quadro_aldeias_municipal(mun_crit, limite=20)
    rows_qui = _quadro_quilombos(pts, risco, limite=25)

    headers_ti = ["Município", "N.º de aldeias", "Risco atual", "Projeção ~7 dias", "Principal exposição"]
    headers_qui = ["Comunidade", "Município", "Risco atual", "Projeção ~7 dias", "Principal exposição"]
    md_ti = md_table(headers_ti, rows_ti, vazio=INDISPONIVEL) if rows_ti else (
        f"_Nenhuma aldeia indígena em município nas classes vermelha ou roxa nesta rodada. {cite_v}_"
    )
    md_qui = md_table(headers_qui, rows_qui, vazio=INDISPONIVEL) if rows_qui else (
        f"_Nenhuma comunidade quilombola certificada em município nas classes vermelha ou roxa nesta rodada. {cite_v}_"
    )

    n_mun_ald_crit = int((mun_crit["n_aldeias"].fillna(0) > 0).sum()) if not mun_crit.empty and "n_aldeias" in mun_crit.columns else 0
    n_mun_qui_crit = int((mun_crit["n_quilombos"].fillna(0) > 0).sum()) if not mun_crit.empty and "n_quilombos" in mun_crit.columns else 0
    n_crit = int(risco["nivel"].astype(str).str.lower().isin(_NIVEIS_CRITICOS).sum()) if not risco.empty else 0

    resumo_md = (
        f"Entre os {fmt_plural(n_crit, 'município', 'municípios')} nas classes vermelha e roxa, "
        f"**{fmt_int(n_mun_ald_crit)}** têm aldeias indígenas e "
        f"**{fmt_int(n_mun_qui_crit)}** têm comunidades quilombolas certificadas."
    )
    nota_aldeias = (
        "Os quantitativos correspondem a aldeias georreferenciadas associadas ao município "
        "e não representam estimativa populacional."
    )
    nota_quilombos = (
        "Comunidade certificada pela Fundação Cultural Palmares não equivale necessariamente "
        "a território delimitado ou titulado."
    )

    cob_md, nota_cob = _quadro_cobertura_rede()

    mapa: dict[str, Any] = {"disponivel": False}
    if assets_dir is not None and not pts.empty:
        mapa = export_mapa_territorios(resumo, pts, assets_dir, data_ref=data_ref)

    return {
        "ti_status": ti_status,
        "quilombo_status": qui_status,
        "resumo_md": resumo_md,
        "quadro_md": md_ti,
        "quilombo_md": md_qui,
        "nota_aldeias": nota_aldeias,
        "nota_quilombos": nota_quilombos,
        "cobertura_md": cob_md,
        "nota_cobertura": nota_cob,
        "n_aldeias": n_ald,
        "n_quilombos": n_qui,
        "n_mun_aldeias_criticos": n_mun_ald_crit,
        "n_mun_quilombos_criticos": n_mun_qui_crit,
        "mapa": mapa,
        "nota": "",
    }
