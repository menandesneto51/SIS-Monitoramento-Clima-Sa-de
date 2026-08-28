# -*- coding: utf-8 -*-
"""Snapshot operacional null-safe para o boletim El Niño."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

_SNAP_MUN_COLS = [
    "municipio",
    "regional_saude",
    "nivel",
    "nivel_predicao_7d",
    "tmax",
    "umidade_media",
    "pm25_ugm3",
    "focos_queimadas_7d",
    "situacao_hidro",
    "tendencia_7d",
    "indice_prioridade_global",
]


_SECA_HIDRO = frozenset({"seca_baixa", "seca_moderada", "seca_alta"})
_INUND_HIDRO = frozenset({"inundacao_alta", "inundacao_moderada"})
_HABITUAL_HIDRO = frozenset({"normal"})


def _has_col(df: pd.DataFrame, col: str) -> bool:
    return df is not None and not df.empty and col in df.columns


def _hydro_facts(df: pd.DataFrame | None, n: int | None) -> dict[str, int]:
    """Único objeto hidrológico do boletim:  baixa + inundação + habitual = cobertura."""
    out = {
        "low_availability": 0,
        "flood_risk_high": 0,
        "habitual": 0,
        "coverage": 0,
        "state_total": int(n or 0),
    }
    if df is None or df.empty or "situacao_hidro" not in df.columns:
        return out
    s = df["situacao_hidro"]
    valid = s.notna() & ~s.astype(str).str.strip().str.lower().isin({"", "nan", "none", "—"})
    sl = s.astype(str).str.strip().str.lower()
    out["low_availability"] = int(sl[valid].isin(_SECA_HIDRO).sum())
    out["flood_risk_high"] = int(sl[valid].isin(_INUND_HIDRO).sum())
    out["habitual"] = int(sl[valid].isin(_HABITUAL_HIDRO).sum())
    out["coverage"] = int(valid.sum())
    return out


def _n_level(df: pd.DataFrame, *niveis: str) -> int | None:
    if not _has_col(df, "nivel"):
        return None
    s = df["nivel"].astype(str).str.lower().str.strip()
    return int(s.isin({n.lower() for n in niveis}).sum())


def _n_level_col(df: pd.DataFrame, col: str, *niveis: str) -> int | None:
    if not _has_col(df, col):
        return None
    s = df[col].astype(str).str.lower().str.strip()
    return int(s.isin({n.lower() for n in niveis}).sum())


def _median(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.median()) if s.notna().any() else None


def _mean(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.mean()) if s.notna().any() else None


def _sum(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.sum()) if s.notna().any() else None


def _count_ge(df: pd.DataFrame, col: str, limiar: float) -> int | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if not s.notna().any():
        return None
    return int((s >= limiar).sum())


def _count_le(df: pd.DataFrame, col: str, limiar: float) -> int | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    if not s.notna().any():
        return None
    return int((s <= limiar).sum())


def _p90(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.quantile(0.9)) if s.notna().any() else None


def _min(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.min()) if s.notna().any() else None


def _max(df: pd.DataFrame, col: str) -> float | None:
    if not _has_col(df, col):
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    return float(s.max()) if s.notna().any() else None


def _coverage(df: pd.DataFrame, col: str) -> int | None:
    if not _has_col(df, col):
        return None
    return int(df[col].notna().sum())


def _counts_norm(df: pd.DataFrame, col: str) -> dict[str, int] | None:
    if not _has_col(df, col):
        return None
    s = (
        df[col]
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({"": "—", "nan": "—", "none": "—"})
    )
    out = {str(k): int(v) for k, v in s.value_counts().to_dict().items()}
    return out or None


def _counts(df: pd.DataFrame, col: str) -> dict[str, int] | None:
    if not _has_col(df, col):
        return None
    s = df[col].astype(str).str.strip().replace({"": "—", "nan": "—", "None": "—"})
    out = {str(k): int(v) for k, v in s.value_counts().to_dict().items()}
    return out or None


def _series_num(df: pd.DataFrame, col: str) -> pd.Series | None:
    if not _has_col(df, col):
        return None
    return pd.to_numeric(df[col], errors="coerce")


def _sum_if(df: pd.DataFrame, col: str, mask: pd.Series) -> float | None:
    if not _has_col(df, col) or mask is None or len(mask) == 0:
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    sub = s[mask]
    return float(sub.sum()) if sub.notna().any() else None


def _mean_if(df: pd.DataFrame, col: str, mask: pd.Series) -> float | None:
    if not _has_col(df, col) or mask is None or len(mask) == 0:
        return None
    s = pd.to_numeric(df[col], errors="coerce")[mask]
    return float(s.mean()) if s.notna().any() else None


def _row_dict(row: pd.Series, cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in cols:
        if c not in row.index:
            continue
        val = row.get(c)
        out[c] = None if pd.isna(val) else val
    return out


def _extremo(df: pd.DataFrame, col: str, *, ascending: bool = False) -> dict[str, Any] | None:
    if not _has_col(df, col):
        return None
    work = df.copy()
    work["_v"] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["_v"])
    if work.empty:
        return None
    row = work.sort_values("_v", ascending=ascending).iloc[0]
    cols = [c for c in ["municipio", "regional_saude", col] if c in work.columns]
    return _row_dict(row, cols)


def _delta_nivel(atual: str, proj: str) -> str | None:
    """Compara classes ARARAS; retorna None se faltar pareamento válido."""
    a = STAGE_ORDER.get(str(atual or "").lower().strip())
    p = STAGE_ORDER.get(str(proj or "").lower().strip())
    if a is None or p is None or a < 0 or p < 0:
        return None
    d = p - a
    if d > 1:
        return "aumento_2plus"
    if d == 1:
        return "aumento_1"
    if d == 0:
        return "estabilidade"
    return "melhora"


def _tendencia_reg(sub: pd.DataFrame) -> str:
    """Agrega o delta municipal (atual → ~7d) na regional. Nunca publica coluna 100% vazia."""
    if sub is None or sub.empty or "nivel_predicao_7d" not in sub.columns:
        return "—"
    up = st = dn = un = 0
    seen: set[str] = set()
    for _, row in sub.iterrows():
        raw = "".join(ch for ch in str(row.get("cod_ibge") or "") if ch.isdigit())
        key = raw[:6] if len(raw) >= 6 else f"i{len(seen)}"
        if key in seen:
            continue
        seen.add(key)
        d = _delta_nivel(str(row.get("nivel", "")), str(row.get("nivel_predicao_7d", "")))
        if d is None:
            un += 1
        elif d == "melhora":
            dn += 1
        elif d == "estabilidade":
            st += 1
        else:
            up += 1
    if up + st + dn == 0:
        return "—"
    txt = f"↑ {up} · → {st}"
    if dn:
        txt += f" · ↓ {dn}"
    return txt


def merge_predicao_7d(resumo: pd.DataFrame, predicao: pd.DataFrame | None) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    out = resumo.copy()
    if predicao is None or predicao.empty or "cod_ibge" not in predicao.columns:
        return out
    pred = predicao.copy()
    # Reaplica regra canônica RISCO_TÉRMICO_PROJETADO quando há features (evita classe antiga no DB)
    feat_ok = all(c in pred.columns for c in ("tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d"))
    if feat_ok:
        from sisclima.engines.predicao_skill_7d import risco_termico_projetado

        term = pred.apply(lambda r: pd.Series(risco_termico_projetado(r)), axis=1)
        for c in term.columns:
            pred[c] = term[c]
    cols = [
        c
        for c in (
            "cod_ibge",
            "nivel_predicao_7d",
            "tendencia_7d",
            "tmax_max_7d",
            "utci_proxy_max_7d",
            "risco_cumulativo_3d_max_7d",
            "dias_onda_calor_prevista_7d",
            "risco_termico_projetado_0_100",
            "score_intensidade",
            "score_estresse",
            "score_persistencia",
            "score_onda",
            "fonte_predicao",
        )
        if c in pred.columns
    ]
    pred = pred[cols].drop_duplicates(subset=["cod_ibge"])
    if "cod_ibge" not in out.columns:
        return out
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    pred["cod_ibge"] = pred["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    out = out.merge(pred, on="cod_ibge", how="left", suffixes=("", "_pred"))
    if "tendencia_7d_pred" in out.columns and "tendencia_7d" not in out.columns:
        out["tendencia_7d"] = out["tendencia_7d_pred"]
    if "nivel_predicao_7d_pred" in out.columns:
        out["nivel_predicao_7d"] = out["nivel_predicao_7d_pred"].combine_first(out.get("nivel_predicao_7d"))
    return out


def _fire_facts(df: pd.DataFrame | None, n: int | None) -> dict[str, Any]:
    """Fatos de fogo: focos = AQUA_M-T; detecções = multi-satélite."""
    out: dict[str, Any] = {
        "coverage": None,
        "detected": None,
        "total": None,
        "deteccoes_total": None,
        "satelite_referencia": "AQUA_M-T",
        "coverage_is_detection": False,
        "n_zero_explicito": 0,
    }
    if df is None or df.empty or "focos_queimadas_7d" not in df.columns:
        return out
    s = pd.to_numeric(df["focos_queimadas_7d"], errors="coerce")
    n_obs = int(s.notna().sum())
    n_det = int((s.fillna(0) >= 1).sum()) if n_obs else 0
    n_zero = int((s == 0).sum())
    out["coverage"] = n_obs
    out["detected"] = n_det
    out["total"] = float(s.sum()) if n_obs else None
    out["n_zero_explicito"] = n_zero
    if "deteccoes_queimadas_7d" in df.columns:
        d = pd.to_numeric(df["deteccoes_queimadas_7d"], errors="coerce")
        if int(d.notna().sum()):
            out["deteccoes_total"] = float(d.sum())
    n_tot = int(n or 0)
    out["coverage_is_detection"] = bool(n_zero == 0 and n_obs > 0 and n_tot and n_obs < n_tot)
    return out


def _model_qa(df: pd.DataFrame | None, n: int | None, delta: dict[str, int] | None) -> dict[str, Any]:
    """QA interno de saturação/clipping/redundância — não publica números novos no PDF."""
    n_tot = int(n or 0)
    out: dict[str, Any] = {
        "MODEL_SATURATION_WARNING": False,
        "SCORE_CLIPPING_WARNING": False,
        "DRIVER_REDUNDANCY_WARNING": False,
        "projected_red_purple_pct": None,
        "upclass_pct": None,
        "score_dist": {},
        "driver_pct": {},
        "driver_matrix": [],
    }
    if df is None or df.empty or n_tot <= 0:
        return out
    proj = df["nivel_predicao_7d"].astype(str).str.lower().str.strip() if "nivel_predicao_7d" in df.columns else None
    n_rp = int(proj.isin({"vermelha", "roxa"}).sum()) if proj is not None else 0
    pct_rp = n_rp / n_tot
    out["projected_red_purple_pct"] = round(100.0 * pct_rp, 1)
    n_up = 0
    n_comp = 0
    if delta:
        n_up = int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
        n_comp = (
            int(delta.get("melhora") or 0)
            + int(delta.get("estabilidade") or 0)
            + int(delta.get("aumento_1") or 0)
            + int(delta.get("aumento_2plus") or 0)
        )
    up_pct = (n_up / n_comp) if n_comp else 0.0
    out["upclass_pct"] = round(100.0 * up_pct, 1)

    scores = pd.to_numeric(df.get("risco_termico_projetado_0_100"), errors="coerce") if "risco_termico_projetado_0_100" in df.columns else pd.Series(dtype=float)
    s = scores.dropna()
    if not s.empty:
        out["score_dist"] = {
            "min": float(s.min()),
            "p10": float(s.quantile(0.10)),
            "p25": float(s.quantile(0.25)),
            "mediana": float(s.median()),
            "p75": float(s.quantile(0.75)),
            "p90": float(s.quantile(0.90)),
            "max": float(s.max()),
            "n_100": int((s == 100).sum()),
            "n_ge_85": int((s >= 85).sum()),
            "n_ge_70": int((s >= 70).sum()),
            "n": int(len(s)),
        }
        out["SCORE_CLIPPING_WARNING"] = (s == 100).sum() >= max(1, 0.4 * len(s))

    # Agravadores para cobertura de driver
    agravados = df
    if "nivel" in df.columns and "nivel_predicao_7d" in df.columns:
        o_a = df["nivel"].astype(str).str.lower().map(STAGE_ORDER)
        o_p = df["nivel_predicao_7d"].astype(str).str.lower().map(STAGE_ORDER)
        mask_up = o_a.notna() & o_p.notna() & (o_p > o_a)
        agravados = df.loc[mask_up]
    n_agr = max(int(len(agravados)), 1)
    drivers = {
        "tmax37": ("tmax_max_7d", 37),
        "utci36": ("utci_proxy_max_7d", 36),
        "risco7": ("risco_cumulativo_3d_max_7d", 7),
        "onda1": ("dias_onda_calor_prevista_7d", 1),
    }
    pcts: dict[str, float] = {}
    for nome, (col, thr) in drivers.items():
        if col not in agravados.columns or agravados.empty:
            pcts[nome] = 0.0
            continue
        hit = int((pd.to_numeric(agravados[col], errors="coerce") >= thr).sum())
        pcts[nome] = hit / n_agr
    out["driver_pct"] = {k: round(100.0 * v, 1) for k, v in pcts.items()}
    driver_sat = any(v >= 0.95 for v in pcts.values())
    altos = [k for k, v in pcts.items() if v >= 0.90]
    out["DRIVER_REDUNDANCY_WARNING"] = len(altos) >= 2
    out["MODEL_SATURATION_WARNING"] = bool(pct_rp >= 0.95 or up_pct >= 0.70 or driver_sat)

    if "nivel" in df.columns and "nivel_predicao_7d" in df.columns:
        for dnome, (col, thr) in drivers.items():
            if col not in df.columns:
                continue
            hit = pd.to_numeric(df[col], errors="coerce") >= thr
            cruz = (
                df.loc[hit, ["nivel", "nivel_predicao_7d"]]
                .assign(_n=1)
                .groupby(["nivel", "nivel_predicao_7d"], dropna=False)
                .size()
                .reset_index(name="n")
            )
            for _, row in cruz.iterrows():
                out["driver_matrix"].append(
                    {
                        "driver": dnome,
                        "classe_atual": str(row.get("nivel") or ""),
                        "classe_projetada": str(row.get("nivel_predicao_7d") or ""),
                        "n": int(row.get("n") or 0),
                    }
                )
    return out


def snapshot_operacional(resumo: pd.DataFrame) -> dict[str, Any]:
    df = resumo if resumo is not None else pd.DataFrame()
    n = int(len(df))
    tem_recorte = n > 0

    nivel_counts = _counts(df, "nivel") if tem_recorte else None
    nivel_proj_counts = _counts_norm(df, "nivel_predicao_7d") if tem_recorte else None

    top: list[dict[str, Any]] = []
    regionais: list[dict[str, Any]] = []
    delta_resumo: dict[str, int] | None = None

    if tem_recorte:
        work = df.copy()
        rank = work["nivel"].astype(str).str.lower().map(STAGE_ORDER) if "nivel" in work.columns else 0
        work["_rk"] = pd.to_numeric(rank, errors="coerce").fillna(-1)
        if "indice_prioridade_global" in work.columns:
            work["_pri"] = pd.to_numeric(work["indice_prioridade_global"], errors="coerce")
            work = work.sort_values(["_rk", "_pri"], ascending=[False, False])
        else:
            work = work.sort_values("_rk", ascending=False)
        cols = [c for c in _SNAP_MUN_COLS if c in work.columns]
        for _, row in work.head(15).iterrows():
            top.append(_row_dict(row, cols))

        if "regional_saude" in work.columns:
            for nome, sub in work.groupby("regional_saude"):
                regionais.append(
                    {
                        "regional": str(nome or "—"),
                        "n": int(len(sub)),
                        "n_amarela_plus": _n_level(sub, "amarela", "laranja", "vermelha", "roxa"),
                        "n_laranja_plus": _n_level(sub, "laranja", "vermelha", "roxa"),
                        "n_vermelha_roxa": _n_level(sub, "vermelha", "roxa"),
                        "n_laranja": _n_level(sub, "laranja"),
                        "tmax_mediana": _median(sub, "tmax"),
                        "umidade_mediana": _median(sub, "umidade_media"),
                        "pm25_mediana": _median(sub, "pm25_ugm3"),
                        "focos_7d": _sum(sub, "focos_queimadas_7d"),
                        "tendencia_7d": _tendencia_reg(sub),
                    }
                )
            regionais.sort(
                key=lambda r: (
                    int(r.get("n_vermelha_roxa") or 0),
                    float(r.get("tmax_mediana") or 0),
                ),
                reverse=True,
            )

        if "nivel" in work.columns and "nivel_predicao_7d" in work.columns:
            delta: dict[str, int] = {
                "melhora": 0,
                "estabilidade": 0,
                "aumento_1": 0,
                "aumento_2plus": 0,
                "sem_pareamento": 0,
            }
            seen: set[str] = set()
            for _, row in work.iterrows():
                raw = "".join(ch for ch in str(row.get("cod_ibge") or "") if ch.isdigit())
                key = raw[:6] if len(raw) >= 6 else f"i{len(seen)}"
                if key in seen:
                    continue
                seen.add(key)
                d = _delta_nivel(str(row.get("nivel", "")), str(row.get("nivel_predicao_7d", "")))
                if d:
                    delta[d] += 1
                else:
                    delta["sem_pareamento"] += 1
            delta_resumo = delta

    data_ref = None
    for col in ("data_referencia", "data"):
        if col in df.columns and df[col].notna().any():
            data_ref = str(df[col].dropna().astype(str).iloc[0])[:10]
            break

    n_onda: int | None = None
    if "onda_calor_p95_2d" in df.columns and tem_recorte:
        flag = pd.to_numeric(df["onda_calor_p95_2d"], errors="coerce")
        if flag.notna().any():
            n_onda = int((flag.fillna(0) > 0).sum())

    tendencia_counts = _counts_norm(df, "tendencia_7d")
    n_subindo = int((tendencia_counts or {}).get("subindo", 0)) if tendencia_counts else None
    n_descendo = int((tendencia_counts or {}).get("descendo", 0)) if tendencia_counts else None
    n_crit = _n_level(df, "vermelha", "roxa")

    medidor: dict[str, Any] | None = None
    if tem_recorte and n_crit is not None and n_subindo is not None and n_descendo is not None:
        alvo_crit = int(round(n * 0.7))
        net_7d = float(n_subindo - n_descendo)
        taxa_dia = net_7d / 7.0 if net_7d != 0 else 0.0
        acima_ref = int(n_crit) >= int(alvo_crit)
        # ETA só é publicado quando houver robustez temporal (≥3 rodadas).
        # Nesta emissão o saldo tendência_7d é um único corte — sem histórico de rodadas.
        n_rodadas_temporais = 1
        eta_robusto = False
        if acima_ref:
            eta_dias = None
        else:
            faltam = max(0, alvo_crit - n_crit)
            eta_dias = (faltam / taxa_dia) if taxa_dia > 0 else None
            if eta_dias is not None:
                eta_dias = float(min(max(eta_dias, 0.0), 90.0))
            # Publicar ETA somente com ≥3 rodadas e tendência positiva consistente
            eta_robusto = bool(
                n_rodadas_temporais >= 3 and taxa_dia > 0 and eta_dias is not None and not acima_ref
            )
            if not eta_robusto:
                # Mantém o valor interno para confronto, mas marca como não publicável
                pass

        pm25_ge = _count_ge(df, "pm25_ugm3", 25)
        umi_le = _count_le(df, "umidade_media", 30)
        if pm25_ge is not None and umi_le is not None:
            score_tra = min(
                100.0,
                max(
                    0.0,
                    (100.0 * (n_crit / max(n, 1)))
                    + (25.0 * (n_subindo / max(n, 1)))
                    + (20.0 * (pm25_ge / max(n, 1)))
                    + (15.0 * (umi_le / max(n, 1))),
                ),
            )
            if acima_ref:
                classe_tra = "acima do referencial crítico"
            elif score_tra >= 75:
                classe_tra = "trajetória de agravamento"
            elif score_tra >= 55:
                classe_tra = "atenção alta"
            elif score_tra >= 35:
                classe_tra = "atenção moderada"
            else:
                classe_tra = "atenção baixa"
            medidor = {
                "alvo_critico_municipios": alvo_crit,
                "criticos_atuais": n_crit,
                "acima_referencial": acima_ref,
                "saldo_tendencia_7d": int(round(net_7d)),
                "taxa_dia_municipios": taxa_dia,
                "eta_critico_dias": eta_dias if eta_robusto else None,
                "eta_interno_dias": eta_dias,
                "eta_robusto": eta_robusto,
                "n_rodadas_temporais": n_rodadas_temporais,
                "score": score_tra,
                "classe": classe_tra,
                "disponivel": True,
            }
        else:
            medidor = {"disponivel": False}

    hf = _hydro_facts(df if tem_recorte else None, n if tem_recorte else None)
    ff = _fire_facts(df if tem_recorte else None, n if tem_recorte else None)
    mqa = _model_qa(df if tem_recorte else None, n if tem_recorte else None, delta_resumo)
    mask_alta_fumaca = None
    mask_calor_seco = None
    mask_hidro = None
    mask_arb = None
    if tem_recorte:
        pm = _series_num(df, "pm25_ugm3")
        if pm is not None:
            mask_alta_fumaca = pm >= 25
        tmax = _series_num(df, "tmax")
        umi = _series_num(df, "umidade_media")
        if tmax is not None and umi is not None:
            mask_calor_seco = (tmax >= 37) & (umi <= 30)
        if "situacao_hidro" in df.columns:
            sl_h = df["situacao_hidro"].astype(str).str.strip().str.lower()
            mask_hidro = sl_h.isin(_SECA_HIDRO)
        arb = _series_num(df, "casos_arbovirus_7d")
        if arb is not None:
            mask_arb = arb > 0

    monitoramento_agravos = {
        "respiratorio_fumaca": {
            "municipios_pm25_25": _count_ge(df, "pm25_ugm3", 25),
            "casos_srag_soma": int(round(_sum_if(df, "casos_srag", mask_alta_fumaca)))
            if _sum_if(df, "casos_srag", mask_alta_fumaca) is not None
            else None,
            "positividade_lacen_media_pct": _mean_if(df, "positividade_lacen_pct", mask_alta_fumaca),
            "obitos_total_soma": int(round(_sum_if(df, "obitos_total", mask_alta_fumaca)))
            if _sum_if(df, "obitos_total", mask_alta_fumaca) is not None
            else None,
        },
        "calor_desidratacao": {
            "municipios_calor_seco": int(mask_calor_seco.sum()) if mask_calor_seco is not None else None,
            "atendimentos_calor_soma": int(round(_sum_if(df, "atendimentos_calor", mask_calor_seco)))
            if _sum_if(df, "atendimentos_calor", mask_calor_seco) is not None
            else None,
            "n_onda_calor": n_onda,
        },
        "arboviroses_contexto_estiagem": {
            "municipios_com_casos_7d": int(mask_arb.sum()) if mask_arb is not None else None,
            "casos_arbovirus_7d_soma": int(round(_sum_if(df, "casos_arbovirus_7d", mask_arb)))
            if _sum_if(df, "casos_arbovirus_7d", mask_arb) is not None
            else None,
            "incidencia_media_100k": _mean_if(df, "incidencia_arbovirus_100k", mask_arb),
        },
        "hidrorelacionados": {
            "municipios_hidro_alerta": hf["low_availability"] if tem_recorte else None,
            "municipios_inundacao": hf["flood_risk_high"] if tem_recorte else None,
            "situacoes_hidro": _counts(df, "situacao_hidro"),
            "cobertura_hidro": hf["coverage"] if tem_recorte else None,
        },
    }

    return {
        "disponivel": tem_recorte,
        "n_municipios": n if tem_recorte else None,
        "data_referencia": data_ref,
        "n_vermelha_roxa": _n_level(df, "vermelha", "roxa"),
        "n_laranja": _n_level(df, "laranja"),
        "n_amarela": _n_level(df, "amarela"),
        "niveis": {str(k).lower(): int(v) for k, v in nivel_counts.items()} if nivel_counts else None,
        "niveis_projecao_7d": nivel_proj_counts,
        "delta_projecao": delta_resumo,
        "delta_n_comparavel": (
            int(
                (delta_resumo or {}).get("melhora", 0)
                + (delta_resumo or {}).get("estabilidade", 0)
                + (delta_resumo or {}).get("aumento_1", 0)
                + (delta_resumo or {}).get("aumento_2plus", 0)
            )
            if delta_resumo
            else None
        ),
        "delta_sem_pareamento": int((delta_resumo or {}).get("sem_pareamento", 0)) if delta_resumo else None,
        "n_agravadores": (
            int((delta_resumo or {}).get("aumento_1", 0) + (delta_resumo or {}).get("aumento_2plus", 0))
            if delta_resumo
            else None
        ),
        "tmax_mediana": _median(df, "tmax"),
        "tmax_min": _min(df, "tmax"),
        "tmax_max": _max(df, "tmax"),
        "tmax_p90": _p90(df, "tmax"),
        "tmax_media": _mean(df, "tmax"),
        "n_tmax_37": _count_ge(df, "tmax", 37),
        "cobertura_tmax": _coverage(df, "tmax"),
        "tmin_mediana": _median(df, "tmin"),
        "umidade_mediana": _median(df, "umidade_media"),
        "umidade_min": _min(df, "umidade_media"),
        "umidade_max": _max(df, "umidade_media"),
        "cobertura_umidade": _coverage(df, "umidade_media"),
        "n_umidade_30": _count_le(df, "umidade_media", 30),
        "precip_mediana": _median(df, "precipitacao_mm"),
        "n_sem_chuva": _count_le(df, "precipitacao_mm", 0),
        "utci_mediana": _median(df, "utci_proxy"),
        "utci_min": _min(df, "utci_proxy"),
        "utci_max": _max(df, "utci_proxy"),
        "n_utci_32": _count_ge(df, "utci_proxy", 32),
        "n_onda_calor": n_onda,
        "pm25_mediana": _median(df, "pm25_ugm3"),
        "pm25_min": _min(df, "pm25_ugm3"),
        "pm25_max": _max(df, "pm25_ugm3"),
        "pm25_p90": _p90(df, "pm25_ugm3"),
        "cobertura_pm25": _coverage(df, "pm25_ugm3"),
        "n_pm25_15": _count_ge(df, "pm25_ugm3", 15),
        "n_pm25_25": _count_ge(df, "pm25_ugm3", 25),
        "n_pm25_50": _count_ge(df, "pm25_ugm3", 50),
        "qualidade_ar": _counts(df, "qualidade_ar_nivel"),
        "focos_7d_total": _sum(df, "focos_queimadas_7d"),
        "focos_24h_total": _sum(df, "focos_queimadas_24h"),
        "deteccoes_7d_total": ff.get("deteccoes_total")
        if ff.get("deteccoes_total") is not None
        else _sum(df, "deteccoes_queimadas_7d"),
        "n_com_focos_7d": ff.get("detected"),
        "cobertura_focos": ff.get("coverage"),
        "satelite_focos": "AQUA_M-T",
        "solo_mediana": _median(df, "indice_saturacao_solo"),
        "solo_classes": _counts(df, "classe_saturacao_solo"),
        "hidro": _counts(df, "situacao_hidro"),
        "cobertura_hidro": hf["coverage"] if tem_recorte else None,
        "hydro_facts": hf,
        "fire_facts": ff,
        "model_qa": mqa,
        "evidencia_inundacao": bool(hf.get("flood_risk_high")),
        "tendencia_7d": tendencia_counts,
        "medidor_trajetoria": medidor,
        "agravos_monitorados": monitoramento_agravos,
        "prioritarios": top,
        "regionais": regionais,
        "extremos": {
            "tmax": _extremo(df, "tmax"),
            "pm25": _extremo(df, "pm25_ugm3"),
            "focos": _extremo(df, "focos_queimadas_7d"),
        },
    }
