# -*- coding: utf-8 -*-
"""Smoke checklist local do painel + tabelas operacionais.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\smoke_ops.py
  .\\.venv\\Scripts\\python.exe scripts\\smoke_ops.py --url http://127.0.0.1:8501
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _http(url: str, timeout: float = 15.0) -> tuple[int, int]:
    req = urllib.request.Request(url, headers={"User-Agent": "ARARAS-Clima-Saude-MT/smoke"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return int(resp.status), len(body)


def _seed_checks(db: Path) -> dict:
    out: dict = {"path": str(db), "ok": db.exists()}
    if not db.exists():
        return out
    con = sqlite3.connect(db)
    try:
        for t in ("resumo_municipal_atual", "hidro_risco_municipal", "ana_telemetria"):
            try:
                n = con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                out[t] = n
            except sqlite3.Error as e:
                out[t] = f"ERR:{e}"
        cols = [r[1] for r in con.execute("PRAGMA table_info(resumo_municipal_atual)")]
        if "indice_pressao_saude" in cols:
            r = con.execute(
                "SELECT COUNT(DISTINCT ROUND(indice_pressao_saude,1)), "
                "AVG(indice_pressao_saude), MAX(indice_pressao_saude) "
                "FROM resumo_municipal_atual"
            ).fetchone()
            out["pressao_distinct_avg_max"] = r
            out["pressao_flat20"] = bool(r and r[0] <= 2 and r[1] and abs(float(r[1]) - 20) < 0.5)
        if "situacao_hidro" in [c[1] for c in con.execute("PRAGMA table_info(hidro_risco_municipal)")]:
            out["hidro_situacao"] = con.execute(
                "SELECT situacao_hidro, COUNT(*) FROM hidro_risco_municipal GROUP BY 1"
            ).fetchall()
            bad = con.execute(
                "SELECT COUNT(*) FROM hidro_risco_municipal WHERE cota_cm IS NOT NULL AND cota_cm >= 5000"
            ).fetchone()[0]
            out["hidro_cota_suspeita_ge5000"] = bad
    finally:
        con.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8501")
    args = ap.parse_args(argv)
    report: dict = {"checks": {}}

    # HTTP
    for path in ("/healthz", "/"):
        url = args.url.rstrip("/") + path
        try:
            status, nbytes = _http(url)
            report["checks"][path] = {"status": status, "bytes": nbytes, "ok": status == 200}
        except Exception as e:  # noqa: BLE001
            report["checks"][path] = {"ok": False, "error": str(e)}

    report["checks"]["seed"] = _seed_checks(ROOT / "data" / "cloud" / "sis_cloud_seed.db")

    ok_http = all(report["checks"].get(p, {}).get("ok") for p in ("/healthz", "/"))
    seed = report["checks"]["seed"]
    ok_seed = bool(seed.get("ok")) and int(seed.get("resumo_municipal_atual") or 0) >= 100
    ok_pressao = not seed.get("pressao_flat20", True)
    ok_hidro = int(seed.get("hidro_cota_suspeita_ge5000") or 0) == 0

    report["summary"] = {
        "http_ok": ok_http,
        "seed_ok": ok_seed,
        "pressao_ok": ok_pressao,
        "hidro_cotas_ok": ok_hidro,
        "all_ok": ok_http and ok_seed and ok_pressao and ok_hidro,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["summary"]["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
