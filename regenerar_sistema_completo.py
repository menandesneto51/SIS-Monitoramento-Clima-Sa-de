# -*- coding: utf-8 -*-
"""
Regenera a base operacional completa do SIS Clima-Saúde e prepara o painel.

Passos:
  1) pipeline (fontes clima/saúde/DW) → Postgres
  2) completar_sistema_operacional (IndicaSUS + enrichment + pred 7d)
  3) SISREG live → ops_sisreg_municipio
  4) índice de pressão + alertas multinível persistidos
  5) apresentação impacto (opcional)

Uso:
  .venv\\Scripts\\python.exe regenerar_sistema_completo.py
  .venv\\Scripts\\python.exe regenerar_sistema_completo.py --skip-pipeline
  .venv\\Scripts\\python.exe regenerar_sistema_completo.py --pptx
"""
from __future__ import annotations

import argparse
import json
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


def step_pipeline(send_alerts: bool = False) -> dict:
    _step("1/5 Pipeline completo (clima + DW + estágios)")
    from sisclima.pipeline import run_pipeline

    t0 = time.time()
    out = run_pipeline(send_alerts=send_alerts)
    out = dict(out or {})
    out["elapsed_s"] = round(time.time() - t0, 1)
    print(json.dumps({k: out.get(k) for k in ("run_id", "status", "nivel", "score", "elapsed_s")}, ensure_ascii=False))
    return out


def step_enrichment() -> dict:
    _step("2/5 Enriquecimento operacional (IndicaSUS + pred 7d + indicadores)")
    # IndicaSUS (best-effort)
    try:
        from atualizar_ocupacao_indicasus import main as upd_occ

        print("[INFO] Atualizando IndicaSUS...")
        try:
            upd_occ()
        except SystemExit:
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] IndicaSUS: {exc}")

    from sisclima.engines.operational_enrichment import run_operational_enrichment

    summary = run_operational_enrichment(reclassify=True)
    print(json.dumps({k: summary.get(k) for k in list(summary)[:12]}, ensure_ascii=False, default=str))
    return summary


