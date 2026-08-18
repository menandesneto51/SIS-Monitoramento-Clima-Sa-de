# -*- coding: utf-8 -*-
"""
V11.9 - Corrige tabela de predição 7 dias.

Cria/atualiza na tabela predicao_calor_7d_municipal_v6:
- risco_preditivo_score, se ausente
- nivel_predicao_7d

Regra operacional:
- roxa: risco3d >=18 OU tmax >=42 OU utci >=40
- vermelha: risco3d >=12 OU tmax >=40 OU utci >=38
- laranja: risco3d >=7 OU tmax >=38 OU utci >=32 OU onda P95 prevista
- amarela: risco3d >=3 OU tmax >=35 OU utci >=26
- verde: abaixo disso
"""

import sqlite3
from pathlib import Path
import pandas as pd
import numpy as np

DB = Path("data/output/sis_integrado.db")
T = "predicao_calor_7d_municipal_v6"

def table_exists(con, name):
    q = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", con, params=(name,))
    return not q.empty

def pick_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

def boolish(x):
    if pd.isna(x):
        return False
    if isinstance(x, (int, float)):
        return x > 0
    s = str(x).strip().lower()
    return s in {"1", "true", "sim", "yes", "y", "verdadeiro", "prevista", "detectada"}

def classificar(row):
    tmax = row.get("tmax_max_7d", np.nan)
    utci = row.get("utci_proxy_max_7d", np.nan)
    risco = row.get("risco_cumulativo_3d_max_7d", np.nan)
    onda = boolish(row.get("onda_calor_p95_2d_prevista", False))

    vals = []
    try: vals.append(float(risco))
    except Exception: pass

    score = 0
    if pd.notna(risco):
        if risco >= 18: score = max(score, 4)
        elif risco >= 12: score = max(score, 3)
        elif risco >= 7: score = max(score, 2)
        elif risco >= 3: score = max(score, 1)

    if pd.notna(tmax):
        if tmax >= 42: score = max(score, 4)
        elif tmax >= 40: score = max(score, 3)
        elif tmax >= 38: score = max(score, 2)
        elif tmax >= 35: score = max(score, 1)

    if pd.notna(utci):
        if utci >= 40: score = max(score, 4)
        elif utci >= 38: score = max(score, 3)
        elif utci >= 32: score = max(score, 2)
        elif utci >= 26: score = max(score, 1)

    if onda:
        score = max(score, 2)

    nivel = {0:"verde", 1:"amarela", 2:"laranja", 3:"vermelha", 4:"roxa"}[score]
    return pd.Series({"risco_preditivo_score": score, "nivel_predicao_7d": nivel})

def main():
    print("============================================================")
    print("V11.9 - CORRIGIR PREDICAO 7 DIAS")
    print("============================================================")

    if not DB.exists():
        raise SystemExit(f"ERRO: banco não encontrado: {DB}")

    con = sqlite3.connect(DB)

    if not table_exists(con, T):
        raise SystemExit(f"ERRO: tabela não encontrada: {T}")

    df = pd.read_sql(f"SELECT * FROM {T}", con)
    print(f"Linhas carregadas: {len(df)}")
    print(f"Colunas antes: {list(df.columns)}")

    required = ["tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d"]
    for c in required:
        if c not in df.columns:
            print(f"AVISO: coluna ausente: {c}")

    calc = df.apply(classificar, axis=1)
    df["risco_preditivo_score"] = calc["risco_preditivo_score"].astype(int)
    df["nivel_predicao_7d"] = calc["nivel_predicao_7d"].astype(str)

    df.to_sql(T, con, if_exists="replace", index=False)

    # Atualiza alerta inteligente se existir, apenas quando a coluna não existir lá.
    if table_exists(con, "alerta_inteligente_municipal_v6"):
        ai = pd.read_sql("SELECT * FROM alerta_inteligente_municipal_v6", con)
        key = "cod_ibge" if "cod_ibge" in ai.columns and "cod_ibge" in df.columns else None
        if key:
            pred = df[[key, "nivel_predicao_7d", "risco_preditivo_score"]].copy()
            ai = ai.drop(columns=[c for c in ["nivel_predicao_7d", "risco_preditivo_score"] if c in ai.columns], errors="ignore")
            ai = ai.merge(pred, on=key, how="left")
            ai["nivel_predicao_7d"] = ai["nivel_predicao_7d"].fillna("cinza")
            ai["risco_preditivo_score"] = ai["risco_preditivo_score"].fillna(0).astype(int)
            ai.to_sql("alerta_inteligente_municipal_v6", con, if_exists="replace", index=False)
            print("OK: alerta_inteligente_municipal_v6 atualizado com predição 7d.")

    dist = df["nivel_predicao_7d"].value_counts().to_dict()
    print(f"Distribuição nivel_predicao_7d: {dist}")
    print("Top 20 predição:")
    cols = [c for c in ["cod_ibge", "municipio", "regional_saude", "nivel_predicao_7d", "risco_preditivo_score", "tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d"] if c in df.columns]
    print(df.sort_values(["risco_preditivo_score", "risco_cumulativo_3d_max_7d"], ascending=[False, False])[cols].head(20).to_string(index=False))

    con.close()
    print("OK: predição 7 dias corrigida.")

if __name__ == "__main__":
    main()
