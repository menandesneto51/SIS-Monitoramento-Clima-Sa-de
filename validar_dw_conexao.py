# -*- coding: utf-8 -*-
"""Valida conexão com o DW SQL Server e a base operacional única.

Alinhado aos projetos CIEVS-MT (Meningites / Ondas de calor):
  host 10.15.1.50 · DB Datawarehouse · usuário via .env / DW_ENV_FILE
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sisclima.core.config import env, as_bool
from sisclima.core.db import backend_name, init_db, table_exists, get_engine
from sisclima.ingestion.sqlserver import build_sqlserver_conn, read_sqlserver, use_sqlserver


def _tcp_probe(host: str, port: int = 1433, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP {host}:{port} aceitou conexão"
    except OSError as exc:
        return False, f"TCP {host}:{port} falhou: {exc}"


def _redact(value: str | None) -> str:
    if not value:
        return "—"
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]} (len={len(value)})"


def main() -> int:
    print("=== Validação DW + Base Única ===")
    print(f"Base operacional: {backend_name()}")
    print(f"DATABASE_URL driver: {(env('DATABASE_URL') or '')[:48]}...")
    dw_env = env("DW_ENV_FILE")
    if dw_env:
        print(f"DW_ENV_FILE: {dw_env}")

    ok = True
    try:
        init_db()
        eng = get_engine()
        with eng.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        print("OK base operacional respondendo")
        for t in ["pipeline_runs", "nivel_atual", "alertas_enviados"]:
            print(f"  tabela {t}: {'ok' if table_exists(t) else 'ausente'}")
    except Exception as e:
        ok = False
        print(f"FALHA base operacional: {e}")

    print(f"\nUSE_SQLSERVER={use_sqlserver()}")
    if use_sqlserver():
        server = env("DW_SERVER") or env("DW_HOST")
        database = env("DW_DATABASE")
        user = env("DW_USER")
        password = env("DW_PASSWORD")
        port = int(env("DW_PORT", "1433") or "1433")
        client = env("DW_CLIENT", "auto") or "auto"

        print(f"DW_SERVER/HOST={server}")
        print(f"DW_DATABASE={database}")
        print(f"DW_USER={user}")
        print(f"DW_PASSWORD={_redact(password)}")
        print(f"DW_DRIVER={env('DW_DRIVER') or 'ODBC Driver 17/18 for SQL Server'}")
        print(f"DW_CLIENT={client}")
        print(f"DW_ENCRYPT={env('DW_ENCRYPT', 'no')}")

        if not server or not database or not user or not password:
            ok = False
            print("FALHA: DW_SERVER/DW_DATABASE/DW_USER/DW_PASSWORD incompletos")
            print("  Dica: copie de Meningites/Ondas (.env) ou defina DW_ENV_FILE.")
            print("=== FIM ===")
            return 1

        placeholder = any(
            token in password.upper()
            for token in ("COLE_AQUI", "SENHA_AQUI", "SUA_SENHA", "INFORME_AQUI", "XXXX")
        )
        if placeholder:
            ok = False
            print("FALHA: DW_PASSWORD ainda é placeholder — preencha a senha real no .env")

        tcp_ok, tcp_msg = _tcp_probe(str(server), port)
        print(("OK " if tcp_ok else "FALHA ") + tcp_msg)
        if not tcp_ok:
            ok = False
            print("  Sem TCP não há TDS. Use VPN/rede SES ou rode no host corporativo.")

        conn_str = build_sqlserver_conn("DW")
        if not conn_str and client.lower() == "pyodbc":
            ok = False
            print("FALHA: DSN ODBC incompleto")
        else:
            df = read_sqlserver("DW", "SELECT 1 AS ok")
            if df is None or df.empty:
                ok = False
                print("FALHA: SELECT 1 no DW não retornou (rede/TDS/credencial/driver)")
                print("  TCP aberto ≠ protocolo SQL OK. Confirme ODBC 18 ou pymssql na VPN SES.")
            else:
                print("OK DW SQL Server respondendo")

            probes = {
                "SINAN dengue": "SELECT TOP 1 * FROM dbo.VW_SINAN_DENGUE",
                "SINAN notificação": "SELECT TOP 1 * FROM dbo.VW_SINAN_NOTIFICACAOINDIVIDUAL",
                "GAL": "SELECT TOP 1 * FROM dbo.VW_GAL",
                "CNES": "SELECT TOP 1 * FROM dbo.CNES_ESTABELECIMENTOS",
                "SIM": "SELECT TOP 1 * FROM dbo.SIM",
            }
            for name, sql in probes.items():
                sample = read_sqlserver("DW", sql)
                status = "ok" if sample is not None and not sample.empty else "indisponível/sem retorno"
                print(f"  probe {name}: {status}")
    else:
        print("DW desligado (USE_SQLSERVER=false). Pipeline usará CSV locais.")
        print("Para ligar: USE_SQLSERVER=true + DW_* no .env (ver .env.example / Meningites).")

    print("=== FIM ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
