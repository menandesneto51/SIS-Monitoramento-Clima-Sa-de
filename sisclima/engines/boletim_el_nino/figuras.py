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
        import tempfile

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # OneDrive/Windows às vezes trava o PNG aberto — grava temp e substitui
        with tempfile.NamedTemporaryFile(
            suffix=path.suffix or ".png",
            dir=str(path.parent),
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        fig.savefig(tmp_path, dpi=160, bbox_inches="tight", facecolor="white")
        try:
            tmp_path.replace(path)
        except OSError:
            import shutil

            shutil.copy2(tmp_path, path)
            tmp_path.unlink(missing_ok=True)
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


CUIABA_IBGE6 = "510340"
CUIABA_LAT = -15.6014
CUIABA_LON = -56.0979
# Referência histórica SE 35/2026 (estação INMET) — não anotar no gráfico nem no boletim corrente
INMET_CUIABA_RECORDE_SE35 = {
    "2026-08-30": 41.2,
    "2026-08-31": 41.3,
}


def _cache_cuiaba_path() -> Path:
    from sisclima.core.config import ROOT

    p = ROOT / "data" / "cache" / "cuiaba_openmeteo_diario.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _fetch_openmeteo_cuiaba_diario(
    *,
    start: str = "1981-01-01",
    end: str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Série diária Cuiabá via Archive Open-Meteo (janelas de 5 anos + cache CSV)."""
    import time
    from datetime import date, timedelta

    from sisclima.core.config import APP_CONFIG, env
    from sisclima.core.http_client import http_get

    end = end or (date.today() - timedelta(days=1)).isoformat()
    cached = pd.DataFrame()
    cache_path = _cache_cuiaba_path()
    if use_cache and cache_path.exists():
        try:
            cached = pd.read_csv(cache_path)
            cached["data"] = pd.to_datetime(cached["data"], errors="coerce")
        except Exception:  # noqa: BLE001
            cached = pd.DataFrame()

    base = env("OPENMETEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")
    api_key = (env("OPENMETEO_API_KEY", "") or "").strip()
    frames: list[pd.DataFrame] = []
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cur <= end_d:
        chunk_end = min(date(cur.year + 4, 12, 31), end_d)
        s, e = cur.isoformat(), chunk_end.isoformat()
        if not cached.empty:
            mask = (cached["data"] >= s) & (cached["data"] <= e)
            n_have = int(mask.sum())
            n_need = (chunk_end - cur).days + 1
            if n_need > 0 and n_have / n_need >= 0.9:
                cur = chunk_end + timedelta(days=1)
                continue
        params: dict[str, Any] = {
            "latitude": f"{CUIABA_LAT:.5f}",
            "longitude": f"{CUIABA_LON:.5f}",
            "start_date": s,
            "end_date": e,
            "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean",
            "timezone": APP_CONFIG.timezone,
        }
        if api_key:
            params["apikey"] = api_key
        ok = False
        for attempt in range(4):
            try:
                r = http_get(base, params=params, timeout=180, ssl_env_key="OPENMETEO_SSL_VERIFY", retries=0)
                if r.status_code == 429:
                    time.sleep(min(60.0, 10.0 * (attempt + 1)))
                    continue
                r.raise_for_status()
                daily = (r.json() or {}).get("daily") or {}
                if daily.get("time"):
                    frames.append(
                        pd.DataFrame(
                            {
                                "data": daily["time"],
                                "tmax": daily.get("temperature_2m_max"),
                                "tmin": daily.get("temperature_2m_min"),
                                "tmedia": daily.get("temperature_2m_mean"),
                            }
                        )
                    )
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                log.warning("Open-Meteo Cuiabá %s–%s tentativa %s: %s", s, e, attempt + 1, exc)
                time.sleep(5.0 * (attempt + 1))
        if not ok:
            log.warning("Open-Meteo Cuiabá %s–%s falhou após retries", s, e)
        time.sleep(1.2)
        cur = chunk_end + timedelta(days=1)

    parts = []
    if not cached.empty:
        parts.append(cached)
    if frames:
        got = pd.concat(frames, ignore_index=True)
        got["data"] = pd.to_datetime(got["data"], errors="coerce")
        for c in ("tmax", "tmin", "tmedia"):
            got[c] = pd.to_numeric(got[c], errors="coerce")
        parts.append(got)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    for c in ("tmax", "tmin", "tmedia"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["data"]).drop_duplicates("data", keep="last").sort_values("data")
    df["fonte"] = "openmeteo_archive"
    try:
        df[["data", "tmax", "tmin", "tmedia", "fonte"]].to_csv(cache_path, index=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao gravar cache Cuiabá: %s", exc)
    return df.reset_index(drop=True)


def _serie_cuiaba_local_ou_api(*, ano_inicio: int = 1981) -> pd.DataFrame:
    """Série diária Cuiabá; corta dados futuros (OBSERVED_DATA_DATE <= hoje−1)."""
    from datetime import date, timedelta

    df = _serie_cuiaba_local_ou_api_raw(ano_inicio=ano_inicio)
    if df is None or df.empty:
        return pd.DataFrame()
    corte = pd.Timestamp(date.today() - timedelta(days=1))
    df = df[df["data"] <= corte]
    return df.reset_index(drop=True)


def _serie_cuiaba_local_ou_api_raw(*, ano_inicio: int = 1981) -> pd.DataFrame:
    """Série longa Cuiabá: Archive Open-Meteo (padrão dos gráficos) + reforço local recente."""
    from sisclima.core.db import read_table, table_exists

    api = _fetch_openmeteo_cuiaba_diario(start=f"{ano_inicio}-01-01")
    frames: list[pd.DataFrame] = []
    if not api.empty:
        frames.append(api)
    if table_exists("hist_clima_municipal_diario"):
        hist = read_table("hist_clima_municipal_diario")
        if hist is not None and not hist.empty and "cod_ibge" in hist.columns:
            h = hist.copy()
            h["cod6"] = h["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str[:6]
            h = h[h["cod6"] == CUIABA_IBGE6].copy()
            if not h.empty:
                h["data"] = pd.to_datetime(h["data"], errors="coerce")
                for c in ("tmax", "tmin"):
                    if c in h.columns:
                        h[c] = pd.to_numeric(h[c], errors="coerce")
                if "tmedia" not in h.columns:
                    h["tmedia"] = (pd.to_numeric(h.get("tmax"), errors="coerce") + pd.to_numeric(h.get("tmin"), errors="coerce")) / 2.0
                keep = [c for c in ("data", "tmax", "tmin", "tmedia", "fonte") if c in h.columns]
                frames.append(h[keep])
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])
    if "fonte" not in df.columns:
        df["fonte"] = "openmeteo_archive"
    df["_ord"] = df["fonte"].map({"openmeteo_archive": 0, "openmeteo": 1}).fillna(0)
    df = df.sort_values(["data", "_ord"]).drop_duplicates("data", keep="last")
    df = df[df["data"].dt.year >= ano_inicio].sort_values("data")
    return df.drop(columns=["_ord"], errors="ignore").reset_index(drop=True)


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
    # Série OBSERVADA: sem datas futuras relativas ao corte (hoje−1)
    from datetime import date, timedelta

    corte = pd.Timestamp(date.today() - timedelta(days=1))
    df = df[df["data"] <= corte]
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


def export_serie_cuiaba_temperaturas(
    out_dir: Path,
    *,
    ano_inicio: int = 1981,
) -> dict[str, Any]:
    """Temperaturas diárias Cuiabá (máx/média/mín) no padrão série longa."""
    meta: dict[str, Any] = {"disponivel": False, "path": None}
    df = _serie_cuiaba_local_ou_api(ano_inicio=ano_inicio)
    if df.empty or "tmax" not in df.columns:
        return meta
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return meta

    ini = str(df["data"].min().date())
    fim = str(df["data"].max().date())
    fig, ax = plt.subplots(figsize=(10.2, 4.0), dpi=160)
    if "tmin" in df.columns:
        ax.plot(df["data"], df["tmin"], color="#2a9d8f", lw=0.45, alpha=0.9, label="Mínima")
    if "tmedia" in df.columns:
        ax.plot(df["data"], df["tmedia"], color="#e76f3c", lw=0.5, alpha=0.9, label="Média")
    ax.plot(df["data"], df["tmax"], color="#c1121f", lw=0.5, alpha=0.95, label="Máxima")
    ax.set_ylabel("Temperatura (°C)")
    ax.set_xlabel("Data")
    ax.set_title(f"Temperaturas diárias — Cuiabá ({ini[:4]}–{fim[:4]})")
    ax.set_ylim(0, 45)
    ax.legend(loc="upper right", fontsize=8, frameon=False, ncol=3)
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    path = out_dir / "serie_cuiaba_temperaturas_diarias.png"
    saved = _save(fig, path)
    if not saved:
        return meta
    from datetime import date, timedelta

    corte = pd.Timestamp(date.today() - timedelta(days=7))
    recent = df[df["data"] >= corte]
    om_max = float(pd.to_numeric(recent["tmax"], errors="coerce").max()) if not recent.empty else None
    meta.update(
        {
            "disponivel": True,
            "path": saved,
            "inicio": ini,
            "fim": fim,
            "openmeteo_tmax_semana": om_max,
            "n_dias": int(len(df)),
        }
    )
    return meta


def export_serie_cuiaba_amplitude(
    out_dir: Path,
    *,
    ano_inicio: int = 1981,
) -> dict[str, Any]:
    """Amplitude térmica diária Cuiabá + média móvel 30 dias."""
    meta: dict[str, Any] = {"disponivel": False, "path": None}
    df = _serie_cuiaba_local_ou_api(ano_inicio=ano_inicio)
    if df.empty or "tmax" not in df.columns or "tmin" not in df.columns:
        return meta
    work = df.dropna(subset=["tmax", "tmin"]).copy()
    work["amplitude"] = work["tmax"] - work["tmin"]
    work["mm30"] = work["amplitude"].rolling(30, min_periods=10).mean()
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return meta
    ini = str(work["data"].min().date())
    fim = str(work["data"].max().date())
    fig, ax = plt.subplots(figsize=(10.2, 3.8), dpi=160)
    ax.fill_between(work["data"], work["amplitude"], color="#7dcfb6", alpha=0.55, linewidth=0)
    ax.plot(work["data"], work["amplitude"], color="#5fb89a", lw=0.35, label="Amplitude diária")
    ax.plot(work["data"], work["mm30"], color="#1d3557", lw=1.4, ls="--", label="Média móvel 30 dias")
    ax.set_ylabel("Amplitude (°C)")
    ax.set_xlabel("Data")
    ax.set_title(f"Amplitude térmica diária — Cuiabá ({ini[:4]}–{fim[:4]})")
    ax.set_ylim(0, 25)
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.xaxis.set_major_locator(mdates.YearLocator(5))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(True, axis="y", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    path = out_dir / "serie_cuiaba_amplitude_termica.png"
    saved = _save(fig, path)
    if not saved:
        return meta
    meta.update({"disponivel": True, "path": saved, "inicio": ini, "fim": fim, "n_dias": int(len(work))})
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


def export_grafico_projecao_7d(
    niveis_atual: dict[str, Any] | None,
    niveis_proj: dict[str, Any] | None,
    out_dir: Path,
    *,
    nome: str = "grafico_projecao_7d_classes.png",
) -> dict[str, Any]:
    """Barras lado a lado: classes atuais vs projeção ~7d (VR em destaque)."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}
    labels = ["Verde", "Amarela", "Laranja", "Vermelha", "Roxa"]
    keys = ["verde", "amarela", "laranja", "vermelha", "roxa"]
    a = [int((niveis_atual or {}).get(k) or 0) for k in keys]
    p = [int((niveis_proj or {}).get(k) or 0) for k in keys]
    if sum(a) + sum(p) == 0:
        return {"disponivel": False}
    x = np.arange(len(labels))
    w = 0.38
    fig, ax = plt.subplots(figsize=(8.0, 3.6), dpi=160)
    b1 = ax.bar(x - w / 2, a, w, color="#1351B4", label="Atual")
    b2 = ax.bar(x + w / 2, p, w, color="#e87722", label="Projeção ~7d")
    ax.bar_label(b1, padding=2, fontsize=7)
    ax.bar_label(b2, padding=2, fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Municípios")
    ax.set_title("Classes ARARAS — atual × projeção ~7 dias")
    ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis="y", alpha=0.25)
    path = out_dir / nome
    saved = _save(fig, path)
    return {"disponivel": bool(saved), "path": saved}


def export_grafico_picos_tmax(
    ranking: list[dict[str, Any]] | None,
    out_dir: Path,
    *,
    limiar: float = 41.0,
    nome: str = "grafico_picos_tmax_semana.png",
    titulo: str | None = None,
) -> dict[str, Any]:
    """Barras horizontais dos maiores picos de Tmáx na janela."""
    rows = [r for r in (ranking or []) if isinstance(r, dict) and r.get("tmax_max") is not None]
    if not rows:
        return {"disponivel": False}
    rows = sorted(rows, key=lambda r: float(r.get("tmax_max") or 0), reverse=True)[:12]
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}
    nomes = [str(r.get("municipio") or r.get("cod_ibge") or "—")[:22] for r in rows][::-1]
    vals = [float(r.get("tmax_max") or 0) for r in rows][::-1]
    fig, ax = plt.subplots(figsize=(7.5, max(3.2, 0.32 * len(vals) + 1.2)), dpi=160)
    colors = ["#b91c1c" if v >= limiar else "#ea580c" for v in vals]
    bars = ax.barh(nomes, vals, color=colors, edgecolor="#1a1a1a", linewidth=0.3)
    ax.axvline(limiar, color="#7f1d1d", linestyle="--", linewidth=1.0, label=f"{limiar:.0f} °C")
    ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=7)
    ax.set_xlabel("Tmáx (°C)")
    ax.set_title(titulo or f"Picos de Tmáx na janela (≥ {limiar:.0f} °C em destaque)")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis="x", alpha=0.25)
    path = out_dir / nome
    saved = _save(fig, path)
    return {"disponivel": bool(saved), "path": saved}


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


