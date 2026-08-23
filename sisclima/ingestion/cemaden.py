# -*- coding: utf-8 -*-
"""Ingestão de alertas abertos do Cemaden (Painel de Alertas)."""
from __future__ import annotations

import pandas as pd

from sisclima.core.config import APP_CONFIG, as_bool, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"

# Mapeamento operacional Cemaden → nível ARARAS
_NIVEL_MAP = {
    "muito alto": "roxa",
    "alto": "vermelha",
    "moderado": "laranja",
    "moderada": "laranja",
    "baixo": "amarela",
    "baixa": "amarela",
}


def fetch_cemaden_alerts(uf: str | None = None) -> pd.DataFrame:
    """Busca alertas abertos do painel Cemaden.

    Endpoint público oficial: `/wsAlertas2` (sem scraper stealth).
    Filtra por UF (padrão APP_UF / MT) no cliente.
    """
    if not as_bool(env("USE_CEMADEN", "true"), True):
        return pd.DataFrame()

    url = (env("CEMADEN_ALERTS_URL") or DEFAULT_URL).strip()
    if not url:
        return pd.DataFrame()

    uf = (uf if uf is not None else (env("CEMADEN_UF") or APP_CONFIG.uf or "MT"))
    uf = str(uf).strip().upper() if uf is not None else ""

    try:
        r = http_get(
            url,
            timeout=int(env("CEMADEN_TIMEOUT_SECONDS", "30") or 30),
            ssl_env_key="CEMADEN_SSL_VERIFY",
        )
        r.raise_for_status()
        js = r.json()
    except Exception as exc:
        if "SSL" in str(exc).upper() or "CERTIFICATE" in str(exc).upper():
            try:
                r = http_get(
                    url,
                    timeout=int(env("CEMADEN_TIMEOUT_SECONDS", "30") or 30),
                    verify=False,
                )
                r.raise_for_status()
                js = r.json()
            except Exception as exc2:
                log.warning("Falha ao consultar alertas Cemaden (%s): %s", url, exc2)
                return pd.DataFrame()
        else:
            log.warning("Falha ao consultar alertas Cemaden (%s): %s", url, exc)
            return pd.DataFrame()

    rows = js.get("alertas") if isinstance(js, dict) else js
    if not isinstance(rows, list) or not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["atualizado_painel"] = js.get("atualizado") if isinstance(js, dict) else None
    df["fonte"] = "cemaden"
    if uf and uf not in {"*", "BR", "ALL", "TODAS"} and "uf" in df.columns:
        df = df[df["uf"].astype(str).str.upper().eq(uf)].copy()
    return df.reset_index(drop=True)


def normalize_cemaden_alerts(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "data",
                "cod_ibge",
                "municipio",
                "uf",
                "tipo_risco",
                "evento",
                "nivel",
                "nivel_alerta",
                "nivel_sis",
                "status",
                "cod_alerta",
                "lat",
                "lon",
                "fonte",
            ]
        )

    out = df.copy()
    out.columns = [str(c).lower().strip().replace(" ", "_") for c in out.columns]

    rename = {
        "codibge": "cod_ibge",
        "codigo_ibge": "cod_ibge",
        "cod_ibge_7": "cod_ibge",
        "datahoracriacao": "data",
        "data_hora_criacao": "data",
        "ult_atualizacao": "data_atualizacao",
        "latitude": "lat",
        "longitude": "lon",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})

    if "cod_ibge" in out.columns:
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)

    if "data" in out.columns:
        out["data"] = pd.to_datetime(out["data"], errors="coerce")
    else:
        out["data"] = pd.NaT

    evento = out["evento"].astype(str) if "evento" in out.columns else pd.Series([""] * len(out))
    nivel_raw = out["nivel"].astype(str) if "nivel" in out.columns else pd.Series([""] * len(out))
    out["nivel_alerta"] = nivel_raw.str.strip()
    out["nivel_sis"] = nivel_raw.str.strip().str.lower().map(_NIVEL_MAP).fillna("amarela")

    ev_l = evento.str.lower()
    tipo = pd.Series(["outro"] * len(out), index=out.index)
    tipo = tipo.mask(ev_l.str.contains("hidro|inunda|enxurr|alag", regex=True, na=False), "risco_hidrologico")
    tipo = tipo.mask(ev_l.str.contains("massa|desliz|geo", regex=True, na=False), "movimento_massa")
    tipo = tipo.mask(ev_l.str.contains("seca|estiagem|drought", regex=True, na=False), "seca")
    tipo = tipo.mask(ev_l.str.contains("chuva|precip", regex=True, na=False), "chuva")
    out["tipo_risco"] = tipo
    out["evento"] = evento
    if "fonte" not in out.columns:
        out["fonte"] = "cemaden"

    keep = [
        c
        for c in [
            "data",
            "data_atualizacao",
            "cod_ibge",
            "municipio",
            "uf",
            "tipo_risco",
            "evento",
            "nivel",
            "nivel_alerta",
            "nivel_sis",
            "status",
            "cod_alerta",
            "lat",
            "lon",
            "atualizado_painel",
            "fonte",
        ]
        if c in out.columns
    ]
    return out[keep].reset_index(drop=True)


def cemaden_alert_for_municipio(
    alerts: pd.DataFrame,
    municipio: str | None = None,
    cod_ibge: str | None = None,
) -> tuple[str | None, str | None]:
    """Retorna (motivo, nivel_sis) do alerta Cemaden mais grave para o município."""
    if alerts is None or alerts.empty:
        return None, None

    df = alerts.copy()
    if "nivel_sis" not in df.columns:
        df = normalize_cemaden_alerts(df)
    if df.empty:
        return None, None

    selected = df
    if cod_ibge and "cod_ibge" in df.columns:
        cod = str(cod_ibge).strip()
        m = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False).eq(cod)
        if m.any():
            selected = df.loc[m]
        elif municipio and "municipio" in df.columns:
            selected = df[df["municipio"].astype(str).str.lower().eq(str(municipio).lower())]
        else:
            return None, None
    elif municipio and "municipio" in df.columns:
        selected = df[df["municipio"].astype(str).str.lower().eq(str(municipio).lower())]
        if selected.empty:
            return None, None
    else:
        return None, None

    if selected.empty:
        return None, None

    order = {"roxa": 4, "vermelha": 3, "laranja": 2, "amarela": 1, "verde": 0, "cinza": -1}
    selected = selected.copy()
    selected["_score"] = selected["nivel_sis"].map(order).fillna(0)
    row = selected.sort_values("_score", ascending=False).iloc[0]
    tipo = row.get("tipo_risco") or "alerta"
    nivel = row.get("nivel_alerta") or row.get("nivel") or row.get("nivel_sis")
    evento = row.get("evento") or "alerta Cemaden"
    motivo = f"Alerta Cemaden {nivel} ({tipo}): {evento}"
    return motivo, str(row.get("nivel_sis") or "amarela")


def cemaden_motivo_for_municipio(
    alerts: pd.DataFrame,
    municipio: str | None = None,
    cod_ibge: str | None = None,
) -> str | None:
    motivo, _ = cemaden_alert_for_municipio(alerts, municipio=municipio, cod_ibge=cod_ibge)
    return motivo