def step_sisreg() -> dict:
    _step("3/5 SISREG (live → ops_sisreg_municipio)")
    from sisclima.ingestion.sisreg import atualizar_sisreg

    meta = atualizar_sisreg(prefer_live=True)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def step_pressao_alertas() -> dict:
    _step("4/5 Índice de pressão + alertas multinível")
    from sisclima.core.db import read_table, write_df
    from sisclima.engines.alertas_multinivel import build_alertas_multinivel, persist_payloads
    from sisclima.engines.indice_pressao_saude import (
        build_indice_pressao_municipal,
        catalogo_agravos,
        state_pressao_summary,
    )

    resumo = read_table("resumo_municipal_atual")
    pred = read_table("predicao_calor_7d_municipal_v6")
    sis = read_table("ops_sisreg_municipio")
    alerta_int = read_table("alerta_integrado_sis_titan")
    sim = read_table("sim_obitos_calor_municipal_v6")
    saude = read_table("saude_calor_municipio")

    if resumo is None or resumo.empty:
        raise RuntimeError("resumo_municipal_atual vazio após pipeline/enrichment.")

    press = build_indice_pressao_municipal(
        resumo,
        sim_mun=sim if not sim.empty else None,
        saude_calor_mun=saude if not saude.empty else None,
        pred_7d=pred if not pred.empty else None,
        sisreg=sis if not sis.empty else None,
    )
    # Persistir tabela dedicada + merge colunas-chave no resumo
    keep = [
        c
        for c in press.columns
        if c == "cod_ibge"
        or c.startswith("kpi_")
        or c.startswith("indice_pressao")
        or c.startswith("semaforo_pressao")
        or c.startswith("pred_indice")
        or c.startswith("pred_nivel_clima")
        or c.startswith("tendencia_pressao")
        or c == "pilares_disponiveis"
    ]
    snap = press[keep].copy() if keep else press.copy()
    write_df(snap, "indice_pressao_saude_municipal_v1", if_exists="replace")
    cat = catalogo_agravos()
    if not cat.empty:
        write_df(cat, "catalogo_agravos_clima_pressao_v1", if_exists="replace")

    # Merge no resumo para o painel já vir com pressão persistida
    merge_cols = [
        c
        for c in (
            "cod_ibge",
            "indice_pressao_saude",
            "semaforo_pressao",
            "pred_indice_pressao_7d",
            "semaforo_pressao_pred_7d",
            "tendencia_pressao_7d",
            "kpi_indicasus_valor",
            "kpi_indicasus_semaforo",
            "kpi_sisreg_semaforo",
            "kpi_sisreg_solicitacoes",
            "kpi_sisreg_fila_h",
            "kpi_sinan_semaforo",
            "kpi_sinan_casos_7d",
            "kpi_sim_semaforo",
            "kpi_sim_obitos",
            "pilares_disponiveis",
        )
        if c in press.columns
    ]
    if merge_cols:
        base = resumo.copy()
        drop = [c for c in merge_cols if c != "cod_ibge" and c in base.columns]
        if drop:
            base = base.drop(columns=drop, errors="ignore")
        base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        m = press[merge_cols].copy()
        m["cod_ibge"] = m["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        base = base.merge(m, on="cod_ibge", how="left")
        write_df(base, "resumo_municipal_atual", if_exists="replace")

    payloads = build_alertas_multinivel(
        read_table("resumo_municipal_atual"),
        alerta_integrado=alerta_int if not alerta_int.empty else None,
        predicao_7d=pred if not pred.empty else None,
        min_level="amarela",
    )
    n_alertas = persist_payloads(payloads)
    st = state_pressao_summary(press)
    out = {
        "pressao": st,
        "n_alertas": n_alertas,
        "estadual": next((p.get("nivel") for p in payloads if p.get("escopo") == "estadual"), None),
        "cuiaba": next((p.get("nivel") for p in payloads if p.get("escopo") == "cuiaba"), None),
        "sisreg_cobertura": st.get("sisreg_cobertura"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def step_pptx() -> str:
    _step("5/5 Apresentação impacto com dados reais")
    from gerar_apresentacao_sis_impacto_real import build, DEFAULT_OUT

    path, data = build(DEFAULT_OUT)
    print(f"[OK] {path} · alertas={data.get('n_alertas')}")
    return str(path)


def step_validate() -> dict:
    from sisclima.core.db import backend_name, read_table

    tables = [
        "resumo_municipal_atual",
        "ops_sisreg_municipio",
        "indice_pressao_saude_municipal_v1",
        "alertas_multinivel_v1",
        "predicao_calor_7d_municipal_v6",
        "alerta_integrado_sis_titan",
        "hospital_ocupacao_municipio",
        "epi_arboviroses_municipal",
    ]
    out = {"backend": backend_name(), "tables": {}}
    for t in tables:
        df = read_table(t)
        out["tables"][t] = int(len(df))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenera base + painel SIS Clima-Saúde")
    ap.add_argument("--skip-pipeline", action="store_true", help="Pula o pipeline bruto")
    ap.add_argument("--skip-sisreg", action="store_true")
    ap.add_argument("--pptx", action="store_true", help="Gera PPTX impacto ao final")
    ap.add_argument("--send-alerts", action="store_true", help="Permite disparo no pipeline (default: false)")
    args = ap.parse_args()

    report: dict = {"started_at": datetime.now().isoformat(timespec="seconds"), "ok": False}
    try:
        if not args.skip_pipeline:
            report["pipeline"] = step_pipeline(send_alerts=bool(args.send_alerts))
        else:
            print("[INFO] Pipeline pulado (--skip-pipeline)")

        report["enrichment"] = step_enrichment()
        if not args.skip_sisreg:
            report["sisreg"] = step_sisreg()
        report["pressao_alertas"] = step_pressao_alertas()
        report["validacao"] = step_validate()
        if args.pptx:
            report["pptx"] = step_pptx()

        report["ok"] = True
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        out_path = ROOT / "logs" / f"regeneracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n[OK] Regeneração concluída. Relatório: {out_path}")
        print("[OK] Painel: http://localhost:8501  (reinicie o container app se necessário)")
        return 0
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["error"] = str(exc)
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        err_path = ROOT / "logs" / f"regeneracao_ERRO_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        err_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"[ERRO] {exc}", file=sys.stderr)
        print(f"[ERRO] Relatório: {err_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
