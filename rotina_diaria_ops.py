# -*- coding: utf-8 -*-
"""
Rotina operacional diária (ANA + hidro + enrichment + pressão + seed Cloud).

Uso (PowerShell, raiz do repo):
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py --offline
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py --skip-cloud-export

--offline: não tenta IndicaSUS/SISREG live (CSV/cache); útil sem VPN SES.
Com VPN: omita --offline para refresh live quando os hosts responderem.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _step(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {title}")
    print("=" * 72)


def _tcp_ok(host: str | None, port: int = 1433, timeout: float = 2.5) -> bool:
    if not host:
        return False
    h = str(host).split(",")[0].strip()
    if not h:
        return False
    try:
        with socket.create_connection((h, port), timeout=timeout):
            return True
    except OSError:
        return False


def _probe_ses() -> dict:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    dw = os.getenv("DW_HOST") or os.getenv("DW_SERVER")
    ind = os.getenv("INDICASUS_HOST") or os.getenv("INDICASUS_SERVER")
    sis = os.getenv("SISREG_HOST")
    return {
        "dw": _tcp_ok(dw),
        "indicasus": _tcp_ok(ind),
        "sisreg": _tcp_ok(sis),
        "hosts": {"dw": dw, "indicasus": ind, "sisreg": sis},
    }


def step_ana() -> dict:
    _step("1/5 ANA telemetria + hidro_risco_municipal")
    # força fetch live salvo se já definido false no ambiente e usuário passar --offline
    os.environ.setdefault("USE_ANA", "true")
    os.environ.setdefault("ANA_FETCH_SERIES", "true")
    t0 = time.time()
    # reutiliza validador (grava tabelas + reporta)
    import validar_sentinela_ana as ana

    code = ana.main() if hasattr(ana, "main") else 0
    return {"exit": int(code or 0), "elapsed_s": round(time.time() - t0, 1)}


def step_enrichment(try_indicasus: bool) -> dict:
    _step("2/5 Enrichment operacional (hidro no resumo + pred 7d)")
    if try_indicasus:
        try:
            from atualizar_ocupacao_indicasus import main as upd_occ

            print("[INFO] IndicaSUS ocupação...")
            try:
                upd_occ()
            except SystemExit:
                pass
        except Exception as exc:  # noqa: BLE001
            print(f"[AVISO] IndicaSUS: {exc}")
    else:
        print("[INFO] IndicaSUS live pulado (offline / VPN ausente)")

    from sisclima.engines.operational_enrichment import run_operational_enrichment

    return run_operational_enrichment(reclassify=True)


def step_sisreg(prefer_live: bool) -> dict:
    _step("3/5 SISREG")
    from sisclima.ingestion.sisreg import atualizar_sisreg

    return atualizar_sisreg(prefer_live=prefer_live)


def step_pressao() -> dict:
    _step("4/5 Índice de pressão + merge no resumo")
    from regenerar_sistema_completo import step_pressao_alertas

    return step_pressao_alertas()


def step_cloud() -> dict:
    _step("5/5 Export snapshot Cloud")
    import exportar_snapshot_cloud as exp

    if hasattr(exp, "main"):
        code = exp.main()
        return {"exit": int(code or 0)}
    # fallback: chamar como script
    import runpy

    runpy.run_path(str(ROOT / "exportar_snapshot_cloud.py"), run_name="__main__")
    return {"exit": 0}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rotina diária SIS Clima-Saúde (ANA + ops)")
    p.add_argument("--offline", action="store_true", help="Sem DW/IndicaSUS/SISREG live")
    p.add_argument("--skip-cloud-export", action="store_true")
    p.add_argument("--skip-ana", action="store_true")
    args = p.parse_args(argv)

    probe = _probe_ses()
    vpn_ok = probe["dw"] or probe["indicasus"] or probe["sisreg"]
    offline = bool(args.offline or not vpn_ok)
    if not args.offline and not vpn_ok:
        print("[AVISO] Hosts SES (DW/IndicaSUS/SISREG) inacessíveis — modo offline automático.")
        print(json.dumps(probe, ensure_ascii=False))

    report: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "offline": offline,
        "probe": probe,
        "steps": {},
    }

    try:
        if not args.skip_ana:
            report["steps"]["ana"] = step_ana()
        report["steps"]["enrichment"] = step_enrichment(try_indicasus=not offline)
        report["steps"]["sisreg"] = step_sisreg(prefer_live=not offline)
        report["steps"]["pressao"] = step_pressao()
        if not args.skip_cloud_export:
            report["steps"]["cloud"] = step_cloud()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERRO] {exc}", file=sys.stderr)
        report["error"] = str(exc)
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        out = logs / f"rotina_diaria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[LOG] {out}")
        return 1

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"rotina_diaria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n[OK] Rotina diária concluída.")
    print(f"[LOG] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
