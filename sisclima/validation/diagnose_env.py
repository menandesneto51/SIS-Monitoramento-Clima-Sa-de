# -*- coding: utf-8 -*-
"""
Diagnóstico de configuração (.env) sem expor segredos.

Uso:
    python -m sisclima.validation.diagnose_env
"""

from __future__ import annotations

from pathlib import Path

from sisclima.core.config import ROOT, env, env_name_used, ENV_ALIASES
from sisclima.ingestion.sqlserver import build_sqlserver_conn, dw_configured, read_sqlserver, use_sqlserver

SECRET_KEYS = {"PASSWORD", "SENHA", "TOKEN", "KEY", "PWD", "PASS"}


def _redact(name: str, value: str | None) -> str:
    if not value:
        return "(ausente)"
    if any(w in name.upper() for w in SECRET_KEYS):
        return "***configurado***"
    return value


def _env_files() -> list[Path]:
    candidates = [
        ROOT / ".env",
        ROOT / ".env.local",
        ROOT / "secrets.env",
        ROOT.parent / ".env",
    ]
    return [p for p in candidates if p.exists()]


def _check_canonical(key: str) -> dict:
    used = env_name_used(key)
    value = env(key)
    aliases = ENV_ALIASES.get(key, [key])
    return {
        "chave": key,
        "ok": bool(value),
        "alias_usado": used or "(nenhum)",
        "valor": _redact(used or key, value),
        "aliases": ", ".join(aliases[:6]) + ("..." if len(aliases) > 6 else ""),
    }


def main() -> int:
    print("=== DIAGNÓSTICO DE CONFIGURAÇÃO ===\n")
    print("Arquivos .env encontrados:")
    for p in _env_files():
        print(f"  - {p}")
    if not _env_files():
        print("  (nenhum — configure .env ou .env.local na raiz do projeto)")

    print("\n--- Data Warehouse ---")
    for key in ["USE_SQLSERVER", "DW_SERVER", "DW_DATABASE", "DW_USER", "DW_PASSWORD", "DW_DRIVER"]:
        row = _check_canonical(key)
        mark = "OK" if row["ok"] else "FALTA"
        print(f"  [{mark}] {row['chave']}: {row['valor']}  (via {row['alias_usado']})")

    configured = dw_configured()
    active = use_sqlserver()
    print(f"\n  dw_configured: {configured}")
    print(f"  use_sqlserver: {active}")

    if configured:
        print("\n  Testando conexão (SELECT 1)...")
        df = read_sqlserver("DW", "SELECT 1 AS ok")
        if df.empty:
            print("  [FALHA] Não conectou — verifique VPN, servidor e credenciais")
            return 1
        print("  [OK] Conexão DW estabelecida")
        return 0

    print("\n  DW não detectado neste ambiente.")
    print("  Se o projeto já roda em produção, copie o .env de lá para:")
    print(f"    {ROOT / '.env'}")
    print("  ou configure secrets no ambiente cloud (Cursor Environment).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
