# -*- coding: utf-8 -*-
"""Cobertura territorial: aldeia/quilombo/assentamento → CNES mais próximo.

Métrica operacional: quilômetros de TRAJETO (OSRM, perfil driving).
A linha reta (haversine) só pré-seleciona candidatos e entra como fallback
se o roteador falhar. Centroide municipal não entra no ranking.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from sisclima.core.config import SETTINGS, env
from sisclima.core.db import read_table, table_exists, write_df
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.cnes_geo import _corrige_lat_lon, coords_validas_mt
from sisclima.ingestion.vigibarragens import (
    CATEGORIA_ALDEIA,
    CATEGORIA_ASSENTAMENTO,
    CATEGORIA_QUILOMBO,
)

log = get_logger(__name__)

TABLE = "cobertura_territorio_cnes"
_FONTES_OFICIAIS = {"opendata_cnes", "dw_cnes"}
_GRUPOS_APS = {"aps"}
_GRUPOS_HOSP = {"hospital", "urgencia"}
_TERRITORIOS = {CATEGORIA_ALDEIA, CATEGORIA_QUILOMBO, CATEGORIA_ASSENTAMENTO}
LIMIAR_ROUTE_WARNING_KM = 300.0
LIMIAR_P90_VALIDACAO_KM = 300.0
LIMIAR_MAX_VALIDACAO_KM = 500.0
_INATIVO_RE = r"inativ|desativ|extint|baixad|fora de uso|não atende|nao atende"


def _cfg() -> dict:
    return SETTINGS.get("cobertura_territorio") or {}


def limiares_km() -> tuple[float, float]:
    cfg = _cfg()
    try:
        aps = float(cfg.get("aps_km", 30))
    except (TypeError, ValueError):
        aps = 30.0
    try:
        hosp = float(cfg.get("hospital_km", 50))
    except (TypeError, ValueError):
        hosp = 50.0
    return aps, hosp


def _usar_trajeto_padrao() -> bool:
    raw = env("COBERTURA_USAR_TRAJETO", "")
    if str(raw).strip():
        return str(raw).strip().lower() in {"1", "true", "sim", "yes"}
    return bool(_cfg().get("usar_trajeto", True))


def _k_candidatos() -> int:
    try:
        return max(1, int(_cfg().get("candidatos_k", 5)))
    except (TypeError, ValueError):
        return 5


def osrm_trajeto(
    lat_o: float,
    lon_o: float,
    destinos: Sequence[tuple[float, float]],
    *,
    base_url: str | None = None,
    perfil: str | None = None,
) -> list[tuple[float | None, float | None]]:
    """Trajeto da origem a cada destino: (km, minutos). OSRM table API."""
    n = len(destinos)
    vazio: list[tuple[float | None, float | None]] = [(None, None)] * n
    if not destinos:
        return []
    cfg = _cfg()
    base = (base_url or env("OSRM_URL", "") or cfg.get("osrm_url") or "https://router.project-osrm.org").rstrip("/")
    perfil = perfil or str(cfg.get("perfil") or "driving")
    coords = [f"{float(lon_o):.6f},{float(lat_o):.6f}"]
    coords += [f"{float(lon):.6f},{float(lat):.6f}" for lat, lon in destinos]
    dest_idx = ";".join(str(i) for i in range(1, n + 1))
    url = f"{base}/table/v1/{perfil}/{';'.join(coords)}"
    try:
        resp = http_get(
            url,
            params={"annotations": "distance,duration", "sources": "0", "destinations": dest_idx},
            timeout=20,
        )
        if resp.status_code >= 400:
            log.warning("OSRM HTTP %s", resp.status_code)
            return vazio
        payload = resp.json()
    except Exception as exc:
        log.warning("OSRM indisponível: %s", exc)
        return vazio
    dist = (payload or {}).get("distances") or []
    dur = (payload or {}).get("durations") or []
    row_d = dist[0] if dist else []
    row_t = dur[0] if dur else []
    out: list[tuple[float | None, float | None]] = []
    for i in range(n):
        metros = row_d[i] if i < len(row_d) else None
        segs = row_t[i] if i < len(row_t) else None
        km = None if metros is None else _metros_para_km(metros)
        mins = None if segs is None else round(float(segs) / 60.0, 0)
        out.append((km, mins))
    return out


def _metros_para_km(valor: Any) -> float:
    """OSRM table devolve metros. Valores já em km (>10 mil) são recusados como unidade errada."""
    v = float(valor)
    if v > 10_000:
        v = v / 1000.0
    return round(v, 1)


def osrm_trajeto_km(
    lat_o: float,
    lon_o: float,
    destinos: Sequence[tuple[float, float]],
    **kwargs,
) -> list[float | None]:
    """Compatibilidade: só os km do trajeto."""
    return [par[0] for par in osrm_trajeto(lat_o, lon_o, destinos, **kwargs)]


def _parse_rota(item) -> tuple[float | None, float | None]:
    """Aceita km, (km, min) ou dict — para testes e OSRM."""
    if item is None:
        return None, None
    if isinstance(item, dict):
        km = item.get("km")
        mins = item.get("min")
        return (None if km is None else float(km), None if mins is None else float(mins))
    if isinstance(item, (tuple, list)):
        km = item[0] if len(item) > 0 else None
        mins = item[1] if len(item) > 1 else None
        return (None if km is None else float(km), None if mins is None else float(mins))
    try:
        return float(item), None
    except (TypeError, ValueError):
        return None, None


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Distância em km. lat1/lon1 (n,) e lat2/lon2 (m,) → matriz (n, m)."""
    r = 6371.0
    a1 = np.radians(np.asarray(lat1, dtype=float))[:, None]
    o1 = np.radians(np.asarray(lon1, dtype=float))[:, None]
    a2 = np.radians(np.asarray(lat2, dtype=float))[None, :]
    o2 = np.radians(np.asarray(lon2, dtype=float))[None, :]
    dlat = a2 - a1
    dlon = o2 - o1
    h = np.sin(dlat / 2.0) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * r * np.arcsin(np.clip(np.sqrt(h), 0.0, 1.0))


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{7})", expand=False)


