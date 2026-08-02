# -*- coding: utf-8 -*-
"""Destinatários territoriais (regionais / municipais / Cuiabá).

Canal central CIEVS (Menandes + notifica@ses.mt.gov.br) NÃO usa esta planilha:
ele recebe apenas o alerta estadual via ALERT_EMAIL_TO / TELEGRAM_CHAT_ID.

Fan-out territorial só ocorre quando a planilha existir e ALERT_FANOUT_ENABLED=true.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT, as_bool, env
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

VALID_TIPOS = {
    "regional",
    "municipal",
    "cuiaba",
    "vigidesastre",
    "vigidesastre_cuiaba",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EXAMPLE_CONTACTS = ROOT / "config" / "contatos_alertas.exemplo.csv"


def contacts_path() -> Path:
    raw = env("ALERT_CONTACTS_CSV", "data/input/contatos_alertas.csv") or "data/input/contatos_alertas.csv"
    return Path(raw)


def contacts_available() -> bool:
    p = contacts_path()
    return p.is_file() and p.stat().st_size > 0


def resolve_contacts_path(*, allow_example: bool = False) -> Path | None:
    """Planilha de produção, ou exemplo (somente para validação/dry-run)."""
    p = contacts_path()
    if p.is_file() and p.stat().st_size > 0:
        return p
    if allow_example and EXAMPLE_CONTACTS.is_file():
        return EXAMPLE_CONTACTS
    return None


def fanout_enabled() -> bool:
    """Fan-out territorial exige flag explícita + planilha presente."""
    if not as_bool(env("ALERT_FANOUT_ENABLED", "false"), False):
        return False
    return contacts_available()


def fanout_dry_run_enabled() -> bool:
    """Dry-run planeja roteamento sem enviar (não exige ALERT_FANOUT_ENABLED)."""
    return as_bool(env("ALERT_FANOUT_DRY_RUN", "false"), False)


def load_contacts(path: Path | str | None = None) -> pd.DataFrame:
    target = Path(path) if path is not None else contacts_path()
    if not target.exists():
        return pd.DataFrame(columns=REQUIRED_COLS)
    try:
        df = pd.read_csv(target, dtype=str).fillna("")
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler planilha de contatos %s: %s", target, exc)
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
    contacts: pd.DataFrame | None = None,
) -> tuple[list[str], list[str]]:
    """Retorna (emails, telegram_chat_ids) para o escopo territorial.

    Nunca inclui destinatários ``estadual`` — esses vão só pelo canal central.
    """
    c = _active(contacts if contacts is not None else load_contacts())
    if c.empty:
        return [], []

    tipo = c["tipo_destinatario"].astype(str).str.lower().str.strip()
    escopo_l = str(escopo or "").lower()

    if escopo_l == "regional":
        reg = str(regional or "").strip()
        sel = c[(tipo == "regional") & (c["regional_saude"].astype(str).str.strip() == reg)]
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


def validate_contacts(path: Path | str | None = None) -> dict[str, Any]:
    """Valida schema, e-mails e tipos da planilha de contatos."""
    target = Path(path) if path is not None else resolve_contacts_path(allow_example=True)
    errors: list[str] = []
    warnings: list[str] = []
    if target is None:
        return {
            "ok": False,
            "path": str(contacts_path()),
            "fonte": "ausente",
            "n_linhas": 0,
            "n_ativos": 0,
            "errors": ["Planilha de contatos ausente (produção e exemplo)."],
            "warnings": [],
            "por_tipo": {},
        }

    fonte = "exemplo" if target.resolve() == EXAMPLE_CONTACTS.resolve() else "producao"
    if fonte == "exemplo":
        warnings.append(
            f"Usando modelo {EXAMPLE_CONTACTS.name} — copie para data/input/contatos_alertas.csv antes do envio real."
        )

    try:
        df = pd.read_csv(target, dtype=str).fillna("")
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": str(target),
            "fonte": fonte,
            "n_linhas": 0,
            "n_ativos": 0,
            "errors": [f"Falha ao ler CSV: {exc}"],
            "warnings": warnings,
            "por_tipo": {},
        }

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        errors.append(f"Colunas obrigatórias ausentes: {', '.join(missing)}")

    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = ""

    if df.empty:
        errors.append("Planilha sem linhas de contato.")

    ativos = _active(df)
    tipos = (
        ativos["tipo_destinatario"].astype(str).str.lower().str.strip().value_counts().to_dict()
        if not ativos.empty
        else {}
    )

    for i, row in df.iterrows():
        linha = int(i) + 2  # header = 1
        tipo = str(row.get("tipo_destinatario", "")).strip().lower()
        email = str(row.get("email", "")).strip()
        chat = str(row.get("telegram_chat_id", "")).strip()
        regional = str(row.get("regional_saude", "")).strip()
        ibge = str(row.get("cod_ibge", "")).strip()
        mun = str(row.get("municipio", "")).strip()
        ativo = str(row.get("ativo", "")).strip().lower()

        if tipo and tipo not in VALID_TIPOS:
            errors.append(f"L{linha}: tipo_destinatario inválido '{tipo}'")
        if email and not EMAIL_RE.match(email):
            errors.append(f"L{linha}: e-mail inválido '{email}'")
        if not email and not chat:
            warnings.append(f"L{linha}: sem e-mail e sem telegram_chat_id")
        if tipo == "regional" and not regional:
            errors.append(f"L{linha}: regional exige regional_saude")
        if tipo == "municipal":
            if not ibge and not mun:
                errors.append(f"L{linha}: municipal exige cod_ibge ou municipio")
            if ibge and not ibge.isdigit():
                warnings.append(f"L{linha}: cod_ibge não numérico '{ibge}'")
        if tipo in {"cuiaba", "vigidesastre", "vigidesastre_cuiaba"} and not (ibge or mun or regional):
            warnings.append(f"L{linha}: contato Cuiabá sem IBGE/município/regional")
        if ativo and ativo not in {"1", "true", "sim", "s", "yes", "ativo", "0", "false", "nao", "não", "n", "no", "inativo"}:
            warnings.append(f"L{linha}: valor de ativo pouco usual '{ativo}'")

    # Duplicatas ativas (mesmo tipo+chave)
    if not ativos.empty:
        keys = []
        for _, row in ativos.iterrows():
            tipo = str(row.get("tipo_destinatario", "")).strip().lower()
            if tipo == "regional":
                key = (tipo, str(row.get("regional_saude", "")).strip().lower(), str(row.get("email", "")).strip().lower())
            elif tipo == "municipal":
                key = (
                    tipo,
                    str(row.get("cod_ibge", "")).strip() or str(row.get("municipio", "")).strip().lower(),
                    str(row.get("email", "")).strip().lower(),
                )
            else:
                key = (tipo, str(row.get("email", "")).strip().lower(), str(row.get("telegram_chat_id", "")).strip())
            keys.append(key)
        seen: set[tuple] = set()
        for key in keys:
            if key in seen and any(key):
                warnings.append(f"Possível duplicata ativa: {key}")
            seen.add(key)

    return {
        "ok": len(errors) == 0,
        "path": str(target),
        "fonte": fonte,
        "n_linhas": int(len(df)),
        "n_ativos": int(len(ativos)),
        "errors": errors,
        "warnings": warnings,
        "por_tipo": tipos,
    }


def plan_fanout(
    payloads: list[dict[str, Any]] | None,
    *,
    contacts: pd.DataFrame | None = None,
    path: Path | str | None = None,
    allow_example: bool = True,
) -> dict[str, Any]:
    """Monta matriz de roteamento escopo→destinatários sem enviar nada."""
    target = Path(path) if path is not None else resolve_contacts_path(allow_example=allow_example)
    fonte = "ausente"
    if target is not None:
        fonte = "exemplo" if target.resolve() == EXAMPLE_CONTACTS.resolve() else "producao"
        book = contacts if contacts is not None else load_contacts(target)
    else:
        book = pd.DataFrame(columns=REQUIRED_COLS)

    territorial = [
        p
        for p in (payloads or [])
        if str(p.get("escopo") or "").lower() in {"regional", "municipal", "cuiaba"}
    ]
    rows: list[dict[str, Any]] = []
    matched = 0
    sem_dest = 0
    for p in territorial:
        escopo = str(p.get("escopo") or "").lower()
        regional = str(p.get("alvo_nome") if escopo == "regional" else p.get("regional") or "")
        emails, chats = recipients_for(
            escopo,
            regional=regional,
            cod_ibge=str(p.get("alvo_id") or ""),
            municipio=str(p.get("alvo_nome") or ""),
            contacts=book,
        )
        status = "ok" if (emails or chats) else "sem_destinatario"
        if status == "ok":
            matched += 1
        else:
            sem_dest += 1
        rows.append(
            {
                "escopo": escopo,
                "alvo_id": p.get("alvo_id"),
                "alvo_nome": p.get("alvo_nome"),
                "nivel": p.get("nivel"),
                "regional_saude": regional if escopo == "regional" else (p.get("regional") or ""),
                "emails": "; ".join(emails),
                "telegram_chat_ids": "; ".join(chats),
                "n_emails": len(emails),
                "n_chats": len(chats),
                "status_roteamento": status,
            }
        )

    plan_df = pd.DataFrame(rows)
    return {
        "path": str(target) if target is not None else str(contacts_path()),
        "fonte": fonte,
        "fanout_enabled": fanout_enabled(),
        "dry_run_flag": fanout_dry_run_enabled(),
        "n_territoriais": len(territorial),
        "n_com_destinatario": matched,
        "n_sem_destinatario": sem_dest,
        "cobertura_pct": round(100.0 * matched / len(territorial), 1) if territorial else 0.0,
        "plan": plan_df,
    }


def summarize_contacts() -> dict[str, Any]:
    c = _active(load_contacts())
    if c.empty:
        return {
            "path": str(contacts_path()),
            "disponivel": False,
            "fanout_enabled": fanout_enabled(),
            "dry_run": fanout_dry_run_enabled(),
            "n": 0,
        }
    tipos = c["tipo_destinatario"].astype(str).str.lower().value_counts().to_dict()
    return {
        "path": str(contacts_path()),
        "disponivel": True,
        "fanout_enabled": fanout_enabled(),
        "dry_run": fanout_dry_run_enabled(),
        "n": int(len(c)),
        "por_tipo": tipos,
    }


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validação e dry-run do fan-out territorial SIS.")
    parser.add_argument("--csv", default=None, help="Caminho da planilha (default: produção ou exemplo)")
    parser.add_argument("--validate", action="store_true", help="Valida schema/e-mails/tipos")
    parser.add_argument("--plan", action="store_true", help="Monta matriz de roteamento a partir dos boletins atuais")
    parser.add_argument("--min-level", default="laranja", help="Nível mínimo municipal para --plan")
    args = parser.parse_args(argv)

    if not args.validate and not args.plan:
        args.validate = True

    path = Path(args.csv) if args.csv else resolve_contacts_path(allow_example=True)
    rc = 0

    if args.validate:
        report = validate_contacts(path)
        print(f"path={report['path']} fonte={report['fonte']} ok={report['ok']}")
        print(f"linhas={report['n_linhas']} ativos={report['n_ativos']} tipos={report['por_tipo']}")
        for err in report["errors"]:
            print(f"ERROR: {err}")
        for warn in report["warnings"]:
            print(f"WARN: {warn}")
        if not report["ok"]:
            rc = 1

    if args.plan:
        from sisclima.core.db import read_table
        from sisclima.engines.alertas_multinivel import build_alertas_multinivel

        resumo = read_table("resumo_municipal_atual")
        alerta = read_table("alerta_integrado_sis_titan")
        pred = read_table("predicao_calor_7d_municipal_v6")
        payloads = build_alertas_multinivel(
            resumo,
            alerta_integrado=alerta if not alerta.empty else None,
            predicao_7d=pred if not pred.empty else None,
            min_level=args.min_level,
        )
        plan = plan_fanout(payloads, path=path, allow_example=True)
        print(
            f"plan path={plan['path']} fonte={plan['fonte']} "
            f"territoriais={plan['n_territoriais']} "
            f"com_dest={plan['n_com_destinatario']} "
            f"sem_dest={plan['n_sem_destinatario']} "
            f"cobertura={plan['cobertura_pct']}%"
        )
        if not plan["plan"].empty:
            cols = [
                c
                for c in [
                    "escopo",
                    "alvo_nome",
                    "nivel",
                    "emails",
                    "telegram_chat_ids",
                    "status_roteamento",
                ]
                if c in plan["plan"].columns
            ]
            print(plan["plan"][cols].to_string(index=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(_cli())
