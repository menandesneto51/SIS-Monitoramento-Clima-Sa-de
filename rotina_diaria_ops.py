# -*- coding: utf-8 -*-
"""
Rotina operacional diária (pipeline DW + ANA + hidro + enrichment + pressão + seed Cloud).

Uso (PowerShell, raiz do repo):
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py --offline
  .\\.venv\\Scripts\\python.exe rotina_diaria_ops.py --skip-cloud-export

Produção: servidor SES na rede interna (DW/IndicaSUS/SISREG locais; sem VPN).
--offline: só notebook/dev fora da SES (pula DW live; clima público continua).
O pipeline nunca dispara alerta (send_alerts=False).
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


def step_prepare() -> dict:
    _step("0/8 Pasta data/input")
    import importlib.util

    path = ROOT / "scripts" / "preparar_data_input.py"
    spec = importlib.util.spec_from_file_location("preparar_data_input", path)
    if spec is None or spec.loader is None:
        (ROOT / "data" / "input" / "sivep_atualizacao").mkdir(parents=True, exist_ok=True)
        return {"status": "mkdir"}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    info = mod.ensure_layout()
    print(f"[INFO] input={info.get('input_dir')} sivep_exports={info.get('sivep_exports')}")
    return info


def step_sivep() -> dict:
    _step("1/8 SIVEP local")
    from sisclima.ingestion.sivep_local import rebuild_sivep_local_db

    info = rebuild_sivep_local_db()
    print(f"[INFO] SIVEP files={info.get('files')} rows={info.get('rows')}")
    return info


def step_pipeline() -> dict:
    _step("2/8 Pipeline clima + DW (sem envio de alerta)")
    os.environ["USE_OPENMETEO"] = "true"
    os.environ["REFRESH_OPENMETEO"] = "true"
    os.environ.setdefault("USE_OPENMETEO_AQ", "true")
    os.environ.setdefault("OPENMETEO_AQ_PAST_DAYS", "7")
    from sisclima.pipeline import run_pipeline

    t0 = time.time()
    out = dict(run_pipeline(send_alerts=False) or {})
    out["elapsed_s"] = round(time.time() - t0, 1)
    try:
        from sisclima.core.db import read_table

        resumo = read_table("resumo_municipal_atual")
        out["n_resumo"] = 0 if resumo is None or resumo.empty else int(resumo["cod_ibge"].nunique()) if "cod_ibge" in resumo.columns else int(len(resumo))
    except Exception:
        out["n_resumo"] = None
    print(f"[INFO] pipeline status={out.get('status')} nivel={out.get('nivel')} n_resumo={out.get('n_resumo')} elapsed={out['elapsed_s']}s")
    return out


def step_ana() -> dict:
    _step("3/8 ANA telemetria + hidro_risco_municipal")
    # força fetch live salvo se já definido false no ambiente e usuário passar --offline
    os.environ.setdefault("USE_ANA", "true")
    os.environ.setdefault("ANA_FETCH_SERIES", "true")
    t0 = time.time()
    # reutiliza validador (grava tabelas + reporta)
    import validar_sentinela_ana as ana

    code = ana.main() if hasattr(ana, "main") else 0
    return {"exit": int(code or 0), "elapsed_s": round(time.time() - t0, 1)}


def step_enrichment(try_indicasus: bool) -> dict:
    _step("4/8 Enrichment operacional (hidro no resumo + pred 7d)")
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
        print("[INFO] IndicaSUS live pulado (--offline ou hosts SES inacessíveis)")

    from sisclima.engines.operational_enrichment import run_operational_enrichment
    from sisclima.ingestion.ibge_municipios import relabel_resumo_municipios

    summary = run_operational_enrichment(reclassify=True)
    try:
        nomes = relabel_resumo_municipios()
        summary["nomes_municipais"] = nomes
        print(f"[INFO] Nomes municipais IBGE: {nomes}")
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] Relabel nomes municipais: {exc}")
    return summary


def step_sisreg(prefer_live: bool) -> dict:
    _step("5/8 SISREG")
    from sisclima.ingestion.sisreg import atualizar_sisreg

    try:
        return atualizar_sisreg(prefer_live=prefer_live)
    except FileNotFoundError as exc:
        if prefer_live:
            raise
        print(f"[AVISO] SISREG offline sem CSV: {exc}")
        return {"status": "offline_sem_csv", "error": str(exc)}


def step_pressao() -> dict:
    _step("6/8 Índice de pressão + merge no resumo")
    from regenerar_sistema_completo import step_pressao_alertas

    return step_pressao_alertas()


def step_validacao_ocupacao() -> dict:
    """CSVs de homologação IndicaSUS (SIEGES) × SISREG — pasta data/output/validacao_ocupacao_sieges."""
    _step("Validação ocupação SIEGES (artefatos CSV)")
    try:
        from sisclima.reporting.validacao_ocupacao_sieges import gerar_pacote_validacao_ocupacao

        meta = gerar_pacote_validacao_ocupacao()
        tot = meta.get("totais") or {}
        print(
            f"[INFO] validação ocupação: com={tot.get('com_ocupacao')} "
            f"sem={tot.get('sem_leitos_elegiveis')} "
            f"ocup%={tot.get('ocupacao_pct_estadual')} → {meta.get('outdir')}"
        )
        return {"ok": True, **{k: tot.get(k) for k in ("com_ocupacao", "sem_leitos_elegiveis", "ocupacao_pct_estadual")}}
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] Pacote validação ocupação: {exc}")
        return {"ok": False, "error": str(exc)}


def step_plano_indicadores() -> dict:
    """Lê tabelas que o pipeline já gravou e reanexa medições do Plano El Niño."""
    _step("Coleta indicadores automáticos do Plano El Niño")
    try:
        from sisclima.plano.indicadores import atualizar_automaticos

        out = dict(atualizar_automaticos() or {})
        print(
            f"[INFO] plano gravados={out.get('gravados')} "
            f"inalterados={out.get('inalterados')} "
            f"aguardando_fonte={out.get('aguardando_fonte')} erros={out.get('erros')}"
        )
        try:
            from sisclima.plano.cobranca import resumo_cobranca
            from sisclima.plano.relatorio_pdf import gerar_pdf_cobranca

            cob = resumo_cobranca()
            path = gerar_pdf_cobranca()
            from sisclima.plano.cobranca import exportar_rascunhos

            pasta = exportar_rascunhos()
            out["cobranca"] = cob
            out["cobranca_pdf"] = str(path)
            out["cobranca_emails"] = str(pasta)
            print(
                f"[INFO] cobrança pendencias={cob.get('n_pendencias')} "
                f"area={cob.get('n_cobrar_area')} fonte={cob.get('n_aguardar_fonte')} "
                f"pdf={path.name}"
            )
        except Exception as cob_exc:  # noqa: BLE001
            print(f"[AVISO] Relatório de cobrança do Plano: {cob_exc}")
            out["cobranca_erro"] = str(cob_exc)
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] Coleta Plano El Niño: {exc}")
        return {"status": "erro", "error": str(exc)}


def step_alerta_cuiaba(*, force: bool = False) -> dict:
    """Gera/envia boletim municipal de Cuiabá (Vigidesastre) na rotina diária."""
    _step("7/8 Alerta municipal Cuiabá (Vigidesastre)")
    from sisclima.core.config import as_bool, env

    enabled = as_bool(env("ALERT_CUIABA_ENABLED", "true"), True)
    send_ok = as_bool(env("ALERT_CUIABA_SEND", env("SEND_ALERT_ON_LEVEL_CHANGE", "false")), False)
    if not enabled:
        print("[INFO] Alerta Cuiabá desligado (ALERT_CUIABA_ENABLED=false)")
        return {"status": "desligado", "enviado": False}

    import alerta_municipal_cuiaba_v11_10 as cui

    argv = ["--force"] if force or as_bool(env("ALERT_CUIABA_FORCE", "false"), False) else []
    if send_ok:
        argv = ["--send", *argv]
    else:
        argv = ["--dry-run", *argv]
        print("[INFO] Prévia Cuiabá (sem envio). Defina ALERT_CUIABA_SEND=true ou SEND_ALERT_ON_LEVEL_CHANGE=true para disparar.")

    try:
        # reusa argparse do script
        old_argv = sys.argv
        sys.argv = ["alerta_municipal_cuiaba_v11_10.py", *argv]
        try:
            cui.main()
            status = "enviado" if send_ok else "preview"
        finally:
            sys.argv = old_argv
        return {"status": status, "enviado": bool(send_ok), "argv": argv}
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        return {"status": "ok" if code == 0 else "erro", "exit": code, "enviado": bool(send_ok and code == 0)}
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] Alerta Cuiabá: {exc}")
        return {"status": "erro", "error": str(exc), "enviado": False}


def step_cloud() -> dict:
    _step("8/9 Export snapshot Cloud")
    import exportar_snapshot_cloud as exp

    if hasattr(exp, "main"):
        code = exp.main()
        return {"exit": int(code or 0)}
    # fallback: chamar como script
    import runpy

    runpy.run_path(str(ROOT / "exportar_snapshot_cloud.py"), run_name="__main__")
    return {"exit": 0}


def step_smoke() -> dict:
    _step("9/9 Smoke operacional pós-ciclo")
    import importlib.util

    path = ROOT / "scripts" / "smoke_ops.py"
    spec = importlib.util.spec_from_file_location("smoke_ops", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"não foi possível carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    code = mod.main([])
    return {"exit": int(code or 0), "ok": int(code or 0) == 0}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rotina diária ARARAS MT (ANA + ops)")
    p.add_argument("--offline", action="store_true", help="Sem DW/IndicaSUS/SISREG live")
    p.add_argument("--skip-pipeline", action="store_true", help="Não roda o pipeline clima/DW")
    p.add_argument("--skip-cloud-export", action="store_true")
    p.add_argument("--skip-ana", action="store_true")
    p.add_argument("--skip-smoke", action="store_true", help="Não roda scripts/smoke_ops.py ao final")
    args = p.parse_args(argv)

    probe = _probe_ses()
    ses_ok = probe["dw"] or probe["indicasus"] or probe["sisreg"]
    offline = bool(args.offline or not ses_ok)
    if not args.offline and not ses_ok:
        print("[AVISO] Hosts SES (DW/IndicaSUS/SISREG) inacessíveis no servidor — fallback CSV/cache.")
        print(json.dumps(probe, ensure_ascii=False))

    report: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "offline": offline,
        "probe": probe,
        "steps": {},
    }

    try:
        report["steps"]["prepare"] = step_prepare()
        report["steps"]["sivep"] = step_sivep()
        if not args.skip_pipeline:
            if offline:
                print("[INFO] Pipeline climático (Open-Meteo/AQ/INPE); DW live só com hosts SES no ar.")
            report["steps"]["pipeline"] = step_pipeline()
        if not args.skip_ana:
            report["steps"]["ana"] = step_ana()
        report["steps"]["enrichment"] = step_enrichment(try_indicasus=not offline)
        report["steps"]["sisreg"] = step_sisreg(prefer_live=not offline)
        report["steps"]["pressao"] = step_pressao()
        report["steps"]["validacao_ocupacao"] = step_validacao_ocupacao()
        report["steps"]["plano_indicadores"] = step_plano_indicadores()
        report["steps"]["alerta_cuiaba"] = step_alerta_cuiaba()
        if not args.skip_cloud_export:
            report["steps"]["cloud"] = step_cloud()
        if not args.skip_smoke:
            report["steps"]["smoke"] = step_smoke()
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
    smoke_ok = report.get("steps", {}).get("smoke", {}).get("ok", True)
    print("\n[OK] Rotina diária concluída." if smoke_ok else "\n[AVISO] Rotina concluída, mas smoke falhou.")
    print(f"[LOG] {out}")
    return 0 if smoke_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
