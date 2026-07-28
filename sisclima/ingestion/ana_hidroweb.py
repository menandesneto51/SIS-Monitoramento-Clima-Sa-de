# -*- coding: utf-8 -*-
"""Ingestão ANA — estações telemétricas e séries hidrometeorológicas (MT).

Fontes:
- SOAP público: https://telemetriaws1.ana.gov.br/ServiceANA.asmx
  - ListaEstacoesTelemetricas
  - DadosHidrometeorologicos
- Opcional REST HidroWebService (Bearer token): ANA_HIDROWEB_TOKEN
- Fallback CSV: data/input/ana_estacoes_mt.csv e ana_telemetria.csv
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from sisclima.core.config import APP_CONFIG, ROOT, as_bool, env
from sisclima.core.http_client import USER_AGENT, ssl_verify
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols, read_table_safe

log = get_logger(__name__)

SOAP_BASE = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
REST_BASE = "https://www.ana.gov.br/hidrowebservice"


def _session() -> requests.Session:
    """Sessão ANA com User-Agent institucional (sem stealth)."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"})
    s.verify = ssl_verify("ANA_SSL_VERIFY", True)
    return s


def _parse_dataset_xml(xml_text: str) -> pd.DataFrame:
    root = ET.fromstring(xml_text)
    rows = []
    for el in root.iter():
        if el.tag.endswith("Table"):
            row = {child.tag.split("}")[-1]: child.text for child in list(el)}
            if row:
                rows.append(row)
    return pd.DataFrame(rows)


def _root_path(value: str | None, default: str) -> Path:
    p = Path(value or default)
    return p if p.is_absolute() else ROOT / p


def parse_municipio_uf(text: str) -> tuple[str, str]:
    t = str(text or "").strip()
    if "-" in t:
        mun, uf = t.rsplit("-", 1)
        return mun.strip(), uf.strip().upper()
    if "/" in t:
        mun, uf = t.rsplit("/", 1)
        return mun.strip(), uf.strip().upper()
    return t, ""


def fetch_ana_estacoes_telemetricas(uf: str | None = None) -> pd.DataFrame:
    """Lista estações telemétricas ANA; filtra UF (padrão MT)."""
    if not as_bool(env("USE_ANA", "true"), True):
        return pd.DataFrame()
    uf = (uf or env("ANA_UF") or APP_CONFIG.uf or "MT").strip().upper()
    try:
        r = _session().get(
            f"{SOAP_BASE}/ListaEstacoesTelemetricas",
            params={"statusEstacoes": "0", "Origem": ""},
            timeout=int(env("ANA_TIMEOUT_SECONDS", "90") or 90),
            verify=ssl_verify("ANA_SSL_VERIFY", True),
        )
        r.raise_for_status()
        df = _parse_dataset_xml(r.text)
    except Exception as exc:
        log.warning("Falha ao listar estações ANA: %s", exc)
        return pd.DataFrame()

    if df.empty:
        return df

    # NÃO usar normalize_cols antes de mapear nomes originais do SOAP
    colmap = {c.lower().replace("-", "_").replace(" ", "_"): c for c in df.columns}

    def col(*names):
        for n in names:
            key = n.lower().replace("-", "_")
            if key in colmap:
                return colmap[key]
            for k, orig in colmap.items():
                if key in k:
                    return orig
        return None

    c_cod = col("CodEstacao", "codigo_estacao")
    c_nome = col("NomeEstacao", "nome_estacao")
    c_munuf = col("Municipio-UF", "Municipio_UF", "municipio_uf")
    c_lat = col("Latitude", "lat")
    c_lon = col("Longitude", "lon")
    c_rio = col("NomeRio", "nome_rio")

    out = pd.DataFrame()
    out["codigo_estacao"] = df[c_cod].astype(str) if c_cod else ""
    out["nome_estacao"] = df[c_nome].astype(str) if c_nome else ""
    munuf = df[c_munuf].astype(str) if c_munuf else pd.Series([""] * len(df))
    parsed = munuf.map(parse_municipio_uf)
    out["municipio"] = [p[0] for p in parsed]
    out["uf"] = [p[1] for p in parsed]
    out["lat"] = pd.to_numeric(df[c_lat], errors="coerce") if c_lat else pd.NA
    out["lon"] = pd.to_numeric(df[c_lon], errors="coerce") if c_lon else pd.NA
    out["nome_rio"] = df[c_rio].astype(str) if c_rio else ""
    if uf and uf not in {"*", "BR", "ALL"}:
        out = out[out["uf"].astype(str).str.upper().eq(uf)].copy()
    out["fonte"] = "ANA_TELEMETRIA"
    return out.reset_index(drop=True)


