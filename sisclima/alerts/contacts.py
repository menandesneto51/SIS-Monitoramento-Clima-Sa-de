# -*- coding: utf-8 -*-
"""Destinatários territoriais (regionais / municipais / Cuiabá).

Canal central CIEVS (`menandesneto@ses.mt.gov.br` + `notifica@ses.mt.gov.br`) NÃO usa esta planilha:
ele recebe apenas o alerta estadual via ALERT_EMAIL_TO / TELEGRAM_CHAT_ID.

Fan-out territorial só ocorre quando a planilha existir e ALERT_FANOUT_ENABLED=true.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

REQUIRED_COLS = [
    "tipo_destinatario",
    "regional_saude",
    "cod_ibge",
    "municipio",
    "nome",
    "email",
    "telegram_chat_id",
    "ativo",
]


def contacts_path() -> Path:
    raw = env("ALERT_CONTACTS_CSV", "data/input/contatos_alertas.csv") or "data/input/contatos_alertas.csv"
    return Path(raw)


def contacts_available() -> bool:
    p = contacts_path()
    return p.is_file() and p.stat().st_size > 0


def fanout_enabled() -> bool:
    """Fan-out territorial exige flag explícita + planilha presente."""
    if not as_bool(env("ALERT_FANOUT_ENABLED", "false"), False):
        return False
    return contacts_available()


def load_contacts() -> pd.DataFrame:
    path = contacts_path()
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_COLS)
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler planilha de contatos %s: %s", path, exc)
        return pd.DataFrame(columns=REQUIRED_COLS)
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""
    return df


def _active(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    c = df.copy().fillna("")
    mask = c["ativo"].astype(str).str.lower().isin(["", "1", "true", "sim", "s", "yes", "ativo"])
    return c[mask]


def recipients_for(
    escopo: str,
    *,
    regional: str | None = None,
    cod_ibge: str | None = None,
    municipio: str | None = None,
    include_inactive: bool = False,
) -> tuple[list[str], list[str]]:
    """Retorna (emails, telegram_chat_ids) para o escopo territorial.

    Nunca inclui destinatários ``estadual`` — esses vão só pelo canal central.
    ``include_inactive=True`` só para simulação (inclui PENDENTE/ativo=0).
    """
    c = load_contacts() if include_inactive else _active(load_contacts())
    if c.empty:
        return [], []

    tipo = c["tipo_destinatario"].astype(str).str.lower().str.strip()
    escopo_l = str(escopo or "").lower()

    if escopo_l == "regional":
        reg = str(regional or "").strip()
        sel = c[(tipo == "regional") & (c["regional_saude"].astype(str).str.strip() == reg)]
        # COSEMS não traz e-mail de escritório: usa SMS da mesma região.
        if sel.empty and reg:
            sel = c[(tipo == "municipal") & (c["regional_saude"].astype(str).str.strip() == reg)]
    elif escopo_l == "cuiaba":
        sel = c[tipo.isin(["cuiaba", "vigidesastre", "vigidesastre_cuiaba"])]
        if sel.empty and cod_ibge:
            sel = c[(tipo == "municipal") & (c["cod_ibge"].astype(str).str.strip() == str(cod_ibge))]
    elif escopo_l == "municipal":
        ibge = str(cod_ibge or "").strip()
        mun = str(municipio or "").strip().lower()
        by_ibge = c[(tipo == "municipal") & (c["cod_ibge"].astype(str).str.strip() == ibge)] if ibge else c.iloc[0:0]
        if by_ibge.empty and mun:
            sel = c[
                (tipo == "municipal")
                & (c["municipio"].astype(str).str.strip().str.lower() == mun)
            ]
        else:
            sel = by_ibge
    else:
        return [], []

    emails = sorted({e for e in sel["email"].astype(str) if "@" in e})
    chats = sorted({t.strip() for t in sel["telegram_chat_id"].astype(str) if t.strip()})
    return emails, chats


def lookup_contato_por_email(email: str) -> dict[str, str] | None:
    """Município/regional catalogados para o e-mail (COSEMS / planilha de alertas)."""
    mail = str(email or "").strip().lower()
    if "@" not in mail:
        return None
    c = load_contacts()
    if c.empty or "email" not in c.columns:
        return None
    hit = c[c["email"].astype(str).str.strip().str.lower() == mail]
    if hit.empty:
        return None
    row = hit.iloc[0]
    return {
        "email": mail,
        "municipio": str(row.get("municipio") or "").strip(),
        "regional_saude": str(row.get("regional_saude") or "").strip(),
        "cod_ibge": str(row.get("cod_ibge") or "").strip(),
        "tipo": str(row.get("tipo_destinatario") or "").strip().lower(),
        "nome": str(row.get("nome") or "").strip(),
        "ativo": str(row.get("ativo") or "").strip(),
    }


def summarize_contacts() -> dict[str, Any]:
    all_rows = load_contacts()
    c = _active(all_rows)
    if all_rows.empty:
        return {
            "path": str(contacts_path()),
            "disponivel": False,
            "fanout_enabled": fanout_enabled(),
            "n": 0,
            "n_total": 0,
            "n_aprovados": 0,
        }
    tipos = (
        c["tipo_destinatario"].astype(str).str.lower().value_counts().to_dict()
        if not c.empty
        else {}
    )
    return {
        "path": str(contacts_path()),
        "disponivel": True,
        "fanout_enabled": fanout_enabled(),
        "n": int(len(c)),
        "n_total": int(len(all_rows)),
        "n_aprovados": int(len(c)),
        "por_tipo": tipos,
    }
