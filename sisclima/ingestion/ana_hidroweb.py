# -*- coding: utf-8 -*-
"""Ingestão ANA — estações telemétricas e séries hidrometeorológicas (MT).

Fontes:
- SOAP público: https://telemetriaws1.ana.gov.br/ServiceANA.asmx
  - ListaEstacoesTelemetricas
  - DadosHidrometeorologicos
- REST HidroWebService (OAuth Identificador/Senha):
  - OAUth/v1 → Bearer
  - HidroInventarioEstacoes/v1 (query: 'Unidade Federativa')
  - HidroinfoanaSerieTelemetricaAdotada/v1
    (query: 'Código da Estação', 'Tipo Filtro Data', 'Range Intervalo de busca')
- Fallback CSV: data/input/ana_estacoes_mt.csv e ana_telemetria.csv

Ativar REST: ANA_USE_HIDROWEB_REST=true + credenciais no .env (não versionar).
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from sisclima.core.config import APP_CONFIG, ROOT, as_bool, env
from sisclima.core.http_client import USER_AGENT, ssl_verify
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols, read_table_safe

log = get_logger(__name__)

SOAP_BASE = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx"
REST_BASE = "https://www.ana.gov.br/hidrowebservice"

# Cache curto do Bearer (token ANA ~60 min)
_REST_TOKEN: str | None = None
_REST_TOKEN_TS: float = 0.0


def _session() -> requests.Session:
    """Sessão ANA com User-Agent institucional (sem stealth)."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/xml, */*"})
    s.verify = ssl_verify("ANA_SSL_VERIFY", True)
    return s


def _rest_base() -> str:
    return (env("ANA_HIDROWEB_BASE_URL") or REST_BASE).rstrip("/")


def _use_hidroweb_rest() -> bool:
    return as_bool(env("ANA_USE_HIDROWEB_REST", "false"), False)


def _dias_range_enum(days: int) -> str:
    """Mapeia janela em dias para enum do HidroWebService."""
    d = max(1, int(days or 21))
    for cand in (2, 7, 14, 21, 30):
        if d <= cand:
            return f"DIAS_{cand}"
    return "DIAS_30"


def fetch_hidroweb_token(force: bool = False) -> str | None:
    """Obtém Bearer via OAUth/v1 (headers Identificador + Senha)."""
    global _REST_TOKEN, _REST_TOKEN_TS
    preset = (env("ANA_HIDROWEB_TOKEN") or "").strip()
    if preset and not force:
        return preset
    if (
        not force
        and _REST_TOKEN
        and (time.time() - _REST_TOKEN_TS) < 45 * 60
    ):
        return _REST_TOKEN

    ident = (env("ANA_HIDROWEB_IDENTIFICADOR") or "").strip()
    senha = (env("ANA_HIDROWEB_SENHA") or "").strip()
    if not ident or not senha:
        log.warning("ANA REST: faltam ANA_HIDROWEB_IDENTIFICADOR / ANA_HIDROWEB_SENHA")
        return None
    try:
        r = _session().get(
            f"{_rest_base()}/EstacoesTelemetricas/OAUth/v1",
            headers={"Identificador": ident, "Senha": senha, "accept": "*/*"},
            timeout=int(env("ANA_TIMEOUT_SECONDS", "90") or 90),
        )
        # 417 = Expectation Failed / throttling ocasional da ANA — 1 retry
        if r.status_code == 417:
            time.sleep(1.5)
            r = _session().get(
                f"{_rest_base()}/EstacoesTelemetricas/OAUth/v1",
                headers={"Identificador": ident, "Senha": senha, "accept": "*/*"},
                timeout=int(env("ANA_TIMEOUT_SECONDS", "90") or 90),
            )
        r.raise_for_status()
        payload = r.json() if r.content else {}
        items = payload.get("items") if isinstance(payload, dict) else None
        token = None
        if isinstance(items, dict):
            token = items.get("tokenautenticacao") or items.get("token")
        if not token and isinstance(payload, dict):
            token = payload.get("tokenautenticacao") or payload.get("token")
        if not token:
            log.warning("ANA REST OAuth sem token (status=%s)", r.status_code)
            return None
        _REST_TOKEN = str(token)
        _REST_TOKEN_TS = time.time()
        return _REST_TOKEN
    except Exception as exc:
        log.warning("ANA REST OAuth falhou: %s", exc)
        return None


