# -*- coding: utf-8 -*-
"""Gera cotas de referência PROVISÓRIAS a partir da telemetria ANA (percentis).

NÃO substitui régua oficial ANA/Defesa Civil. Marca observacao=PROVISORIO_PERCENTIL.
Uso:
  .\\.venv\\Scripts\\python.exe scripts\\gerar_cotas_provisorias_ana.py
  .\\.venv\\Scripts\\python.exe scripts\\gerar_cotas_provisorias_ana.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

OUT = ROOT / "config" / "ana_cotas_referencia_mt.csv"


def _plausible(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["cota_cm"] = pd.to_numeric(out.get("cota_cm"), errors="coerce")
    out = out.dropna(subset=["cota_cm", "codigo_estacao"])
    out = out[(out["cota_cm"] >= 0) & (out["cota_cm"] < 5000)]
    if "nome_estacao" in out.columns:
        n = out["nome_estacao"].astype(str).str.upper()
        out = out[~n.str.contains("BARRAMENTO", na=False)]
    return out


def build_from_telemetria(tel: pd.DataFrame, est: pd.DataFrame | None = None) -> pd.DataFrame:
    work = _plausible(tel)
    if work.empty:
        return pd.DataFrame()
    rows = []
    for cod, g in work.groupby(work["codigo_estacao"].astype(str)):
        vals = g["cota_cm"]
        if len(vals) < 20:
            continue
        p10 = float(vals.quantile(0.10))
        p75 = float(vals.quantile(0.75))
        p90 = float(vals.quantile(0.90))
        # seca ≈ P10; alerta ≈ P75; emergência ≈ P90 (provisório operacional)
        nome = ""
        mun = ""
        if est is not None and not est.empty:
            m = est[est["codigo_estacao"].astype(str).eq(cod)]
            if not m.empty:
                nome = str(m.iloc[0].get("nome_estacao") or "")
                mun = str(m.iloc[0].get("municipio") or "")
        if not nome and "nome_estacao" in g.columns:
            nome = str(g["nome_estacao"].dropna().astype(str).iloc[0]) if g["nome_estacao"].notna().any() else ""
        if not mun and "municipio" in g.columns:
            mun = str(g["municipio"].dropna().astype(str).iloc[0]) if g["municipio"].notna().any() else ""
        rows.append(
            {
                "codigo_estacao": cod,
                "nome_estacao": nome,
                "municipio": mun,
                "cota_seca_cm": round(p10, 1),
                "cota_alerta_cm": round(p75, 1),
                "cota_emergencia_cm": round(p90, 1),
                "observacao": "PROVISORIO_PERCENTIL — substituir por régua oficial ANA/Defesa Civil",
            }
        )
    return pd.DataFrame(rows).sort_values(["municipio", "codigo_estacao"]).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Sobrescreve config/ana_cotas_referencia_mt.csv")
    args = ap.parse_args(argv)

    from sisclima.core.db import read_table, reset_engine

    reset_engine()
    tel = read_table("ana_telemetria")
    est = read_table("ana_estacoes")
    if tel is None or tel.empty:
        # fallback seed
        import sqlite3

        seed = ROOT / "data" / "cloud" / "sis_cloud_seed.db"
        con = sqlite3.connect(seed)
        tel = pd.read_sql("SELECT * FROM ana_telemetria", con)
        try:
            est = pd.read_sql("SELECT * FROM ana_estacoes", con)
        except Exception:
            est = pd.DataFrame()
        con.close()

    out = build_from_telemetria(tel, est)
    if out.empty:
        print("[ERRO] sem séries plausíveis para gerar cotas")
        return 1
    preview = ROOT / "config" / "ana_cotas_referencia_mt.provisorio.csv"
    out.to_csv(preview, index=False, encoding="utf-8")
    print(f"preview {preview} · {len(out)} estações")
    print(out.head(8).to_string(index=False))
    if args.apply:
        # preserva header + comentário de aviso
        header = (
            "# Cotas PROVISÓRIAS por percentil da série ANA (seca=P10, alerta=P75, emergência=P90).\n"
            "# Substituir por valores oficiais assim que disponíveis. Linhas com # são ignoradas pelo motor.\n"
        )
        with OUT.open("w", encoding="utf-8", newline="") as f:
            f.write(header)
            out.to_csv(f, index=False)
        print(f"[OK] aplicado em {OUT}")
    else:
        print("[INFO] rode com --apply para gravar em config/ana_cotas_referencia_mt.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
