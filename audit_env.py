"""Auditoria operacional do .env (sem imprimir segredos).

Uso:
  .\\.venv\\Scripts\\python.exe audit_env.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sisclima.core.config import ROOT, env, as_bool, env_name_used
from sisclima.validation.validate_sources import looks_like_placeholder
from sisclima.validation.preflight import run_preflight, summarize_preflight

SECRET_MARKERS = ("PASSWORD", "SENHA", "TOKEN", "KEY", "PWD", "PASS", "SECRET")


def _redact(key: str, value: str | None) -> str:
    if value is None or str(value).strip() == "":
        return "(vazio)"
    if looks_like_placeholder(value):
        return "***placeholder***"
    if any(m in key.upper() for m in SECRET_MARKERS):
        return "***configurado***"
    text = str(value)
    if len(text) > 90:
        return text[:87] + "..."
    return text


def _status(ok: bool) -> str:
    return "OK" if ok else "PENDENTE"


def _check_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    env_path = ROOT / ".env"
    print("=== AUDITORIA .env ===")
    print(f"arquivo: {env_path} | existe={env_path.exists()}")
    print()

    checks: list[tuple[str, bool, str]] = []

    # Flags principais
    flags = {
        "USE_SQLSERVER": as_bool(env("USE_SQLSERVER", "false")),
        "USE_OPENMETEO": as_bool(env("USE_OPENMETEO", "true"), True),
        "USE_INMET": as_bool(env("USE_INMET", "false")),
        "USE_COPERNICUS": as_bool(env("USE_COPERNICUS", "false")),
        "USE_SIVEP_LOCAL": as_bool(env("USE_SIVEP_LOCAL", "true"), True),
        "USE_EMAIL / ALERT_EMAIL_ENABLED": as_bool(env("ALERT_EMAIL_ENABLED", "false")),
        "USE_TELEGRAM / ALERT_TELEGRAM_ENABLED": as_bool(env("ALERT_TELEGRAM_ENABLED", "false")),
        "RUN_PREFLIGHT": as_bool(env("RUN_PREFLIGHT", "false")),
        "SEND_ALERT_ON_LEVEL_CHANGE": as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false")),
    }
    print("--- flags ---")
    for k, v in flags.items():
        print(f"{k}={v}")
    print()

    # Credenciais / configs críticas
    items = [
        ("DW_SERVER", env("DW_SERVER"), flags["USE_SQLSERVER"]),
        ("DW_DATABASE", env("DW_DATABASE"), flags["USE_SQLSERVER"]),
        ("DW_USER", env("DW_USER"), flags["USE_SQLSERVER"]),
        ("DW_PASSWORD", env("DW_PASSWORD"), flags["USE_SQLSERVER"]),
        ("DW_ENCRYPT", env("DW_ENCRYPT") or "no", False),
        ("DW_TRUST_SERVER_CERTIFICATE", env("DW_TRUST_SERVER_CERTIFICATE") or "yes", False),
        ("INMET_ALERTS_URL", env("INMET_ALERTS_URL"), flags["USE_INMET"]),
        ("COPERNICUS_KEY", env("COPERNICUS_KEY"), flags["USE_COPERNICUS"]),
        ("SMTP_HOST", env("SMTP_HOST"), flags["USE_EMAIL / ALERT_EMAIL_ENABLED"]),
        ("SMTP_USER", env("SMTP_USER"), flags["USE_EMAIL / ALERT_EMAIL_ENABLED"]),
        ("SMTP_PASSWORD", env("SMTP_PASSWORD"), flags["USE_EMAIL / ALERT_EMAIL_ENABLED"]),
        ("ALERT_EMAIL_TO", env("ALERT_EMAIL_TO") or env("EMAIL_TO"), flags["USE_EMAIL / ALERT_EMAIL_ENABLED"]),
        ("TELEGRAM_BOT_TOKEN", env("TELEGRAM_BOT_TOKEN"), flags["USE_TELEGRAM / ALERT_TELEGRAM_ENABLED"]),
        ("TELEGRAM_CHAT_ID", env("TELEGRAM_CHAT_ID") or env("TG_CHAT_ID"), flags["USE_TELEGRAM / ALERT_TELEGRAM_ENABLED"]),
    ]

    print("--- variáveis (valores mascarados) ---")
    for key, value, required in items:
        used = env_name_used(key) or key
        placeholder = looks_like_placeholder(value)
        present = bool(value) and not placeholder
        ok = present or not required
        detail = f"{used}={_redact(key, value)}"
        if required and placeholder:
            detail += " | ainda é placeholder"
        elif required and not value:
            detail += " | ausente"
        checks.append((key, ok, detail))
        print(f"[{_status(ok)}] {detail}")
    print()

    # IndicaSUS dedicado (script auxiliar local)
    ind_host = env("INDICASUS_HOST") or env("INDICASUS_SERVER")
    ind_db = env("INDICASUS_DATABASE") or env("INDICASUS_DB")
    ind_user = env("INDICASUS_USER")
    ind_pwd = env("INDICASUS_PASSWORD")
    ind_ok = bool(ind_host and ind_db and ind_user and ind_pwd and not looks_like_placeholder(ind_pwd))
    checks.append((
        "INDICASUS dedicado",
        ind_ok,
        (
            f"HOST={_redact('INDICASUS_HOST', ind_host)} "
            f"DB={_redact('INDICASUS_DATABASE', ind_db)} "
            f"USER={_redact('INDICASUS_USER', ind_user)} "
            f"PASSWORD={_redact('INDICASUS_PASSWORD', ind_pwd)}"
            + ("" if ind_ok else " | necessário para atualizar_ocupacao_indicasus.py")
        ),
    ))

    # Pacotes opcionais
    cdsapi_ok = _check_module("cdsapi")
    pyodbc_ok = _check_module("pyodbc")
    checks.append(("pacote pyodbc", pyodbc_ok, "instalado" if pyodbc_ok else "ausente"))
    checks.append((
        "pacote cdsapi",
        cdsapi_ok or not flags["USE_COPERNICUS"],
        "instalado" if cdsapi_ok else "ausente (USE_COPERNICUS=true precisa de: pip install cdsapi)",
    ))

    # Arquivo .cdsapirc
    cds_dot = (ROOT / ".cdsapirc").exists() or (Path.home() / ".cdsapirc").exists()
    if flags["USE_COPERNICUS"]:
        key_ok = bool(env("COPERNICUS_KEY")) and not looks_like_placeholder(env("COPERNICUS_KEY"))
        checks.append((
            "credencial Copernicus efetiva",
            key_ok or cds_dot,
            ".cdsapirc encontrado" if cds_dot else ("COPERNICUS_KEY ok" if key_ok else "sem chave válida nem .cdsapirc"),
        ))

    print("--- pendências detectadas ---")
    pending = [(n, d) for n, ok, d in checks if not ok]
    if not pending:
        print("Nenhuma pendência de configuração detectada neste auditor.")
    else:
        for name, detail in pending:
            print(f"- {name}: {detail}")
    print()

    print("--- preflight ---")
    df = run_preflight()
    summary = summarize_preflight(df)
    fails = df[~df["ok"]].copy()
    if fails.empty:
        print("preflight sem falhas")
    else:
        for _, row in fails.iterrows():
            print(f"- [{row['severity']}] {row['item']}: {row['detail']}")
    print("RESUMO preflight:", summary)
    print()

    print("--- recomendações práticas (com base no último ciclo) ---")
    print("1) Se INMET_ALERTS_URL ainda for placeholder: use USE_INMET=false")
    print("2) Se cdsapi faltar e Copernicus estiver ligado: pip install cdsapi")
    print("3) Se atualizar_ocupacao_indicasus.py falhar: preencha INDICASUS_HOST/DATABASE/USER/PASSWORD")
    print("4) Open-Meteo com SSL self-signed: revisar proxy/antivírus corporativo (não é .env)")
    print("5) Só use send_alerts=True depois de validar SMTP/Telegram")

    # Código de saída: 0 se preflight crítico ok e sem pendências obrigatórias do auditor
    critical = int(summary.get("critical_fail") or 0)
    return 2 if critical > 0 or pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