def _rest_get(path: str, params: dict | None = None) -> dict | list | None:
    token = fetch_hidroweb_token()
    if not token:
        return None
    url = f"{_rest_base()}/EstacoesTelemetricas/{path.lstrip('/')}"
    try:
        r = _session().get(
            url,
            headers={"Authorization": f"Bearer {token}", "accept": "*/*"},
            params=params or {},
            timeout=int(env("ANA_TIMEOUT_SECONDS", "120") or 120),
        )
        if r.status_code == 401:
            token = fetch_hidroweb_token(force=True)
            if not token:
                return None
            r = _session().get(
                url,
                headers={"Authorization": f"Bearer {token}", "accept": "*/*"},
                params=params or {},
                timeout=int(env("ANA_TIMEOUT_SECONDS", "120") or 120),
            )
        r.raise_for_status()
        return r.json() if r.content else None
    except Exception as exc:
        log.warning("ANA REST GET %s falhou: %s", path, exc)
        return None


def fetch_ana_estacoes_rest(uf: str | None = None) -> pd.DataFrame:
    """Inventário MT via HidroInventarioEstacoes/v1 (param 'Unidade Federativa')."""
    uf = (uf or env("ANA_UF") or APP_CONFIG.uf or "MT").strip().upper()
    payload = _rest_get(
        "HidroInventarioEstacoes/v1",
        params={"Unidade Federativa": uf},
    )
    if not payload:
        return pd.DataFrame()
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        return pd.DataFrame()
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cod = (
            it.get("Codigo_Adicional")
            or it.get("Codigo_Estacao")
            or it.get("codigoestacao")
            or it.get("codigo_estacao")
        )
        if cod is None or str(cod).strip() in {"", "None", "nan"}:
            continue
        tipo = str(it.get("Tipo_Estacao") or "")
        tele = str(it.get("Tipo_Estacao_Telemetrica") or it.get("Telemetrica") or "")
        nivel = str(it.get("Tipo_Estacao_Registrador_Nivel") or it.get("Tipo_Estacao_Escala") or "")
        rows.append(
            {
                "codigo_estacao": str(cod).replace(".0", "").strip(),
                "nome_estacao": str(it.get("Estacao_Nome") or it.get("Nome_Estacao") or ""),
                "municipio": str(it.get("Municipio_Nome") or ""),
                "uf": str(
                    it.get("UF_Estacao")
                    or it.get("Responsavel_Unidade_UF")
                    or uf
                )
                .strip()
                .upper()[:2],
                "lat": pd.to_numeric(it.get("Latitude"), errors="coerce"),
                "lon": pd.to_numeric(it.get("Longitude"), errors="coerce"),
                "nome_rio": str(it.get("Rio_Nome") or "").replace("N/A", "").strip(),
                "tipo_estacao": tipo,
                "telemetrica": tele,
                "tem_nivel": nivel,
                "fonte": "ANA_HIDROWEB_REST",
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    t = out["tipo_estacao"].astype(str).str.lower()
    tele = out["telemetrica"].astype(str).str.lower()
    niv = out["tem_nivel"].astype(str).str.lower()
    yes = {"1", "sim", "true", "s", "yes"}
    out["_prio"] = 3
    out.loc[t.str.contains("fluv", na=False), "_prio"] = 1
    out.loc[tele.isin(yes) | niv.isin(yes), "_prio"] = out["_prio"].clip(upper=1)
    out.loc[t.str.contains("pluv", na=False) & ~tele.isin(yes), "_prio"] = 2
    # códigos 8 dígitos oficiais primeiro
    cod = out["codigo_estacao"].astype(str)
    out["_prio2"] = np.where(cod.str.fullmatch(r"\d{8}"), 0, 1)
    out = out.sort_values(["_prio", "_prio2", "codigo_estacao"], kind="mergesort")
    return out.drop(columns=["_prio", "_prio2"], errors="ignore").reset_index(drop=True)


def fetch_ana_serie_estacao_rest(codigo_estacao: str, days: int = 21) -> pd.DataFrame:
    """Série adotada via REST (params em português conforme OpenAPI/manual)."""
    rng = _dias_range_enum(days)
    payload = _rest_get(
        "HidroinfoanaSerieTelemetricaAdotada/v1",
        params={
            "Código da Estação": str(codigo_estacao),
            "Tipo Filtro Data": "DATA_LEITURA",
            "Range Intervalo de busca": rng,
        },
    )
    if not payload:
        return pd.DataFrame()
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    if df.empty:
        return df
    rename = {
        "Chuva_Adotada": "chuva_mm",
        "Cota_Adotada": "cota_cm",
        "Vazao_Adotada": "vazao_m3s",
        "Data_Hora_Medicao": "data_hora",
        "codigoestacao": "codigo_estacao",
        "Codigo_Estacao": "codigo_estacao",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "codigo_estacao" not in df.columns:
        df["codigo_estacao"] = str(codigo_estacao)
    else:
        df["codigo_estacao"] = df["codigo_estacao"].astype(str)
    if "data_hora" in df.columns:
        df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce")
        df["data"] = df["data_hora"].dt.date.astype(str)
    for c in ("chuva_mm", "cota_cm", "vazao_m3s"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    keep = [c for c in ("codigo_estacao", "data_hora", "data", "chuva_mm", "cota_cm", "vazao_m3s") if c in df.columns]
    df = df[keep].copy()
    df["fonte"] = "ANA_HIDROWEB_REST"
    return df


def _parse_dataset_xml(xml_text: str) -> pd.DataFrame:
    """Extrai linhas de DiffGram/DataSet SOAP da ANA (Table ou DadosHidromet*)."""
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    row_tags = {
        "Table",
        "DadosHidrometereologicos",  # ortografia histórica do serviço ANA
        "DadosHidrometeorologicos",
    }

    def _row_from_el(el: ET.Element) -> dict:
        return {child.tag.split("}")[-1]: child.text for child in list(el)}

    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in row_tags:
            row = _row_from_el(el)
            if row:
                rows.append(row)
    if rows:
        return pd.DataFrame(rows)

    # Fallback: filhos diretos de DocumentElement com campos de medição
    for el in root.iter():
        if el.tag.split("}")[-1] != "DocumentElement":
            continue
        for child in list(el):
            row = _row_from_el(child)
            if row and any(k in row for k in ("CodEstacao", "DataHora", "Chuva", "Nivel", "Vazao")):
                rows.append(row)
        break
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

    if _use_hidroweb_rest():
        rest = fetch_ana_estacoes_rest(uf=uf)
        if not rest.empty:
            log.info("ANA estações via HidroWeb REST: %s", len(rest))
            # Complementa com inventário SOAP (códigos telemétricos clássicos) sem perder REST
            try:
                soap = _fetch_ana_estacoes_soap(uf=uf)
                if not soap.empty:
                    both = pd.concat([rest, soap], ignore_index=True)
                    both = both.drop_duplicates(subset=["codigo_estacao"], keep="first")
                    log.info("ANA estações REST+SOAP: %s", len(both))
                    return both.reset_index(drop=True)
            except Exception as exc:
                log.warning("Complemento SOAP de estações falhou: %s", exc)
            return rest
        log.warning("ANA REST inventário vazio — tentando SOAP")

    return _fetch_ana_estacoes_soap(uf=uf)


def _fetch_ana_estacoes_soap(uf: str | None = None) -> pd.DataFrame:
    """Lista estações via SOAP público ListaEstacoesTelemetricas."""
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
        mapped["municipio"] = mapped["municipio"].where(
            mapped["municipio"].astype(str).str.len() > 0, mapped["municipio_ibge"]
        )
    # NÃO usar endswith("_ibge"): isso apaga a própria coluna cod_ibge
    drop_cols = [c for c in ("_k", "cod_ibge_ibge", "municipio_ibge") if c in mapped.columns]
    return mapped.drop(columns=drop_cols, errors="ignore")


def fetch_ana_serie_estacao(codigo_estacao: str, days: int = 7) -> pd.DataFrame:
    """Busca série hidrometeorológica recente de uma estação (REST se ativo, senão SOAP)."""
    if _use_hidroweb_rest():
        rest = fetch_ana_serie_estacao_rest(codigo_estacao, days=days)
        if not rest.empty:
            return rest

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
        ("nivel", "cota_cm"),  # SOAP DadosHidrometeorologicos usa Nivel (cm)
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
        elif cl in ("cota", "nivel") or ("cota" in cl) or (cl == "nivel" or cl.endswith("_nivel")):
            df = df.rename(columns={c: "cota_cm"})
        elif "vazao" in cl or "vazão" in cl:
            df = df.rename(columns={c: "vazao_m3s"})
        elif "data" in cl and "hora" in cl:
            df = df.rename(columns={c: "data_hora"})
        elif cl == "datahora":
            df = df.rename(columns={c: "data_hora"})
    if "data_hora" in df.columns:
        # SOAP devolve ISO (YYYY-MM-DD HH:MM:SS) — dayfirst=True inverteria mês/dia
        raw = df["data_hora"]
        df["data_hora"] = pd.to_datetime(raw, errors="coerce", format="ISO8601")
        if df["data_hora"].isna().all():
            df["data_hora"] = pd.to_datetime(raw, errors="coerce", dayfirst=False)
        if df["data_hora"].isna().mean() > 0.5:
            df["data_hora"] = pd.to_datetime(raw, errors="coerce", dayfirst=True)
        df["data"] = df["data_hora"].dt.date.astype(str)
    for c in ["chuva_mm", "cota_cm", "vazao_m3s"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["fonte"] = "ANA_SOAP"
    return df


def _prioritize_estacoes_fluviometricas(estacoes: pd.DataFrame) -> pd.DataFrame:
    """Prioriza estações com nome de rio (fluviométricas) antes das só pluviométricas."""
    if estacoes is None or estacoes.empty:
        return estacoes if estacoes is not None else pd.DataFrame()
    out = estacoes.copy()
    if "nome_rio" in out.columns:
        rio = out["nome_rio"].astype(str).str.strip()
        out["_prio"] = np.where(
            rio.ne("") & rio.str.lower().ne("nan") & rio.str.lower().ne("none"),
            0,
            1,
        )
        # Códigos 8 dígitos típicos de fluviométricas oficiais (ex.: 15043000)
        cod = out["codigo_estacao"].astype(str).str.replace(r"\.0$", "", regex=True)
        out["_prio2"] = np.where(cod.str.fullmatch(r"\d{8}"), 0, 1)
        out = out.sort_values(["_prio", "_prio2", "codigo_estacao"], kind="mergesort").drop(
            columns=["_prio", "_prio2"]
        )
    return out.reset_index(drop=True)


def fetch_ana_telemetria_mt(
    estacoes: pd.DataFrame | None = None,
    max_estacoes: int | None = None,
    days: int | None = None,
) -> pd.DataFrame:
    """Consulta séries de um subconjunto de estações MT (prioriza fluviométricas).

    Tenta mais códigos do que o teto de sucesso, porque várias estações
    telemétricas respondem Error/vazio no SOAP de série.
    """
    if not as_bool(env("USE_ANA", "true"), True):
        return pd.DataFrame()
    if estacoes is None or estacoes.empty:
        estacoes = fetch_ana_estacoes_telemetricas()
    if estacoes.empty or "codigo_estacao" not in estacoes.columns:
        return pd.DataFrame()

    if days is None:
        try:
            days = int(env("ANA_SERIES_DAYS", "21") or 21)
        except Exception:
            days = 21
    days = max(7, int(days))

    max_env = env("ANA_MAX_ESTACOES")
    if max_estacoes is None and max_env:
        try:
            max_estacoes = int(max_env)
        except Exception:
            max_estacoes = 35
    if max_estacoes is None:
        max_estacoes = 35

    # Pool de tentativa: até 3× o teto de estações com série útil
    try_cap = max(max_estacoes * 3, max_estacoes + 10)
    estacoes = _prioritize_estacoes_fluviometricas(estacoes)
    codes = estacoes["codigo_estacao"].astype(str).drop_duplicates().head(try_cap).tolist()
    frames = []
    ok = 0
    for i, cod in enumerate(codes):
        if ok >= max_estacoes:
            break
        serie = fetch_ana_serie_estacao(cod, days=days)
        if serie.empty:
            continue
        # exige ao menos uma variável hidrológica
        has_var = any(
            c in serie.columns and pd.to_numeric(serie[c], errors="coerce").notna().any()
            for c in ("cota_cm", "vazao_m3s", "chuva_mm")
        )
        if not has_var:
            continue
        meta = estacoes[estacoes["codigo_estacao"].astype(str).eq(cod)].head(1)
        for col in ["municipio", "cod_ibge", "nome_estacao", "lat", "lon", "uf", "nome_rio"]:
            if col in meta.columns:
                serie[col] = meta.iloc[0][col]
        frames.append(serie)
        ok += 1
        time.sleep(0.2)
        if ok % 5 == 0:
            log.info("ANA telemetria: %s/%s estações úteis (tentativa %s, janela %sd)", ok, max_estacoes, i + 1, days)
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
    if "cod_ibge" in keys and df["cod_ibge"].isna().all():
        keys = [c for c in keys if c != "cod_ibge"]
    if not keys or "data" not in keys:
        return pd.DataFrame()

    agg = {"chuva_mm": "sum", "cota_cm": "max", "vazao_m3s": "max"}
    use = {k: v for k, v in agg.items() if k in df.columns}
    g = df.groupby(keys, as_index=False, dropna=False).agg(use)

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


def _ensure_telemetria_ibge(
    tel: pd.DataFrame,
    est: pd.DataFrame | None = None,
    municipios: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Propaga cod_ibge para telemetria (estação → município fuzzy ASCII)."""
    if tel is None or tel.empty:
        return tel if tel is not None else pd.DataFrame()
    out = tel.copy()
    if est is not None and not est.empty and "codigo_estacao" in out.columns and "codigo_estacao" in est.columns:
        meta_cols = ["codigo_estacao"] + [c for c in ["cod_ibge", "municipio"] if c in est.columns]
        meta = est[meta_cols].drop_duplicates("codigo_estacao")
        out = out.merge(meta, on="codigo_estacao", how="left", suffixes=("", "_est"))
        if "cod_ibge_est" in out.columns:
            if "cod_ibge" not in out.columns:
                out["cod_ibge"] = out["cod_ibge_est"]
            else:
                out["cod_ibge"] = out["cod_ibge"].fillna(out["cod_ibge_est"])
        if "municipio_est" in out.columns:
            if "municipio" not in out.columns:
                out["municipio"] = out["municipio_est"]
            else:
                out["municipio"] = out["municipio"].where(
                    out["municipio"].astype(str).str.len() > 0, out["municipio_est"]
                )
        out = out.drop(columns=[c for c in out.columns if c.endswith("_est")], errors="ignore")
    if municipios is not None and not municipios.empty and "municipio" in out.columns:
        out = map_estacoes_to_ibge(out, municipios)
    return out


def load_ana_bundle(municipios: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Carrega inventário + telemetria ANA (API) com fallback CSV."""
    # Padrão: série live (ANA_FETCH_SERIES=true). false força CSV.
    prefer_csv = not as_bool(env("ANA_FETCH_SERIES", "true"), True)
    est = pd.DataFrame()
    tel = pd.DataFrame()

    if prefer_csv:
        est_csv, tel_csv = load_ana_csv_fallback()
        est = map_estacoes_to_ibge(est_csv, municipios) if not est_csv.empty else est_csv
        tel = _ensure_telemetria_ibge(tel_csv, est, municipios) if not tel_csv.empty else tel_csv
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
    tel = _ensure_telemetria_ibge(tel, est, municipios)
    risco = ana_risco_municipal(tel)
    return {
        "ana_estacoes": est,
        "ana_telemetria": tel,
        "ana_risco_municipal": risco if risco is not None else pd.DataFrame(),
    }