def map_estacoes_to_ibge(estacoes: pd.DataFrame, municipios: pd.DataFrame | None = None) -> pd.DataFrame:
    import unicodedata

    def key(s: str) -> str:
        t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
        return t.lower().strip()

    out = estacoes.copy() if estacoes is not None else pd.DataFrame()
    if out.empty:
        return out
    if "cod_ibge" not in out.columns:
        out["cod_ibge"] = pd.NA
    if municipios is None or municipios.empty or "municipio" not in municipios.columns:
        return out
    mun = municipios.copy()
    mun["_k"] = mun["municipio"].map(key)
    out["_k"] = out["municipio"].map(key)
    keep = ["_k"] + [c for c in ["cod_ibge", "municipio"] if c in mun.columns]
    mapped = out.merge(mun[keep].drop_duplicates("_k"), on="_k", how="left", suffixes=("", "_ibge"))
    if "cod_ibge_ibge" in mapped.columns:
        mapped["cod_ibge"] = mapped["cod_ibge"].fillna(mapped["cod_ibge_ibge"])
    if "municipio_ibge" in mapped.columns:
        mapped["municipio"] = mapped["municipio"].where(mapped["municipio"].astype(str).str.len() > 0, mapped["municipio_ibge"])
    return mapped.drop(columns=[c for c in mapped.columns if c.endswith("_ibge") or c == "_k"], errors="ignore")


