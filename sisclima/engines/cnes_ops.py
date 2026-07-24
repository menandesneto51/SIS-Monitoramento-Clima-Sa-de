from __future__ import annotations

import numpy as np
import pandas as pd

from sisclima.utils.io import normalize_cols
from sisclima.utils.municipios import ensure_municipality, municipality_cols


def _pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    # contains match
    for name in candidates:
        key = name.lower()
        for col_l, col in lower.items():
            if key in col_l:
                return col
    return None


def _cod_ibge_series(df: pd.DataFrame) -> pd.Series:
    col = _pick_col(
        df,
        [
            "cod_ibge",
            "estabelecimentomunicipiocodigo",
            "codigomunicipioresidencia",
            "codmunicipio",
            "ibge",
            "codigoibge",
        ],
    )
    if col is None:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="object")
    s = (
        df[col]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.extract(r"(\d+)", expand=False)
        .fillna("")
        .str.zfill(7)
    )
    s = s.where(s.str.len() >= 6, np.nan)
    return s


def _municipio_series(df: pd.DataFrame) -> pd.Series:
    col = _pick_col(
        df,
        [
            "municipio",
            "estabelecimentomunicipionome",
            "municipioresidencia",
            "nomemunicipio",
        ],
    )
    if col is None:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[col].astype(str)


def _qty_series(df: pd.DataFrame, candidates: list[str], default: float = 1.0) -> pd.Series:
    col = _pick_col(df, candidates)
    if col is None:
        return pd.Series([default] * len(df), index=df.index, dtype="float")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _flag_equipamento(df: pd.DataFrame, tokens: list[str]) -> pd.Series:
    text_cols = [
        c
        for c in df.columns
        if any(k in str(c).lower() for k in ("equip", "descr", "tipo", "nome"))
    ]
    if not text_cols:
        return pd.Series([0] * len(df), index=df.index, dtype="int")
    blob = df[text_cols].astype(str).agg(" ".join, axis=1).str.lower()
    mask = False
    for tok in tokens:
        mask = mask | blob.str.contains(tok, na=False)
    return mask.astype(int)


def aggregate_cnes_municipal(
    estabelecimentos: pd.DataFrame | None = None,
    leitos: pd.DataFrame | None = None,
    equipamentos: pd.DataFrame | None = None,
    equipes: pd.DataFrame | None = None,
    profissionais: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Agrega capacidade CNES municipal para resiliência operacional."""
    frames: list[pd.DataFrame] = []

    if estabelecimentos is not None and not estabelecimentos.empty:
        est = normalize_cols(estabelecimentos.copy())
        est["cod_ibge"] = _cod_ibge_series(est)
        est["municipio"] = _municipio_series(est)
        qtd = _qty_series(est, ["qtdestabelecimento", "qtd_estabelecimento", "quantidade"], 1.0)
        g = (
            est.assign(_q=qtd)
            .groupby(["cod_ibge", "municipio"], dropna=False, as_index=False)
            .agg(cnes_estabelecimentos_total=("_q", "sum"))
        )
        frames.append(g)

    if leitos is not None and not leitos.empty:
        lei = normalize_cols(leitos.copy())
        lei["cod_ibge"] = _cod_ibge_series(lei)
        lei["municipio"] = _municipio_series(lei)
        qtd = _qty_series(lei, ["leitos_existentes", "qtdexistente", "leitos_sus", "qtdsus", "leitos_total"], 0.0)
        g = (
            lei.assign(_q=qtd)
            .groupby(["cod_ibge", "municipio"], dropna=False, as_index=False)
            .agg(cnes_leitos_total=("_q", "sum"))
        )
        frames.append(g)

    if equipamentos is not None and not equipamentos.empty:
        eq = normalize_cols(equipamentos.copy())
        eq["cod_ibge"] = _cod_ibge_series(eq)
        eq["municipio"] = _municipio_series(eq)
        qtd = _qty_series(eq, ["qtd_equipamento", "qtdexistente", "quantidade", "qtdequipamento"], 1.0)
        flag_vent = _flag_equipamento(eq, ["ventil", "respirad"])
        flag_mon = _flag_equipamento(eq, ["monitor"])
        g = (
            eq.assign(_q=qtd, _v=flag_vent, _m=flag_mon)
            .groupby(["cod_ibge", "municipio"], dropna=False, as_index=False)
            .agg(
                cnes_equipamentos_total=("_q", "sum"),
                flag_ventilador=("_v", "sum"),
                flag_monitor=("_m", "sum"),
            )
        )
        frames.append(g)

    prof_src = profissionais if profissionais is not None and not profissionais.empty else equipes
    if prof_src is not None and not prof_src.empty:
        pr = normalize_cols(prof_src.copy())
        pr["cod_ibge"] = _cod_ibge_series(pr)
        pr["municipio"] = _municipio_series(pr)
        qtd = _qty_series(
            pr,
            [
                "qtd_profissional",
                "qtdprofissional",
                "quantidadeprofissionais",
                "qtd_equipe",
                "qtdequipe",
                "quantidade",
            ],
            1.0,
        )
        g = (
            pr.assign(_q=qtd)
            .groupby(["cod_ibge", "municipio"], dropna=False, as_index=False)
            .agg(cnes_profissionais_total=("_q", "sum"))
        )
        frames.append(g)

    if not frames:
        return pd.DataFrame(
            columns=[
                "cod_ibge",
                "municipio",
                "cnes_estabelecimentos_total",
                "cnes_leitos_total",
                "cnes_equipamentos_total",
                "cnes_profissionais_total",
                "flag_ventilador",
                "flag_monitor",
                "indice_capacidade_cnes",
                "fonte_operacional_cnes",
            ]
        )

    out = frames[0]
    for fr in frames[1:]:
        keys = [k for k in ("cod_ibge", "municipio") if k in out.columns and k in fr.columns]
        if "cod_ibge" in keys:
            keys = ["cod_ibge"]
            fr = fr.drop(columns=[c for c in ("municipio",) if c in fr.columns and c in out.columns], errors="ignore")
        out = out.merge(fr, on=keys, how="outer")

    out = ensure_municipality(out)
    for c in [
        "cnes_estabelecimentos_total",
        "cnes_leitos_total",
        "cnes_equipamentos_total",
        "cnes_profissionais_total",
        "flag_ventilador",
        "flag_monitor",
    ]:
        if c not in out.columns:
            out[c] = 0.0
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

    # Índice 0-100: média de percentis relativos entre municípios (capacidade instalada).
    def _pct_rank(s: pd.Series) -> pd.Series:
        if s.isna().all() or float(s.max()) == float(s.min()):
            return pd.Series([50.0] * len(s), index=s.index)
        return (s.rank(method="average", pct=True) * 100).clip(0, 100)

    out["indice_capacidade_cnes"] = (
        0.35 * _pct_rank(out["cnes_leitos_total"])
        + 0.25 * _pct_rank(out["cnes_estabelecimentos_total"])
        + 0.20 * _pct_rank(out["cnes_equipamentos_total"])
        + 0.20 * _pct_rank(out["cnes_profissionais_total"])
    ).round(2)
    out["fonte_operacional_cnes"] = "DW_CNES"
    cols = [
        "cod_ibge",
        "municipio",
        "cnes_estabelecimentos_total",
        "cnes_leitos_total",
        "cnes_equipamentos_total",
        "cnes_profissionais_total",
        "flag_ventilador",
        "flag_monitor",
        "indice_capacidade_cnes",
        "fonte_operacional_cnes",
    ]
    return out[cols].drop_duplicates(subset=["cod_ibge"], keep="first")
