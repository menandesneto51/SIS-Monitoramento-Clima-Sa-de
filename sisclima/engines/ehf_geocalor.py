"""Ondas de calor no método GeoCalor / Nairn & Fawcett (EHF).

Definição (GeoCalor Fiocruz / LAGAS-UnB):
- Tmédia diária; T3d = média móvel de 3 dias; T30d = média dos 30 dias anteriores.
- EHIsig = T3d − P95(Tmédia local)
- EHIaccl = T3d − T30d
- EHF = EHIsig × max(1, EHIaccl)
- Evento: ≥ 3 dias consecutivos com EHF > 0
- Intensidade (sobre dias com EHF > 0 no município):
  baixa 0 < EHF ≤ EHF85; severa EHF85 < EHF ≤ 3×EHF85; extrema EHF > 3×EHF85
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

METODOLOGIA = "GeoCalor_EHF_NairnFawcett_3d"
MIN_DIAS_EVENTO = 3


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)


def ensure_tmedia(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "tmedia" not in out.columns or out["tmedia"].isna().all():
        if {"tmax", "tmin"}.issubset(out.columns):
            out["tmedia"] = (
                pd.to_numeric(out["tmax"], errors="coerce")
                + pd.to_numeric(out["tmin"], errors="coerce")
            ) / 2.0
        else:
            out["tmedia"] = pd.to_numeric(out.get("tmedia"), errors="coerce")
    else:
        out["tmedia"] = pd.to_numeric(out["tmedia"], errors="coerce")
    return out


def compute_ehf_geocalor(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula EHI/EHF e classifica dias de onda (is_hw_day) por município."""
    if df is None or df.empty:
        return pd.DataFrame()

    out = ensure_tmedia(df)
    out["cod_ibge"] = _ibge7(out["cod_ibge"])
    out["data"] = pd.to_datetime(out["data"], errors="coerce")
    out = out.dropna(subset=["cod_ibge", "data", "tmedia"]).sort_values(["cod_ibge", "data"])

    frames = []
    for _cod, g in out.groupby("cod_ibge", sort=False):
        g = g.copy()
        t = g["tmedia"]
        t95 = float(t.quantile(0.95)) if t.notna().sum() else np.nan
        g["t95_tmedia"] = t95
        g["tmedia_3d"] = t.rolling(3, min_periods=3).mean()
        g["tmedia_30d_prev"] = t.shift(1).rolling(30, min_periods=15).mean()
        g["ehi_sig"] = g["tmedia_3d"] - t95
        g["ehi_accl"] = g["tmedia_3d"] - g["tmedia_30d_prev"]
        g["ehf"] = g["ehi_sig"] * np.maximum(1.0, g["ehi_accl"])
        pos = g.loc[g["ehf"] > 0, "ehf"]
        ehf85 = float(pos.quantile(0.85)) if len(pos) else np.nan
        g["ehf85"] = ehf85
        g["intensidade"] = _classificar_intensidade(g["ehf"], ehf85)
        g["is_hw_day"] = 0
        frames.append(g)

    daily = pd.concat(frames, ignore_index=True)
    daily = _marcar_dias_evento(daily)
    daily["data"] = daily["data"].dt.strftime("%Y-%m-%d")
    daily["atualizado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return daily


def _classificar_intensidade(ehf: pd.Series, ehf85: float) -> pd.Series:
    out = pd.Series(index=ehf.index, dtype=object)
    out[:] = None
    pos = ehf > 0
    if not pos.any() or pd.isna(ehf85) or ehf85 <= 0:
        out.loc[pos] = "baixa"
        return out
    out.loc[pos & (ehf <= ehf85)] = "baixa"
    out.loc[pos & (ehf > ehf85) & (ehf <= 3 * ehf85)] = "severa"
    out.loc[pos & (ehf > 3 * ehf85)] = "extrema"
    return out


def _marcar_dias_evento(df: pd.DataFrame) -> pd.DataFrame:
    """is_hw_day = 1 só em sequências com EHF>0 de pelo menos 3 dias."""
    out = df.copy()
    flags = []
    for _cod, g in out.groupby("cod_ibge", sort=False):
        ehf_pos = (pd.to_numeric(g["ehf"], errors="coerce").fillna(0) > 0).to_numpy()
        n = len(ehf_pos)
        hw = np.zeros(n, dtype=int)
        i = 0
        while i < n:
            if not ehf_pos[i]:
                i += 1
                continue
            j = i
            while j < n and ehf_pos[j]:
                j += 1
            if (j - i) >= MIN_DIAS_EVENTO:
                hw[i:j] = 1
            i = j
        g = g.copy()
        g["is_hw_day"] = hw
        flags.append(g)
    return pd.concat(flags, ignore_index=True)


def eventos_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Catálogo de eventos (≥3 dias consecutivos com EHF>0)."""
    if daily is None or daily.empty:
        return pd.DataFrame()

    work = daily.copy()
    work["cod_ibge"] = _ibge7(work["cod_ibge"])
    work["data"] = pd.to_datetime(work["data"], errors="coerce")
    work["ehf"] = pd.to_numeric(work["ehf"], errors="coerce")
    work = work.sort_values(["cod_ibge", "data"])

    rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for cod, g in work.groupby("cod_ibge", sort=False):
        g = g.reset_index(drop=True)
        ehf_pos = (g["ehf"].fillna(0) > 0).to_numpy()
        n = len(g)
        i = 0
        mun = None
        if "municipio" in g.columns:
            mun = g["municipio"].dropna().astype(str)
            mun = mun.iloc[0] if len(mun) else None
        while i < n:
            if not ehf_pos[i]:
                i += 1
                continue
            j = i
            while j < n and ehf_pos[j]:
                j += 1
            dur = j - i
            if dur >= MIN_DIAS_EVENTO:
                bloco = g.iloc[i:j]
                ints = bloco["intensidade"].dropna().astype(str)
                if (ints == "extrema").any():
                    peak = "extrema"
                elif (ints == "severa").any():
                    peak = "severa"
                else:
                    peak = "baixa"
                rows.append(
                    {
                        "cod_ibge": str(cod).zfill(7),
                        "municipio": mun,
                        "data_inicio": bloco["data"].min().strftime("%Y-%m-%d"),
                        "data_fim": bloco["data"].max().strftime("%Y-%m-%d"),
                        "duracao_dias": int(dur),
                        "ehf_max": float(bloco["ehf"].max()),
                        "ehf_medio": float(bloco["ehf"].mean()),
                        "intensidade": peak,
                        "n_dias_baixa": int((ints == "baixa").sum()),
                        "n_dias_severa": int((ints == "severa").sum()),
                        "n_dias_extrema": int((ints == "extrema").sum()),
                        "metodologia": METODOLOGIA,
                        "fonte": str(bloco["fonte"].iloc[0]) if "fonte" in bloco.columns else "openmeteo_archive",
                        "atualizado_em": now,
                    }
                )
            i = j
    return pd.DataFrame(rows)


def colunas_diario_persistencia() -> list[str]:
    return [
        "cod_ibge",
        "data",
        "municipio",
        "tmax",
        "tmin",
        "tmedia",
        "umidade_media",
        "precipitacao_mm",
        "ehi_sig",
        "ehi_accl",
        "ehf",
        "is_hw_day",
        "intensidade",
        "fonte",
        "atualizado_em",
    ]


EHF_RESUMO_COLS = [
    "ehf_geocalor",
    "ehf",
    "is_hw_day",
    "intensidade_ehf",
    "data_ehf_geocalor",
    "ehf_geocalor_idade_dias",
    "ehf_fonte",
    "duracao_onda_ehf_dias",
    "onda_geocalor_ativa",
    "onda_geocalor_severidade",
]


def geocalor_freshness_meta(*, max_age_days: int | None = None) -> dict[str, Any]:
    """SLO informativo do STAR GeoCalor (não bloqueia envio por padrão).

    Campos: ok, max_data, idade_dias, max_age_days, reason (se não ok).
    """
    from sisclima.core.config import env

    if max_age_days is None:
        try:
            max_age_days = int(
                env("ALERT_GEOCALOR_MAX_AGE_DAYS", "")
                or env("STAR_ETL_MAX_AGE_DAYS", "7")
                or 7
            )
        except (TypeError, ValueError):
            max_age_days = 7
    out: dict[str, Any] = {"ok": True, "max_age_days": int(max_age_days)}
    try:
        from sisclima.core.db import read_table

        daily = read_table("star_clima_geocalor_diario")
        if daily is None or daily.empty or "data" not in daily.columns:
            out.update({"ok": False, "reason": "star_vazio"})
            return out
        mx = pd.to_datetime(daily["data"], errors="coerce").max()
        if pd.isna(mx):
            out.update({"ok": False, "reason": "sem_data"})
            return out
        idade = int((pd.Timestamp.today().normalize() - pd.Timestamp(mx).normalize()).days)
        out.update({"max_data": str(pd.Timestamp(mx).date()), "idade_dias": idade})
        if idade > int(max_age_days):
            out["ok"] = False
            out["reason"] = "stale"
    except Exception as exc:  # noqa: BLE001
        out.update({"ok": False, "reason": "erro", "detail": str(exc)})
    return out


def _streak_ehf_positivo(g: pd.DataFrame, data_ref: pd.Timestamp) -> int:
    """Dias consecutivos com EHF>0 terminando em data_ref (ou no último dia ≤ ref)."""
    if g is None or g.empty:
        return 0
    work = g.sort_values("data")
    work = work[work["data"] <= data_ref]
    if work.empty:
        return 0
    last = work.iloc[-1]["data"]
    # exige continuidade até o último dia disponível do município
    if pd.Timestamp(last).normalize() < pd.Timestamp(data_ref).normalize() - pd.Timedelta(days=2):
        # série municipal muito defasada vs ref global
        pass
    streak = 0
    for _, row in work.iloc[::-1].iterrows():
        ehf = float(row["ehf"]) if pd.notna(row.get("ehf")) else 0.0
        if ehf > 0:
            streak += 1
        else:
            break
    return int(streak)


def snapshot_ehf_geocalor_municipal(
    *,
    data_ref: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Uma linha por município: EHF do último dia GeoCalor + duração da onda atual."""
    try:
        from sisclima.core.db import read_table

        daily = read_table("star_clima_geocalor_diario")
        eventos = read_table("star_ondas_calor_evento")
    except Exception:
        return pd.DataFrame()

    if daily is None or daily.empty:
        return pd.DataFrame()

    df = daily.copy()
    df["cod_ibge"] = _ibge7(df["cod_ibge"])
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["ehf"] = pd.to_numeric(df.get("ehf"), errors="coerce")
    df["is_hw_day"] = pd.to_numeric(df.get("is_hw_day"), errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["cod_ibge", "data"])
    if df.empty:
        return pd.DataFrame()

    fim = pd.to_datetime(data_ref, errors="coerce") if data_ref is not None else df["data"].max()
    if pd.isna(fim):
        fim = df["data"].max()
    fim = min(pd.Timestamp(fim).normalize(), df["data"].max().normalize())
    hoje = pd.Timestamp.today().normalize()
    idade_global = int((hoje - fim).days)

    rows: list[dict] = []
    for cod, g in df.groupby("cod_ibge", sort=False):
        g = g.sort_values("data")
        # último dia ≤ fim
        g_ok = g[g["data"] <= fim]
        if g_ok.empty:
            continue
        last = g_ok.iloc[-1]
        streak = _streak_ehf_positivo(g_ok, pd.Timestamp(last["data"]).normalize())
        intensidade = last.get("intensidade")
        if intensidade is None or (isinstance(intensidade, float) and pd.isna(intensidade)):
            intensidade = None
        rows.append(
            {
                "cod_ibge": str(cod).zfill(7),
                "ehf_geocalor": float(last["ehf"]) if pd.notna(last["ehf"]) else None,
                "is_hw_day": int(last.get("is_hw_day") or 0),
                "intensidade_ehf": str(intensidade) if intensidade else None,
                "data_ehf_geocalor": pd.Timestamp(last["data"]).strftime("%Y-%m-%d"),
                "ehf_geocalor_idade_dias": idade_global,
                "duracao_onda_ehf_dias": streak,
                "ehf_fonte": "geocalor_star",
            }
        )
    snap = pd.DataFrame(rows)
    if snap.empty:
        return snap

    # Evento aberto/recente reforça duração
    if eventos is not None and not eventos.empty:
        ev = eventos.copy()
        ev["cod_ibge"] = _ibge7(ev["cod_ibge"])
        ev["data_fim"] = pd.to_datetime(ev.get("data_fim"), errors="coerce")
        ev["duracao_dias"] = pd.to_numeric(ev.get("duracao_dias"), errors="coerce")
        ev = ev.dropna(subset=["cod_ibge", "data_fim"])
        # evento que termina perto do fim da série (±3 dias)
        recent = ev[(ev["data_fim"] >= fim - pd.Timedelta(days=3)) & (ev["data_fim"] <= fim + pd.Timedelta(days=1))]
        if not recent.empty:
            best = (
                recent.sort_values(["cod_ibge", "duracao_dias", "data_fim"], ascending=[True, False, False])
                .drop_duplicates("cod_ibge", keep="first")
            )
            m = best[["cod_ibge", "duracao_dias", "ehf_max", "intensidade"]].rename(
                columns={
                    "duracao_dias": "duracao_evento_ehf",
                    "ehf_max": "ehf_max_evento",
                    "intensidade": "intensidade_evento",
                }
            )
            snap = snap.merge(m, on="cod_ibge", how="left")
            # Só reforça duração/intensidade de evento se o dia ainda está em EHF>0 / onda
            ativo = (
                pd.to_numeric(snap["ehf_geocalor"], errors="coerce").fillna(0).gt(0)
                | pd.to_numeric(snap["is_hw_day"], errors="coerce").fillna(0).gt(0)
            )
            if ativo.any():
                d_day = pd.to_numeric(snap["duracao_onda_ehf_dias"], errors="coerce")
                d_ev = pd.to_numeric(snap.get("duracao_evento_ehf"), errors="coerce")
                snap.loc[ativo, "duracao_onda_ehf_dias"] = (
                    pd.concat([d_day, d_ev], axis=1).max(axis=1).loc[ativo].fillna(0).astype(int)
                )
                miss = ativo & (
                    snap["intensidade_ehf"].isna()
                    | (snap["intensidade_ehf"].astype(str).str.strip() == "")
                    | (snap["intensidade_ehf"].astype(str).str.lower() == "none")
                )
                if "intensidade_evento" in snap.columns:
                    snap.loc[miss, "intensidade_ehf"] = snap.loc[miss, "intensidade_evento"]
            # Dia sem EHF positivo: não herdar intensidade/duração de evento antigo
            inativo = ~ativo
            if inativo.any():
                snap.loc[inativo & (pd.to_numeric(snap["ehf_geocalor"], errors="coerce").fillna(0) <= 0), "intensidade_ehf"] = None
    return snap


def inject_ehf_geocalor(
    resumo: pd.DataFrame,
    *,
    data_ref: str | pd.Timestamp | None = None,
    prefer_geocalor: bool = True,
) -> pd.DataFrame:
    """Junta EHF GeoCalor no resumo municipal (operacional + alertas + RIT).

    - Preenche ``ehf_geocalor``, ``is_hw_day``, ``intensidade_ehf``, datas/idade.
    - Com ``prefer_geocalor=True``, sobrescreve ``ehf`` e ``ehf_adaptado`` quando houver GeoCalor.
    - Atualiza ``duracao_onda_calor_dias`` com o máximo entre o valor atual e a onda EHF.
    """
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    snap = snapshot_ehf_geocalor_municipal(data_ref=data_ref)
    if snap is None or snap.empty:
        return resumo

    out = resumo.copy()
    if "cod_ibge" not in out.columns:
        return out
    out["cod_ibge"] = _ibge7(out["cod_ibge"])

    drop_cols = [c for c in EHF_RESUMO_COLS + ["duracao_evento_ehf", "ehf_max_evento", "intensidade_evento"] if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols, errors="ignore")

    keep_snap = [c for c in snap.columns if c == "cod_ibge" or c not in out.columns or c in EHF_RESUMO_COLS]
    # always bring snapshot cols
    bring = [
        c
        for c in [
            "cod_ibge",
            "ehf_geocalor",
            "is_hw_day",
            "intensidade_ehf",
            "data_ehf_geocalor",
            "ehf_geocalor_idade_dias",
            "duracao_onda_ehf_dias",
            "ehf_fonte",
            "ehf_max_evento",
        ]
        if c in snap.columns
    ]
    out = out.merge(snap[bring].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")

    # Indicador composto: onda GeoCalor ativa (não substitui RIT nem nível)
    ehf_num = pd.to_numeric(out.get("ehf_geocalor"), errors="coerce")
    hw = pd.to_numeric(out.get("is_hw_day"), errors="coerce").fillna(0)
    ativa = (hw.gt(0) & ehf_num.fillna(0).gt(0)).astype(int)
    out["onda_geocalor_ativa"] = ativa
    sev = out.get("intensidade_ehf")
    if sev is not None:
        out["onda_geocalor_severidade"] = sev.where(ativa.eq(1), None)
    else:
        out["onda_geocalor_severidade"] = None

    if prefer_geocalor and "ehf_geocalor" in out.columns:
        geo = pd.to_numeric(out["ehf_geocalor"], errors="coerce")
        out["ehf"] = geo
        # stages / RIT leem ehf_adaptado — preferir GeoCalor quando válido
        if "ehf_adaptado" in out.columns:
            out["ehf_adaptado"] = geo.combine_first(pd.to_numeric(out["ehf_adaptado"], errors="coerce"))
        else:
            out["ehf_adaptado"] = geo
        # ehf_max para RIT quando houver evento
        if "ehf_max_evento" in out.columns:
            out["ehf_max"] = pd.to_numeric(out["ehf_max_evento"], errors="coerce").combine_first(geo)
        else:
            out["ehf_max"] = geo

    # duração de onda usada na persistência roxa
    d_geo = pd.to_numeric(out.get("duracao_onda_ehf_dias"), errors="coerce")
    if "duracao_onda_calor_dias" in out.columns:
        d_old = pd.to_numeric(out["duracao_onda_calor_dias"], errors="coerce")
        out["duracao_onda_calor_dias"] = pd.concat([d_old, d_geo], axis=1).max(axis=1)
    else:
        out["duracao_onda_calor_dias"] = d_geo

    return out


def geocalor_linhas_alerta(row: pd.Series | dict) -> list[str]:
    """Linhas curtas para texto de alerta municipal / Cuiabá."""
    r = row if isinstance(row, dict) else row.to_dict()
    ehf = r.get("ehf_geocalor")
    if ehf is None or (isinstance(ehf, float) and pd.isna(ehf)):
        ehf = r.get("ehf")
    if ehf is None or (isinstance(ehf, float) and pd.isna(ehf)):
        ehf = r.get("ehf_adaptado")
    if ehf is None or (isinstance(ehf, float) and pd.isna(ehf)):
        return []

    try:
        ehf_f = float(ehf)
    except (TypeError, ValueError):
        return []

    data = r.get("data_ehf_geocalor") or "—"
    idade = r.get("ehf_geocalor_idade_dias")
    idade_txt = f" · defasagem {int(idade)}d" if idade is not None and not (isinstance(idade, float) and pd.isna(idade)) else ""
    intens = str(r.get("intensidade_ehf") or "").strip()
    if intens.lower() in {"", "none", "nan", "—"}:
        intens = "—"
    hw = int(float(r.get("is_hw_day") or 0) or 0)
    dur = r.get("duracao_onda_ehf_dias")
    if dur is None or (isinstance(dur, float) and pd.isna(dur)):
        dur = r.get("duracao_onda_calor_dias")

    lines = [
        "GeoCalor / EHF:",
        f"- EHF {ehf_f:.2f} · intensidade {intens} · ref. {data}{idade_txt}",
    ]
    if hw and ehf_f > 0:
        lines.append("- Dia de onda de calor (sequência EHF>0 ≥ 3 dias)")
    try:
        if (
            ehf_f > 0
            and dur is not None
            and not (isinstance(dur, float) and pd.isna(dur))
            and float(dur) > 0
        ):
            lines.append(f"- Duração atual da onda (EHF): {int(float(dur))} dia(s)")
    except (TypeError, ValueError):
        pass
    if ehf_f > 0:
        lines.append("- Entra no RIT (domínio EHF) e na leitura de persistência térmica quando aplicável.")
    return lines
