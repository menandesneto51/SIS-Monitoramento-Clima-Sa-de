# -*- coding: utf-8 -*-
"""Smoke de homologação pré-produção — gates do plano ARARAS MT.

Uso:
  python scripts/smoke_homologacao_producao.py
  python scripts/smoke_homologacao_producao.py --json logs/homologacao_smoke.json

Não imprime senhas. Exit 0 se all_ok; 1 se algum gate bloqueante falhar.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

# Limiar operacional de frescor EHF (dias)
EHF_MAX_IDADE_DIAS = 3
CLIMA_MAX_LAG_DIAS = 2


def _ok(v: bool) -> str:
    return "OK" if v else "NOK"


def _tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(url: str, timeout: float = 10.0) -> tuple[bool, int | None]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ARARAS-Clima-Saude-MT/homolog"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status) == 200, int(resp.status)
    except Exception:
        return False, None


def _redact_url(url: str | None) -> str:
    if not url:
        return "MISSING"
    if "://" not in url:
        return "SET"
    try:
        pre, rest = url.split("://", 1)
        _, host = rest.split("@", 1)
        return f"{pre}://***@{host}"
    except Exception:
        return "SET(redacted)"


def _gate_env(report: dict[str, Any]) -> None:
    e = dotenv_values(ROOT / ".env")
    db = str(e.get("DATABASE_URL") or "")
    is_pg = "postgres" in db.lower()
    send = str(e.get("SEND_ALERT_ON_LEVEL_CHANGE") or "").lower() in {"1", "true", "yes"}
    fanout = str(e.get("ALERT_FANOUT_ENABLED") or "").lower() in {"1", "true", "yes"}
    contacts = str(e.get("ALERT_CONTACTS_CSV") or "")
    piloto = "piloto" in contacts.lower()
    checks = {
        "DATABASE_URL_postgres": is_pg,
        "DATABASE_URL": _redact_url(db),
        "SEND_ALERT_ON_LEVEL_CHANGE_false": not send,
        "ALERT_FANOUT_ENABLED_false": not fanout,
        "ALERT_PILOTO_RESTRITO": piloto if (send or fanout) else True,
        "DW_HOST": e.get("DW_HOST") or e.get("DW_SERVER") or "MISSING",
        "INDICASUS_HOST": e.get("INDICASUS_HOST") or e.get("BDSES_HOST") or "MISSING",
        "SISREG_HOST": e.get("SISREG_HOST") or "MISSING",
    }
    report["env"] = checks
    report["gates"]["env_postgres"] = is_pg
    # Aceita envio desligado OU piloto restrito (Cuiabá/Sorriso)
    report["gates"]["alertas_envio_desligado"] = ((not send) and (not fanout)) or bool(piloto)


def _gate_rede(report: dict[str, Any]) -> None:
    hosts = {
        "DW_1433": (os.getenv("DW_HOST") or os.getenv("DW_SERVER") or "10.15.1.50", 1433),
        "IndicaSUS_1433": (os.getenv("INDICASUS_HOST") or os.getenv("BDSES_HOST") or "10.15.0.222", 1433),
        "SISREG_1433": (os.getenv("SISREG_HOST") or "10.15.1.71", 1433),
    }
    out = {}
    all_ok = True
    for name, (host, port) in hosts.items():
        ok = _tcp(host, port)
        out[name] = {"host": host, "port": port, "ok": ok}
        all_ok = all_ok and ok
    report["rede"] = out
    report["gates"]["rede_sql_ses"] = all_ok


def _gate_http(report: dict[str, Any], base: str) -> None:
    ok_h, st_h = _http_ok(base.rstrip("/") + "/healthz")
    ok_r, st_r = _http_ok(base.rstrip("/") + "/")
    report["http"] = {
        "base": base,
        "healthz": {"ok": ok_h, "status": st_h},
        "home": {"ok": ok_r, "status": st_r},
    }
    report["gates"]["painel_healthz"] = ok_h


def _gate_dados(report: dict[str, Any]) -> None:
    from sisclima.core.db import read_table

    out: dict[str, Any] = {}
    try:
        resumo = read_table("resumo_municipal_atual")
    except Exception as exc:  # noqa: BLE001
        report["dados"] = {"error": str(exc)}
        report["gates"]["resumo_142"] = False
        report["gates"]["ocupacao_sem_fallback"] = False
        report["gates"]["ehf_presente"] = False
        report["gates"]["rit_presente"] = False
        report["gates"]["clima_fresco"] = False
        report["gates"]["ehf_fresco"] = False
        return

    n = len(resumo)
    out["n_municipios"] = n
    report["gates"]["resumo_142"] = n == 142

    fontes = resumo.get("fonte_ocupacao")
    if fontes is not None:
        s = fontes.astype(str).str.upper()
        n_fb = int(s.str.contains("FALLBACK", na=False).sum())
        n_live = int(s.str.contains("INDICASUS", na=False).sum())
        n_sem = int(s.str.contains("SEM_LEITOS", na=False).sum())
        out["ocupacao"] = {"fallback": n_fb, "indicasus": n_live, "sem_leitos": n_sem}
        report["gates"]["ocupacao_sem_fallback"] = n_fb == 0
    else:
        out["ocupacao"] = {"error": "coluna fonte_ocupacao ausente"}
        report["gates"]["ocupacao_sem_fallback"] = False

    ehf_ok = "ehf_geocalor" in resumo.columns and resumo["ehf_geocalor"].notna().sum() >= 100
    rit_ok = "rit_0_100" in resumo.columns and resumo["rit_0_100"].notna().sum() >= 100
    out["ehf_non_null"] = int(resumo["ehf_geocalor"].notna().sum()) if "ehf_geocalor" in resumo.columns else 0
    out["rit_non_null"] = int(resumo["rit_0_100"].notna().sum()) if "rit_0_100" in resumo.columns else 0
    report["gates"]["ehf_presente"] = bool(ehf_ok)
    report["gates"]["rit_presente"] = bool(rit_ok)

    # Frescor EHF
    idade = None
    if "ehf_geocalor_idade_dias" in resumo.columns and resumo["ehf_geocalor_idade_dias"].notna().any():
        idade = float(resumo["ehf_geocalor_idade_dias"].dropna().median())
    elif "data_ehf_geocalor" in resumo.columns and resumo["data_ehf_geocalor"].notna().any():
        dmax = str(resumo["data_ehf_geocalor"].dropna().astype(str).max())[:10]
        try:
            idade = (date.today() - date.fromisoformat(dmax)).days
        except ValueError:
            idade = None
    out["ehf_idade_dias_mediana"] = idade
    # Idade negativa = data futura (forecast) — não conta como EHF observado fresco.
    report["gates"]["ehf_fresco"] = (
        idade is not None and 0 <= idade <= EHF_MAX_IDADE_DIAS
    )

    # Frescor clima via hist / data no resumo
    clima_ok = False
    data_ref = None
    for col in ("data", "data_referencia", "atualizado_em"):
        if col in resumo.columns and resumo[col].notna().any():
            data_ref = str(resumo[col].dropna().astype(str).max())[:10]
            break
    out["data_resumo"] = data_ref
    if data_ref:
        try:
            lag = (date.today() - date.fromisoformat(data_ref[:10])).days
            out["clima_lag_dias"] = lag
            clima_ok = lag <= CLIMA_MAX_LAG_DIAS
        except ValueError:
            pass
    report["gates"]["clima_fresco"] = clima_ok

    # Cuiabá pontual
    if "cod_ibge" in resumo.columns:
        m = resumo[
            resumo["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7).eq("5103403")
        ]
        if not m.empty:
            row = m.iloc[0]
            out["cuiaba"] = {
                "nivel": row.get("nivel") or row.get("nivel_operacional"),
                "ehf_geocalor": None if row.get("ehf_geocalor") != row.get("ehf_geocalor") else row.get("ehf_geocalor"),
                "data_ehf_geocalor": str(row.get("data_ehf_geocalor") or ""),
                "rit_0_100": row.get("rit_0_100"),
                "rit_faixa": row.get("rit_faixa"),
            }

    report["dados"] = out


def _gate_etl_health(report: dict[str, Any]) -> None:
    path = ROOT / "logs" / "etl_scheduler_health.json"
    if not path.exists():
        report["etl_health"] = {"ok": False, "error": "arquivo ausente"}
        report["gates"]["etl_health_file"] = False
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ok = str(data.get("status") or data.get("pipeline_status") or "").lower() == "success"
        report["etl_health"] = {
            "ok": ok,
            "finished_at": data.get("finished_at"),
            "geocalor_max_data": data.get("geocalor_max_data"),
            "geocalor_idade_dias": data.get("geocalor_idade_dias"),
        }
        report["gates"]["etl_health_file"] = ok
    except Exception as exc:  # noqa: BLE001
        report["etl_health"] = {"ok": False, "error": str(exc)}
        report["gates"]["etl_health_file"] = False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Smoke homologação produção ARARAS MT")
    ap.add_argument("--url", default=os.getenv("PAINEL_URL", "http://127.0.0.1:8501"))
    ap.add_argument("--json", default=str(ROOT / "logs" / "homologacao_smoke.json"))
    ap.add_argument("--skip-rede", action="store_true", help="Pular testes TCP 1433")
    args = ap.parse_args(argv)

    report: dict[str, Any] = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "branch_hint": "ver git branch no host",
        "gates": {},
    }
    _gate_env(report)
    if not args.skip_rede:
        _gate_rede(report)
    else:
        report["rede"] = {"skipped": True}
        report["gates"]["rede_sql_ses"] = True
    _gate_http(report, args.url)
    _gate_dados(report)
    _gate_etl_health(report)

    # Bloqueantes Fase 1 (go-live painel+ETL)
    blockers = [
        "env_postgres",
        "alertas_envio_desligado",
        "painel_healthz",
        "resumo_142",
        "ocupacao_sem_fallback",
        "ehf_presente",
        "rit_presente",
    ]
    # Frescor e rede: aviso se NOK, mas rede fora da SES pode ser skip
    soft = ["clima_fresco", "ehf_fresco", "etl_health_file", "rede_sql_ses"]

    gate_results = report["gates"]
    hard_fail = [g for g in blockers if not gate_results.get(g)]
    soft_fail = [g for g in soft if not gate_results.get(g)]
    report["hard_fail"] = hard_fail
    report["soft_fail"] = soft_fail
    report["all_ok"] = len(hard_fail) == 0
    report["parecer"] = (
        "APROVADO_FASE1_COM_RESSALVAS" if report["all_ok"] and soft_fail else
        "APROVADO_FASE1" if report["all_ok"] else
        "BLOQUEADO"
    )

    out_path = Path(args.json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"PARECER: {report['parecer']}")
    print("Gates:")
    for k, v in sorted(gate_results.items()):
        print(f"  {_ok(bool(v))}: {k}")
    if hard_fail:
        print("Bloqueantes:", ", ".join(hard_fail))
    if soft_fail:
        print("Ressalvas:", ", ".join(soft_fail))
    print(f"JSON: {out_path}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