def export_grafico_geocalor_ehf(
    resumo: dict[str, Any] | None,
    out_dir: Path,
    *,
    nome: str = "grafico_geocalor_ehf_janela.png",
) -> dict[str, Any]:
    """Canal operacional: municípios em dia de onda (EHF) na temporada + janela do boletim.

    Usa ``serie_temporada_n_onda`` quando há pontos suficientes; senão cai na janela curta.
    Canal = P25–P75 móvel de 14 dias. Não é climatologia multi-anual.
    """
    meta = resumo or {}
    serie_temp = list(meta.get("serie_temporada_n_onda") or [])
    serie_janela = list(meta.get("serie_diaria_n_onda") or [])
    usar_temporada = len(serie_temp) >= 21
    serie = serie_temp if usar_temporada else serie_janela
    if len(serie) < 2:
        return {"disponivel": False}
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}

    datas = pd.to_datetime([r.get("data") for r in serie], errors="coerce")
    vals = pd.Series([int(r.get("n_onda") or 0) for r in serie], dtype=float)
    if datas.isna().all():
        return {"disponivel": False}

    # Canal móvel 14 dias (P25–P75)
    win = min(14, max(3, len(vals) // 3))
    p25 = vals.rolling(win, min_periods=max(2, win // 2), center=True).quantile(0.25)
    p75 = vals.rolling(win, min_periods=max(2, win // 2), center=True).quantile(0.75)

    mediana_temp = meta.get("n_onda_mediana_temporada")
    if mediana_temp is None and vals.notna().any():
        mediana_temp = float(vals.median())

    jan_ini = pd.to_datetime(meta.get("janela_inicio"), errors="coerce")
    jan_fim = pd.to_datetime(meta.get("janela_fim"), errors="coerce")
    in_janela = pd.Series(False, index=vals.index)
    if pd.notna(jan_ini) and pd.notna(jan_fim):
        in_janela = (datas >= jan_ini) & (datas <= jan_fim)

    fig, ax = plt.subplots(figsize=(9.2, 3.8), dpi=160)
    # Canal institucional (azul claro)
    ax.fill_between(
        datas,
        p25,
        p75,
        color="#93C5FD",
        alpha=0.45,
        label=f"Canal móvel P25–P75 ({win}d)",
        linewidth=0,
    )
    # Linha temporada
    ax.plot(
        datas,
        vals,
        color="#1351B4",
        linewidth=1.6,
        label="Municípios em dia de onda (EHF)",
        zorder=3,
    )
    if mediana_temp is not None:
        ax.axhline(
            float(mediana_temp),
            color="#64748B",
            ls="--",
            lw=1.1,
            label=f"Mediana da temporada ({float(mediana_temp):.0f})",
        )
    # Janela do boletim destacada
    if in_janela.any():
        ax.plot(
            datas[in_janela],
            vals[in_janela],
            color="#b91c1c",
            linewidth=2.2,
            marker="o",
            markersize=4,
            label="Janela do boletim",
            zorder=4,
        )
        # faixa vertical suave na janela
        ax.axvspan(
            datas[in_janela].min(),
            datas[in_janela].max(),
            color="#FEE2E2",
            alpha=0.35,
            zorder=0,
        )

    temp_ini = meta.get("temporada_inicio") or (str(datas.min().date()) if pd.notna(datas.min()) else "")
    temp_fim = meta.get("temporada_fim") or (str(datas.max().date()) if pd.notna(datas.max()) else "")
    ano = str(temp_ini)[:4] if temp_ini else "2026"
    if usar_temporada:
        ax.set_title(f"GeoCalor / EHF — municípios em dia de onda · temporada operacional {ano}")
    else:
        ini = meta.get("janela_inicio") or ""
        fim = meta.get("janela_fim") or ""
        ax.set_title(f"GeoCalor / EHF — municípios em dia de onda · {ini} a {fim}")

    ax.set_ylabel("Municípios em dia de onda (EHF)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    if len(datas) > 40:
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    else:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(datas) // 10)))
    fig.autofmt_xdate(rotation=45, ha="right")
    ax.legend(loc="upper left", fontsize=7.5, frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, axis="y", alpha=0.25)
    ax.set_ylim(bottom=0)
    path = out_dir / nome
    saved = _save(fig, path)
    return {
        "disponivel": bool(saved),
        "path": saved,
        "temporada": bool(usar_temporada),
        "temporada_inicio": temp_ini,
        "temporada_fim": temp_fim,
    }


def export_grafico_sazonalidade_historico(
    pack: dict[str, Any] | None,
    out_dir: Path,
    *,
    nome: str = "grafico_sazonalidade_historico_atual.png",
    resumo: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Figura composta: índice sazonal mensal (histórico × atual) + top correlações R/ρ/p.

    Preferência: lags temporais. Se vazios, calcula Pearson/Spearman ecológicos
    transversais (município) nos top pares OR do pacote.
    """
    pack = pack or {}
    mensal = pack.get("mensal") if isinstance(pack.get("mensal"), pd.DataFrame) else pd.DataFrame()
    picos = pack.get("picos") if isinstance(pack.get("picos"), pd.DataFrame) else pd.DataFrame()
    lags = pack.get("lags") if isinstance(pack.get("lags"), pd.DataFrame) else pd.DataFrame()
    odds = pack.get("odds") if isinstance(pack.get("odds"), pd.DataFrame) else pd.DataFrame()
    if mensal.empty and lags.empty and odds.empty:
        return {"disponivel": False}
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        log.warning("matplotlib indisponível: %s", exc)
        return {"disponivel": False}

    from datetime import date

    from sisclima.engines.clima_exposicoes import CLIMA_ROTULOS

    # Se lags vazios, montar correlações transversais a partir dos top OR
    fonte_corr = "lags"
    if lags.empty or (len(lags.columns) == 1 and "_empty" in lags.columns):
        fonte_corr = "transversal"
        lags = _correlacoes_transversais_or(odds, resumo)

    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=(11.2, 4.2), dpi=160, gridspec_kw={"width_ratios": [1.05, 1.35]}
    )

    # --- Painel A: índice sazonal mensal ---
    mes_atual = int(date.today().month)
    if not mensal.empty and "indice_sazonal" in mensal.columns:
        sm = mensal.copy()
        sm["indice_sazonal"] = pd.to_numeric(sm["indice_sazonal"], errors="coerce")
        sm["mes"] = pd.to_numeric(sm.get("mes"), errors="coerce")
        sm = sm.dropna(subset=["indice_sazonal"]).sort_values("mes")
        labels = [str(r.get("mes_rotulo") or int(r["mes"])) for _, r in sm.iterrows()]
        vals = sm["indice_sazonal"].tolist()
        cores = []
        for _, r in sm.iterrows():
            m = int(r["mes"]) if pd.notna(r.get("mes")) else -1
            if m == mes_atual:
                cores.append("#b91c1c")
            elif float(r["indice_sazonal"]) > 1.0:
                cores.append("#1351B4")
            else:
                cores.append("#93C5FD")
        ax_a.bar(range(len(vals)), vals, color=cores, width=0.72)
        ax_a.axhline(1.0, color="#64748B", ls="--", lw=1.0, label="Média do período (=1)")
        ax_a.set_xticks(range(len(labels)))
        ax_a.set_xticklabels(labels, fontsize=8)
        ax_a.set_ylabel("Índice sazonal")
        ax_a.set_title("Índice sazonal mensal (histórico)")
        if not picos.empty and "tipo" in picos.columns:
            se = picos[picos["tipo"] == "se_atual_vs_media"].head(1)
            if (
                not se.empty
                and pd.notna(se["valor_atual"].iloc[0])
                and pd.notna(se["valor_medio_historico"].iloc[0])
            ):
                atual = float(se["valor_atual"].iloc[0])
                media = float(se["valor_medio_historico"].iloc[0])
                se_n = se["semana_epi"].iloc[0] if "semana_epi" in se.columns else "—"
                try:
                    se_n = int(float(se_n))
                except Exception:
                    pass
                se_txt = f"SE {se_n}: atual {atual:.2f} vs média {media:.2f} (Δ {atual - media:+.2f})"
                ax_a.text(
                    0.02,
                    0.98,
                    se_txt,
                    transform=ax_a.transAxes,
                    va="top",
                    ha="left",
                    fontsize=7.5,
                    color="#1e293b",
                    bbox={
                        "boxstyle": "round,pad=0.25",
                        "facecolor": "#F8FAFC",
                        "edgecolor": "#CBD5E1",
                        "linewidth": 0.6,
                    },
                )
        ax_a.legend(loc="upper right", fontsize=7, frameon=False)
        ax_a.spines[["top", "right"]].set_visible(False)
        ax_a.grid(True, axis="y", alpha=0.25)
    else:
        ax_a.text(0.5, 0.5, "Índice sazonal indisponível", ha="center", va="center", transform=ax_a.transAxes)
        ax_a.set_axis_off()

    # --- Painel B: Pearson R / Spearman ρ ---
    titulo_b = (
        "Top associações temporais (R e ρ)"
        if fonte_corr == "lags"
        else "Top pares OR — correlação ecológica municipal (R e ρ)"
    )
    if not lags.empty and ("spearman" in lags.columns or "abs_spearman" in lags.columns):
        lg = lags.copy()
        lg["abs_spearman"] = pd.to_numeric(
            lg["abs_spearman"] if "abs_spearman" in lg.columns else lg.get("spearman"),
            errors="coerce",
        ).abs()
        lg["spearman"] = pd.to_numeric(lg.get("spearman"), errors="coerce")
        lg["pearson"] = pd.to_numeric(lg.get("pearson"), errors="coerce")
        lg["p_value"] = pd.to_numeric(lg.get("p_value"), errors="coerce")
        lg = lg.dropna(subset=["abs_spearman"]).sort_values("abs_spearman", ascending=False).head(8)
        if lg.empty:
            ax_b.text(0.5, 0.5, "Correlações insuficientes", ha="center", va="center", transform=ax_b.transAxes)
            ax_b.set_axis_off()
        else:
            y = np.arange(len(lg))
            h = 0.35
            pear = lg["pearson"].fillna(0).to_numpy()
            spea = lg["spearman"].fillna(0).to_numpy()
            ax_b.barh(y + h / 2, pear, height=h, color="#1351B4", label="Pearson R")
            ax_b.barh(y - h / 2, spea, height=h, color="#DC2626", alpha=0.85, label="Spearman ρ")
            labels_b = []
            for _, r in lg.iterrows():
                exp = CLIMA_ROTULOS.get(str(r.get("exposicao") or ""), str(r.get("exposicao") or "—"))
                des = str(r.get("desfecho") or "—").replace("_", " ")
                lag_s = ""
                if pd.notna(r.get("lag_dias")):
                    try:
                        lag_s = f" (lag {int(float(r['lag_dias']))}d)"
                    except Exception:
                        lag_s = ""
                labels_b.append(f"{exp} → {des}{lag_s}")
            ax_b.set_yticks(y)
            ax_b.set_yticklabels(labels_b, fontsize=6.5)
            ax_b.axvline(0, color="#94A3B8", lw=0.8)
            ax_b.set_xlabel("Correlação")
            ax_b.set_title(titulo_b)
            xmax = max(abs(float(np.nanmax(pear))), abs(float(np.nanmax(spea))), 0.1) * 1.45
            ax_b.set_xlim(-xmax, xmax)
            for i, (_, r) in enumerate(lg.iterrows()):
                p = r.get("p_value")
                try:
                    p_s = f"p={float(p):.3g}"
                    sig = " *" if float(p) < 0.05 else ""
                except Exception:
                    p_s = "p=—"
                    sig = ""
                try:
                    ann = (
                        f"R={float(r['pearson']):+.2f} · ρ={float(r['spearman']):+.2f} · {p_s}{sig}"
                    )
                except Exception:
                    ann = p_s
                ax_b.text(xmax * 0.98, i, ann, va="center", ha="right", fontsize=5.8, color="#334155")
            ax_b.legend(loc="lower right", fontsize=7, frameon=False)
            ax_b.spines[["top", "right"]].set_visible(False)
            ax_b.grid(True, axis="x", alpha=0.25)
            ax_b.invert_yaxis()
    else:
        ax_b.text(0.5, 0.5, "Correlações (R/ρ) indisponíveis", ha="center", va="center", transform=ax_b.transAxes)
        ax_b.set_axis_off()

    fig.suptitle(
        "Sazonalidade operacional — histórico × atual e correlações clima→desfecho",
        fontsize=11,
        y=1.02,
    )
    fig.tight_layout()
    path = out_dir / nome
    saved = _save(fig, path)
    return {"disponivel": bool(saved), "path": saved, "fonte_corr": fonte_corr}


def _correlacoes_transversais_or(
    odds: pd.DataFrame,
    resumo: pd.DataFrame | None,
) -> pd.DataFrame:
    """Pearson/Spearman ecológicos (município) nos top pares OR significativos."""
    if odds is None or odds.empty or resumo is None or resumo.empty:
        return pd.DataFrame()
    od = odds.copy()
    if "significativo_005" in od.columns:
        sig = pd.to_numeric(od["significativo_005"], errors="coerce").fillna(0).astype(int).eq(1)
        if sig.any():
            od = od.loc[sig]
    od["or"] = pd.to_numeric(od.get("or"), errors="coerce")
    od = od.dropna(subset=["or"]).sort_values("or", ascending=False).head(12)
    rows: list[dict[str, Any]] = []
    for _, r in od.iterrows():
        exp = str(r.get("exposicao") or "")
        des = str(r.get("desfecho") or "")
        if exp not in resumo.columns or des not in resumo.columns:
            continue
        x = pd.to_numeric(resumo[exp], errors="coerce")
        y = pd.to_numeric(resumo[des], errors="coerce")
        ok = x.notna() & y.notna()
        n = int(ok.sum())
        if n < 12:
            continue
        xv, yv = x[ok], y[ok]
        pear = float(xv.corr(yv, method="pearson"))
        spear = float(xv.rank().corr(yv.rank(), method="pearson"))
        # p aproximado via Spearman (mesma heurística do motor de sazonalidade)
        try:
            from sisclima.engines.seasonality import _spearman_pvalue

            p_sp = _spearman_pvalue(spear, n)
        except Exception:
            p_sp = float("nan")
        rows.append(
            {
                "exposicao": exp,
                "desfecho": des,
                "lag_dias": None,
                "pearson": pear,
                "spearman": spear,
                "abs_spearman": abs(spear) if spear == spear else float("nan"),
                "p_value": p_sp,
                "n_dias_validos": n,
            }
        )
    return pd.DataFrame(rows)


def relpath_fig(path: str | Path | None, dest: Path) -> str:
    if not path:
        return ""
    p = Path(str(path))
    try:
        return p.relative_to(dest).as_posix()
    except ValueError:
        return p.name
