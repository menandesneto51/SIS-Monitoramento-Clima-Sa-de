# -*- coding: utf-8 -*-
"""Homologação rápida de municípios críticos (sala de situação).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\homologar_municipios_criticos.py
  .\\.venv\\Scripts\\python.exe scripts\\homologar_municipios_criticos.py --json logs/homolog_mun.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

# Prioridade CIEVS: capital + polo + bacias hidro (Guaporé/Juruena/Aripuanã)
CRITICOS = [
    ("5103403", "CUIABÁ"),
    ("5108405", "VÁRZEA GRANDE"),
    ("5107602", "RONDONÓPOLIS"),
    ("5107909", "SINOP"),
    ("5100250", "ALTA FLORESTA"),
    ("5107928", "SORRISO"),
    ("5105251", "LUCAS DO RIO VERDE"),
    ("5106752", "PONTES E LACERDA"),
    ("5105507", "VILA BELA DA SANTÍSSIMA TRINDADE"),
    ("5101407", "ARIPUANÃ"),
    ("5102686", "CAMPOS DE JÚLIO"),
    ("5107875", "SAPEZAL"),
]


def _pick(resumo: pd.DataFrame) -> pd.DataFrame:
    codes = []
    seen = set()
    for cod, _nome in CRITICOS:
        if cod in seen:
            continue
        seen.add(cod)
        codes.append(cod)
    r = resumo.copy()
    r["cod_ibge"] = r["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True)
    out = r[r["cod_ibge"].isin(codes)].copy()
    # completar com top roxa/vermelha se faltar
    if "nivel" in r.columns and len(out) < 8:
        ordem = {"roxa": 5, "vermelha": 4, "laranja": 3, "amarela": 2, "verde": 1}
        extra = r.copy()
        extra["_o"] = extra["nivel"].astype(str).str.lower().map(ordem).fillna(0)
        extra = extra.sort_values("_o", ascending=False)
        for _, row in extra.iterrows():
            if str(row["cod_ibge"]) in set(out["cod_ibge"].astype(str)):
                continue
            out = pd.concat([out, row.to_frame().T], ignore_index=True)
            if len(out) >= 10:
                break
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)

    from sisclima.core.db import backend_name, read_table, reset_engine

    reset_engine()
    resumo = read_table("resumo_municipal_atual")
    hidro = read_table("hidro_risco_municipal")
    if resumo is None or resumo.empty:
        print("[ERRO] resumo_municipal_atual vazio")
        return 1

    sample = _pick(resumo)
    cols = [
        c
        for c in [
            "cod_ibge",
            "municipio",
            "nivel",
            "score",
            "indice_pressao_saude",
            "semaforo_pressao",
            "ocupacao_leitos_pct",
            "situacao_hidro",
            "nivel_alerta_hidro",
            "cota_cm",
            "motivos",
        ]
        if c in sample.columns
    ]
    view = sample[cols].copy()

    # sempre completa hidro a partir da tabela dedicada (resumo pode não ter merge)
    if hidro is not None and not hidro.empty:
        h = hidro.copy()
        h["cod_ibge"] = h["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True)
        keep = [c for c in ["cod_ibge", "situacao_hidro", "cota_cm", "nivel_alerta_hidro"] if c in h.columns]
        h = h[keep].drop_duplicates("cod_ibge")
        view = view.drop(columns=[c for c in ("situacao_hidro", "cota_cm", "nivel_alerta_hidro") if c in view.columns], errors="ignore")
        view = view.merge(h, on="cod_ibge", how="left")

    print(f"backend={backend_name()} · municipios={len(view)}")
    print(view.to_string(index=False))

    checks = {
        "n": len(view),
        "com_nivel": int(view["nivel"].notna().sum()) if "nivel" in view.columns else 0,
        "com_pressao": int(pd.to_numeric(view.get("indice_pressao_saude"), errors="coerce").notna().sum())
        if "indice_pressao_saude" in view.columns
        else 0,
        "com_ocupacao": int(pd.to_numeric(view.get("ocupacao_leitos_pct"), errors="coerce").notna().sum())
        if "ocupacao_leitos_pct" in view.columns
        else 0,
        "pressao_flat20": False,
    }
    if "indice_pressao_saude" in view.columns:
        s = pd.to_numeric(view["indice_pressao_saude"], errors="coerce")
        checks["pressao_flat20"] = bool(s.nunique(dropna=True) <= 1 and abs(float(s.mean() or 0) - 20) < 0.5)

    ok = checks["n"] >= 5 and checks["com_nivel"] >= 5 and not checks["pressao_flat20"]
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "backend": backend_name(),
        "checks": checks,
        "ok": ok,
        "rows": view.fillna("").to_dict(orient="records"),
    }
    out = Path(args.json) if args.json else ROOT / "logs" / f"homolog_mun_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n[{'OK' if ok else 'PEND'}] {out}")
    # checklist texto para impressão
    txt = ROOT / "exports" / "envio_STI_CIEVS_2026-08-07" / "05_HOMOLOG_MUNICIPIOS_CRITICOS.txt"
    if txt.parent.exists():
        lines = [
            "Homologação municípios críticos — preencher OK/NOK na sala de situação",
            f"Gerado: {report['generated_at']} · backend={report['backend']}",
            "",
        ]
        for row in report["rows"]:
            mun = row.get("municipio") or row.get("cod_ibge")
            lines.append(
                f"[ ] {mun} | nivel={row.get('nivel')} | pressao={row.get('indice_pressao_saude')} | "
                f"ocup={row.get('ocupacao_leitos_pct')} | hidro={row.get('situacao_hidro')} | cota={row.get('cota_cm')}"
            )
        lines.append("")
        lines.append("Assinatura CIEVS: ______________________ Data: ____/____/________")
        txt.write_text("\n".join(lines), encoding="utf-8")
        print(f"[TXT] {txt}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