def _estabelecimento_ativo(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in ("ativo", "st_ativo", "situacao", "situacao_funcionamento", "descricao_situacao"):
        if col not in out.columns:
            continue
        s = out[col].astype(str).str.lower()
        inativo = s.str.contains(_INATIVO_RE, regex=True, na=False)
        if col in {"ativo", "st_ativo"}:
            inativo = inativo | s.isin({"0", "false", "nao", "não", "n"})
        out = out.loc[~inativo]
    return out


def _uf_mt(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if "cod_ibge" in out.columns:
        ibge = out["cod_ibge"].astype(str)
        mask = ibge.str.startswith("51") | ibge.isin({"", "nan", "None", "<NA>"})
        out = out.loc[mask]
    if "uf" in out.columns:
        uf = out["uf"].astype(str).str.upper()
        out = out.loc[uf.isin({"MT", "51", "", "NAN", "NONE"}) | out["uf"].isna()]
    return out


def unidades_oficiais(cnes: pd.DataFrame) -> pd.DataFrame:
    if cnes is None or cnes.empty:
        return pd.DataFrame()
    out = cnes.copy()
    if "fonte_coord" in out.columns:
        fonte = out["fonte_coord"].astype(str)
        out = out[fonte.isin(_FONTES_OFICIAIS)]
    out = _corrige_lat_lon(out)
    out = _estabelecimento_ativo(out)
    out = _uf_mt(out)
    out["lat"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lon"] = pd.to_numeric(out.get("lon"), errors="coerce")
    ok = coords_validas_mt(out["lat"], out["lon"])
    out = out.loc[ok].dropna(subset=["lat", "lon"])
    if "cnes" in out.columns:
        out = out.drop_duplicates("cnes", keep="first")
    return out


def _grupo(df: pd.DataFrame) -> pd.Series:
    if "grupo_tipo" in df.columns:
        return df["grupo_tipo"].astype(str)
    if "tipo_unidade" in df.columns:
        from sisclima.ingestion.cnes_geo import grupo_tipo

        return df["tipo_unidade"].map(grupo_tipo)
    return pd.Series("outros", index=df.index)


RouterFn = Callable[[float, float, Sequence[tuple[float, float]]], Sequence]


def _nearest(
    territorios: pd.DataFrame,
    unidades: pd.DataFrame,
    prefix: str,
    *,
    usar_trajeto: bool,
    k: int,
    roteador: RouterFn | None,
) -> pd.DataFrame:
    cols = {
        f"km_{prefix}": np.nan,
        f"km_{prefix}_linha_reta": np.nan,
        f"min_{prefix}": np.nan,
        f"metodo_{prefix}": pd.NA,
        f"cnes_{prefix}": pd.NA,
        f"nome_{prefix}": pd.NA,
        f"tipo_{prefix}": pd.NA,
        f"rota_valida_{prefix}": False,
        f"fallback_geodesico_ok_{prefix}": False,
    }
    out = pd.DataFrame(cols, index=territorios.index)
    if territorios.empty or unidades.empty:
        return out
    dist = haversine_km(
        territorios["lat"].to_numpy(),
        territorios["lon"].to_numpy(),
        unidades["lat"].to_numpy(),
        unidades["lon"].to_numpy(),
    )
    k = max(1, min(int(k), dist.shape[1]))
    order = np.argsort(dist, axis=1)[:, :k]
    router = roteador or osrm_trajeto
    nome_col = "nome_unidade" if "nome_unidade" in unidades.columns else None
    tipo_col = "tipo_unidade" if "tipo_unidade" in unidades.columns else None
    cnes_col = "cnes" if "cnes" in unidades.columns else None
    units = unidades.reset_index(drop=True)

    for i, terr_idx in enumerate(territorios.index):
        cand_pos = order[i]
        reta = dist[i, cand_pos]
        best_pos = int(cand_pos[0])
        best_km = float(reta[0]) if np.isfinite(reta[0]) else np.nan
        best_min: float | None = None
        metodo = "linha_reta"
        if usar_trajeto:
            dests = [(float(units.iloc[int(p)]["lat"]), float(units.iloc[int(p)]["lon"])) for p in cand_pos]
            rotas = list(router(float(territorios.iloc[i]["lat"]), float(territorios.iloc[i]["lon"]), dests))
            melhores: list[tuple[float, float | None, int]] = []
            for j, item in enumerate(rotas):
                km_r, mins = _parse_rota(item)
                if km_r is None:
                    continue
                melhores.append((float(km_r), mins, int(cand_pos[j])))
            if melhores:
                best_km, best_min, best_pos = min(melhores, key=lambda t: t[0])
                metodo = "trajeto"
                reta0 = float(reta[0]) if np.isfinite(reta[0]) else None
                if reta0 is not None and best_km > 2000 and reta0 < 400:
                    best_km = best_km / 1000.0
        if not np.isfinite(best_km):
            continue
        picked = units.iloc[best_pos]
        reta_km = float(reta[0]) if np.isfinite(reta[0]) else np.nan
        rota_ok = metodo == "trajeto" and np.isfinite(best_km) and float(best_km) > 0
        if rota_ok and np.isfinite(reta_km) and float(best_km) > max(LIMIAR_ROUTE_WARNING_KM, 4 * reta_km):
            rota_ok = False
        fallback_ok = metodo == "linha_reta" and np.isfinite(best_km) and 0 < float(best_km) <= LIMIAR_ROUTE_WARNING_KM
        out.at[terr_idx, f"km_{prefix}"] = round(float(best_km), 1)
        out.at[terr_idx, f"km_{prefix}_linha_reta"] = round(reta_km, 1) if np.isfinite(reta_km) else np.nan
        out.at[terr_idx, f"min_{prefix}"] = round(float(best_min), 0) if best_min is not None else np.nan
        out.at[terr_idx, f"metodo_{prefix}"] = metodo
        out.at[terr_idx, f"rota_valida_{prefix}"] = bool(rota_ok)
        out.at[terr_idx, f"fallback_geodesico_ok_{prefix}"] = bool(fallback_ok)
        if cnes_col:
            out.at[terr_idx, f"cnes_{prefix}"] = picked[cnes_col]
        if nome_col:
            out.at[terr_idx, f"nome_{prefix}"] = picked[nome_col]
        if tipo_col:
            out.at[terr_idx, f"tipo_{prefix}"] = picked[tipo_col]
    return out


def calcular_cobertura(
    territorios: pd.DataFrame,
    cnes: pd.DataFrame,
    resumo: pd.DataFrame | None = None,
    *,
    aps_km: float | None = None,
    hospital_km: float | None = None,
    usar_trajeto: bool | None = None,
    roteador: RouterFn | None = None,
    candidatos_k: int | None = None,
) -> pd.DataFrame:
    lim_aps, lim_hosp = limiares_km()
    if aps_km is not None:
        lim_aps = float(aps_km)
    if hospital_km is not None:
        lim_hosp = float(hospital_km)
    if usar_trajeto is None:
        usar_trajeto = _usar_trajeto_padrao()
    k = candidatos_k if candidatos_k is not None else _k_candidatos()

    if territorios is None or territorios.empty:
        return pd.DataFrame()
    terr = territorios.copy()
    if "categoria" in terr.columns:
        terr = terr[terr["categoria"].isin(_TERRITORIOS)]
    terr = _corrige_lat_lon(terr)
    ok_orig = coords_validas_mt(terr["lat"], terr["lon"])
    terr = terr.loc[ok_orig].dropna(subset=["lat", "lon"])
    if terr.empty:
        return pd.DataFrame()
    if "cod_ibge" in terr.columns:
        terr["cod_ibge"] = _ibge7(terr["cod_ibge"])
    terr = terr.drop_duplicates(subset=[c for c in ("nome", "lat", "lon", "cod_ibge") if c in terr.columns])

    units = unidades_oficiais(cnes)
    grupos = _grupo(units) if not units.empty else pd.Series(dtype=str)
    aps = units[grupos.isin(_GRUPOS_APS)] if not units.empty else pd.DataFrame()
    hosp = units[grupos.isin(_GRUPOS_HOSP)] if not units.empty else pd.DataFrame()

    near_aps = _nearest(terr, aps, "aps", usar_trajeto=bool(usar_trajeto), k=k, roteador=roteador)
    near_hosp = _nearest(terr, hosp, "hospital", usar_trajeto=bool(usar_trajeto), k=k, roteador=roteador)
    cob = pd.concat([terr.reset_index(drop=True), near_aps.reset_index(drop=True), near_hosp.reset_index(drop=True)], axis=1)
    cob["longe_aps"] = pd.to_numeric(cob["km_aps"], errors="coerce") > lim_aps
    cob["longe_hospital"] = pd.to_numeric(cob["km_hospital"], errors="coerce") > lim_hosp
    cob.loc[cob["km_aps"].isna(), "longe_aps"] = False
    cob.loc[cob["km_hospital"].isna(), "longe_hospital"] = False
    cob["longe_rede"] = cob["longe_aps"] | cob["longe_hospital"]
    cob["aps_km_limiar"] = lim_aps
    cob["hospital_km_limiar"] = lim_hosp
    rota = pd.to_numeric(cob["km_aps"], errors="coerce")
    reta = pd.to_numeric(cob.get("km_aps_linha_reta"), errors="coerce")
    cob["alerta_distancia_rota"] = (rota > LIMIAR_ROUTE_WARNING_KM) | (
        (rota.notna() & reta.notna()) & (rota > reta * 4) & (rota > 150)
    )
    n_warn = int(cob["alerta_distancia_rota"].fillna(False).sum())
    if n_warn:
        log.warning("ROUTE_DISTANCE_WARNING n=%s (km_aps>300 ou rota>>linha reta)", n_warn)
    cob["exige_validacao_aps"] = (rota > LIMIAR_MAX_VALIDACAO_KM) | cob["alerta_distancia_rota"].fillna(False)

    if resumo is not None and not resumo.empty and "cod_ibge" in resumo.columns and "cod_ibge" in cob.columns:
        r = resumo.copy()
        r["cod_ibge"] = _ibge7(r["cod_ibge"])
        keep = [c for c in ["cod_ibge", "nivel", "nivel_predicao_7d", "regional_saude"] if c in r.columns]
        r = r[keep].drop_duplicates("cod_ibge")
        cob = cob.merge(r, on="cod_ibge", how="left", suffixes=("", "_r"))
        if "municipio" not in cob.columns and "municipio_r" in cob.columns:
            cob["municipio"] = cob["municipio_r"]
    cob["atualizado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = [
        c
        for c in [
            "nome",
            "categoria",
            "municipio",
            "cod_ibge",
            "regional_saude",
            "nivel",
            "nivel_predicao_7d",
            "lat",
            "lon",
            "km_aps",
            "km_aps_linha_reta",
            "min_aps",
            "metodo_aps",
            "cnes_aps",
            "nome_aps",
            "tipo_aps",
            "rota_valida_aps",
            "fallback_geodesico_ok_aps",
            "km_hospital",
            "km_hospital_linha_reta",
            "min_hospital",
            "metodo_hospital",
            "cnes_hospital",
            "nome_hospital",
            "tipo_hospital",
            "rota_valida_hospital",
            "fallback_geodesico_ok_hospital",
            "longe_aps",
            "longe_hospital",
            "longe_rede",
            "alerta_distancia_rota",
            "exige_validacao_aps",
            "aps_km_limiar",
            "hospital_km_limiar",
            "atualizado_em",
        ]
        if c in cob.columns
    ]
    return cob[keep]


def persistir_cobertura(resumo: pd.DataFrame | None = None) -> pd.DataFrame:
    terr = pd.DataFrame()
    if table_exists("vigibarragens_populacoes"):
        terr = read_table("vigibarragens_populacoes")
    if (terr is None or terr.empty) and table_exists("vigibarragens_populacoes"):
        terr = read_table("vigibarragens_populacoes")
    cnes = read_table("cnes_unidades_geo") if table_exists("cnes_unidades_geo") else pd.DataFrame()
    cob = calcular_cobertura(terr, cnes, resumo)
    if not cob.empty:
        write_df(cob, TABLE)
        log.info("Cobertura território-CNES: %s pontos", len(cob))
    return cob


def load_cobertura() -> pd.DataFrame:
    if not table_exists(TABLE):
        return pd.DataFrame()
    df = read_table(TABLE)
    return df if df is not None else pd.DataFrame()