def fetch_ana_serie_estacao(codigo_estacao: str, days: int = 7) -> pd.DataFrame:
    """Busca série hidrometeorológica recente de uma estação (SOAP)."""
    fim = date.today()
    ini = fim - timedelta(days=max(1, days))
    try:
        r = _session().get(
            f"{SOAP_BASE}/DadosHidrometeorologicos",
            params={
                "codEstacao": str(codigo_estacao),
                "dataInicio": ini.strftime("%d/%m/%Y"),
                "dataFim": fim.strftime("%d/%m/%Y"),
            },
            timeout=int(env("ANA_TIMEOUT_SECONDS", "90") or 90),
            verify=ssl_verify("ANA_SSL_VERIFY", True),
        )
        r.raise_for_status()
        df = _parse_dataset_xml(r.text)
    except Exception as exc:
        log.warning("Falha série ANA %s: %s", codigo_estacao, exc)
        return pd.DataFrame()

    if df.empty or "Error" in df.columns:
        return pd.DataFrame()

    df = normalize_cols(df)
    df["codigo_estacao"] = str(codigo_estacao)
    # campos comuns observados / aliases
    rename = {}
    for a, b in [
        ("chuva", "chuva_mm"),
        ("precipitacao", "chuva_mm"),
        ("cota", "cota_cm"),
        ("vazao", "vazao_m3s"),
        ("datahora", "data_hora"),
        ("data_hora_medicao", "data_hora"),
        ("datamedicao", "data_hora"),
    ]:
        if a in df.columns:
            rename[a] = b
    df = df.rename(columns=rename)
    # fuzzy match remaining
    for c in list(df.columns):
        cl = c.lower()
        if "chuva" in cl or "precip" in cl:
            df = df.rename(columns={c: "chuva_mm"})
        elif "cota" in cl:
            df = df.rename(columns={c: "cota_cm"})
        elif "vazao" in cl or "vazão" in cl:
            df = df.rename(columns={c: "vazao_m3s"})
        elif "data" in cl and "hora" in cl:
            df = df.rename(columns={c: "data_hora"})
    if "data_hora" in df.columns:
        df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce", dayfirst=True)
        df["data"] = df["data_hora"].dt.date.astype(str)
    for c in ["chuva_mm", "cota_cm", "vazao_m3s"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fonte"] = "ANA_SOAP"
    return df


def fetch_ana_telemetria_mt(
    estacoes: pd.DataFrame | None = None,
    max_estacoes: int | None = None,
    days: int = 7,
) -> pd.DataFrame:
    """Consulta séries de um subconjunto de estações MT."""
    if not as_bool(env("USE_ANA", "true"), True):
        return pd.DataFrame()
    if estacoes is None or estacoes.empty:
        estacoes = fetch_ana_estacoes_telemetricas()
    if estacoes.empty or "codigo_estacao" not in estacoes.columns:
        return pd.DataFrame()

    max_env = env("ANA_MAX_ESTACOES")
    if max_estacoes is None and max_env:
        try:
            max_estacoes = int(max_env)
        except Exception:
            max_estacoes = 15
    if max_estacoes is None:
        max_estacoes = 15

    codes = estacoes["codigo_estacao"].astype(str).drop_duplicates().head(max_estacoes).tolist()
    frames = []
    for i, cod in enumerate(codes):
        serie = fetch_ana_serie_estacao(cod, days=days)
        if serie.empty:
            continue
        meta = estacoes[estacoes["codigo_estacao"].astype(str).eq(cod)].head(1)
        for col in ["municipio", "cod_ibge", "nome_estacao", "lat", "lon", "uf"]:
            if col in meta.columns:
                serie[col] = meta.iloc[0][col]
        frames.append(serie)
        time.sleep(0.2)
        if (i + 1) % 5 == 0:
            log.info("ANA telemetria: %s/%s estações", i + 1, len(codes))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_ana_csv_fallback() -> tuple[pd.DataFrame, pd.DataFrame]:
    est_path = _root_path(env("ANA_ESTACOES_CSV"), "data/input/ana_estacoes_mt.csv")
    tel_path = _root_path(env("ANA_TELEMETRIA_CSV"), "data/input/ana_telemetria.csv")
    est = read_table_safe(est_path) if est_path.exists() else pd.DataFrame()
    tel = read_table_safe(tel_path) if tel_path.exists() else pd.DataFrame()
    if est.empty:
        sample = ROOT / "data" / "sample" / "ana_estacoes_mt.csv"
        if sample.exists():
            est = read_table_safe(sample)
    if tel.empty:
        sample = ROOT / "data" / "sample" / "ana_telemetria.csv"
        if sample.exists():
            tel = read_table_safe(sample)
    return normalize_cols(est) if not est.empty else est, normalize_cols(tel) if not tel.empty else tel


def ana_risco_municipal(telemetria: pd.DataFrame) -> pd.DataFrame:
    """Agrega chuva/cota por município/dia e gera flags operacionais simples."""
    if telemetria is None or telemetria.empty:
        return pd.DataFrame()
    df = telemetria.copy()
    if "data" not in df.columns and "data_hora" in df.columns:
        df["data"] = pd.to_datetime(df["data_hora"], errors="coerce").dt.date.astype(str)
    if "data" not in df.columns:
        return pd.DataFrame()

    for c in ["chuva_mm", "cota_cm", "vazao_m3s"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    keys = [c for c in ["data", "cod_ibge", "municipio"] if c in df.columns]
    if not keys:
        return pd.DataFrame()

    agg = {"chuva_mm": "sum", "cota_cm": "max", "vazao_m3s": "max"}
    use = {k: v for k, v in agg.items() if k in df.columns}
    g = df.groupby(keys, as_index=False).agg(use)

    # limiares configuráveis
    chuva_amarela = float(env("ANA_CHUVA_AMARELA_MM", "30") or 30)
    chuva_laranja = float(env("ANA_CHUVA_LARANJA_MM", "50") or 50)
    chuva_vermelha = float(env("ANA_CHUVA_VERMELHA_MM", "80") or 80)
    if "chuva_mm" in g.columns:
        g["nivel_chuva"] = "verde"
        g.loc[g["chuva_mm"] >= chuva_amarela, "nivel_chuva"] = "amarela"
        g.loc[g["chuva_mm"] >= chuva_laranja, "nivel_chuva"] = "laranja"
        g.loc[g["chuva_mm"] >= chuva_vermelha, "nivel_chuva"] = "vermelha"
        g["precipitacao_mm"] = g["chuva_mm"]
    g["fonte"] = "ANA"
    return g


def load_ana_bundle(municipios: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Carrega inventário + telemetria ANA (API) com fallback CSV."""
    prefer_csv = not as_bool(env("ANA_FETCH_SERIES", "true"), True)
    est = pd.DataFrame()
    tel = pd.DataFrame()

    if prefer_csv:
        est_csv, tel_csv = load_ana_csv_fallback()
        est = map_estacoes_to_ibge(est_csv, municipios) if not est_csv.empty else est_csv
        tel = tel_csv
        if not est.empty or not tel.empty:
            log.info("ANA via CSV (ANA_FETCH_SERIES=false): est=%s tel=%s", len(est), len(tel))
            return {
                "ana_estacoes": est,
                "ana_telemetria": tel,
                "ana_risco_municipal": ana_risco_municipal(tel),
            }

    est = fetch_ana_estacoes_telemetricas()
    if not est.empty:
        est = map_estacoes_to_ibge(est, municipios)
        tel = fetch_ana_telemetria_mt(est)
    if est.empty or tel.empty:
        est_csv, tel_csv = load_ana_csv_fallback()
        if est.empty and not est_csv.empty:
            est = map_estacoes_to_ibge(est_csv, municipios)
            log.info("ANA estações via CSV fallback: %s", len(est))
        if tel.empty and not tel_csv.empty:
            tel = tel_csv
            log.info("ANA telemetria via CSV fallback: %s", len(tel))
    risco = ana_risco_municipal(tel)
    return {
        "ana_estacoes": est,
        "ana_telemetria": tel,
        "ana_risco_municipal": ana_risco_municipal(tel) if risco is None else risco,
    }
