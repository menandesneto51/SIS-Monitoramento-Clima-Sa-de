from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

import pandas as pd

from sisclima.core.config import APP_CONFIG, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.core.recorte_mt import RECORTE_UF, alerta_abrange_mato_grosso, extrair_areas_mato_grosso

log = get_logger(__name__)

DEFAULT_INMET_RSS_URL = "https://apiprevmet3.inmet.gov.br/avisos/rss"


def _parse_rss_table_field(html: str, label: str) -> str | None:
    if not html:
        return None
    m = re.search(rf"<th[^>]*>{re.escape(label)}</th>\s*<td>([^<]+)</td>", html, re.I)
    return m.group(1).strip() if m else None


def _parse_rss_datetime(raw: str | None) -> pd.Timestamp:
    if not raw:
        return pd.NaT
    txt = str(raw).split(".")[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return pd.Timestamp(datetime.strptime(txt, fmt))
        except ValueError:
            continue
    return pd.to_datetime(raw, errors="coerce")


def _severidade_to_nivel(sev: str | None) -> str:
    s = str(sev or "").lower()
    if "grande perigo" in s or "vermelh" in s:
        return "vermelha"
    if s == "perigo" or ("perigo" in s and "potencial" not in s):
        return "laranja"
    if "potencial" in s or "amarel" in s:
        return "amarela"
    return "amarela"


def parse_inmet_rss(content: bytes | str, *, uf: str | None = None) -> pd.DataFrame:
    """Converte feed RSS Alert-AS do INMET em DataFrame padronizado."""
    try:
        root = ET.fromstring(content if isinstance(content, (bytes, bytearray)) else content.encode("utf-8"))
    except ET.ParseError as exc:
        log.warning("RSS INMET inválido: %s", exc)
        return pd.DataFrame()

    uf = (uf or env("INMET_UF") or APP_CONFIG.uf or RECORTE_UF).strip().upper()
    rows: list[dict[str, object]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = item.findtext("description") or ""
        pub = item.findtext("pubDate")
        link = item.findtext("link") or item.findtext("guid")
        evento = _parse_rss_table_field(desc, "Evento") or title
        severidade = _parse_rss_table_field(desc, "Severidade")
        inicio = _parse_rss_table_field(desc, "Início")
        fim = _parse_rss_table_field(desc, "Fim")
        area = _parse_rss_table_field(desc, "Área") or ""
        status = _parse_rss_table_field(desc, "Status")
        descricao = _parse_rss_table_field(desc, "Descrição") or re.sub(r"<[^>]+>", " ", desc)
        descricao = re.sub(r"\s+", " ", descricao).strip()

        blob = f"{title} {area} {descricao}"
        if uf and uf not in {"*", "BR", "ALL", "TODAS"}:
            if uf == RECORTE_UF:
                if not alerta_abrange_mato_grosso(blob):
                    continue
            elif uf not in blob.upper():
                continue

        area_mt = extrair_areas_mato_grosso(area)
        rows.append(
            {
                "data_emissao": _parse_rss_datetime(pub) if pub else pd.NaT,
                "inicio_vigencia": _parse_rss_datetime(inicio),
                "fim_vigencia": _parse_rss_datetime(fim),
                "municipio": (area_mt or area)[:180] if (area_mt or area) else "Área abrangente",
                "cod_ibge": None,
                "uf": RECORTE_UF,
                "nivel_alerta": _severidade_to_nivel(severidade),
                "severidade": severidade,
                "evento": evento,
                "descricao": descricao[:500],
                "area_abrangencia": area,
                "area_mt": area_mt,
                "status": status,
                "fonte": "inmet_rss",
                "link": link,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def fetch_inmet_rss_alerts(*, uf: str | None = None) -> pd.DataFrame:
    """Busca avisos INMET via feed RSS oficial (Alert-AS)."""
    url = (env("INMET_ALERTS_URL") or env("INMET_RSS_URL") or DEFAULT_INMET_RSS_URL).strip()
    if not url:
        return pd.DataFrame()
    headers = {"Accept": "application/rss+xml, application/xml, text/xml, */*"}
    try:
        r = http_get(url, timeout=30, headers=headers, ssl_env_key="INMET_SSL_VERIFY")
        r.raise_for_status()
        df = parse_inmet_rss(r.content, uf=uf)
        if not df.empty:
            return df
    except Exception as exc:
        log.warning("Falha ao consultar RSS INMET (%s): %s", url, exc)
        if "SSL" in str(exc).upper() or "CERTIFICATE" in str(exc).upper():
            try:
                r = http_get(url, timeout=30, headers=headers, verify=False)
                r.raise_for_status()
                return parse_inmet_rss(r.content, uf=uf)
            except Exception as exc2:
                log.warning("RSS INMET (verify=False) falhou: %s", exc2)
    return pd.DataFrame()


def fetch_inmet_alerts() -> pd.DataFrame:
    """Conector genérico para alertas INMET (URL oficial / CSV fallback).

    Se INMET_ALERTS_URL estiver vazio, retorna DataFrame vazio e o pipeline usa CSV.
    """
    url = env("INMET_ALERTS_URL")
    if url:
        try:
            r = http_get(url, timeout=30, ssl_env_key="INMET_SSL_VERIFY")
            r.raise_for_status()
            js = r.json()
            if isinstance(js, list):
                return pd.DataFrame(js)
            if isinstance(js, dict):
                for key in ["data", "alertas", "features", "items"]:
                    if key in js and isinstance(js[key], list):
                        return pd.DataFrame(js[key])
                return pd.DataFrame([js])
        except Exception as exc:
            log.warning("Falha ao consultar alertas INMET (JSON): %s", exc)
    return fetch_inmet_rss_alerts()


def normalize_inmet_alerts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(c).lower().strip().replace(' ', '_') for c in df.columns]
    # Padronização mínima esperada pelo motor de estágio
    for col in ['nivel','severidade','risco']:
        if col in df.columns and 'nivel_alerta' not in df.columns:
            df = df.rename(columns={col:'nivel_alerta'})
            break
    return df
