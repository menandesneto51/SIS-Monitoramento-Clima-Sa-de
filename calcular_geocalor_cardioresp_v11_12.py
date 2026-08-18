# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime
import math
import warnings

import numpy as np
import pandas as pd

DB = Path("data/output/sis_integrado.db")
COD_CUIABA = "5103403"
OUT_DIR = Path("data/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

INPUT_CANDIDATES = [
    "geocalor_model_input_diario",
    "v11_geocalor_input_diario",
    "painel_geocalor_diario",
    "v9_painel_clima_saude_diario",
]

OUTCOMES = {
    "internacoes_cardio": "Internações cardiovasculares",
    "internacoes_resp": "Internações respiratórias",
    "obitos_cardio": "Óbitos cardiovasculares",
    "obitos_resp": "Óbitos respiratórios",
}

def table_exists(con, name: str) -> bool:
    q = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", con, params=(name,))
    return not q.empty

def read_first_input(con):
    for t in INPUT_CANDIDATES:
        if table_exists(con, t):
            df = pd.read_sql(f"SELECT * FROM {t}", con)
            if not df.empty:
                return t, df
    return None, pd.DataFrame()

def norm_cod(s):
    return s.astype(str).str.replace(r"\.0$", "", regex=True)

def crude_rr_lag(df_mun: pd.DataFrame, outcome: str, lag: int) -> dict:
    d = df_mun.sort_values("data").copy()
    d[f"isHW_lag{lag}"] = d["isHW"].shift(lag).fillna(0).astype(int)

    exp = d[d[f"isHW_lag{lag}"] == 1]
    unexp = d[d[f"isHW_lag{lag}"] == 0]

    a = float(exp[outcome].sum()) if not exp.empty else 0.0
    b = float(unexp[outcome].sum()) if not unexp.empty else 0.0
    n1 = max(len(exp), 1)
    n0 = max(len(unexp), 1)

    rate1 = (a + 0.5) / n1
    rate0 = (b + 0.5) / n0
    rr = rate1 / rate0 if rate0 > 0 else np.nan

    se = math.sqrt((1.0 / (a + 0.5)) + (1.0 / (b + 0.5)))
    lcl = math.exp(math.log(rr) - 1.96 * se) if rr and rr > 0 else np.nan
    ucl = math.exp(math.log(rr) + 1.96 * se) if rr and rr > 0 else np.nan

    return {
        "lag": lag,
        "dias_expostos_lag": n1,
        "dias_nao_expostos": n0,
        "eventos_expostos": a,
        "eventos_nao_expostos": b,
        "rr": rr,
        "rr_ic95_inf": lcl,
        "rr_ic95_sup": ucl,
    }

def fit_nb_distributed_lag(df_mun: pd.DataFrame, outcome: str) -> pd.DataFrame | None:
    try:
        import statsmodels.api as sm
    except Exception:
        return None

    d = df_mun.sort_values("data").copy()
    for lag in range(8):
        d[f"isHW_lag{lag}"] = d["isHW"].shift(lag).fillna(0).astype(int)

    d["trend"] = np.arange(len(d))
    d["month"] = pd.to_datetime(d["data"]).dt.month.astype("category")
    d["dow"] = pd.to_datetime(d["data"]).dt.dayofweek.astype("category")

    xcols = [f"isHW_lag{i}" for i in range(8)] + ["trend"]

    for c in ["umidade_med", "thermal_range", "UmidadeMed", "thermalRange"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(pd.to_numeric(d[c], errors="coerce").median())
            xcols.append(c)

    y = pd.to_numeric(d[outcome], errors="coerce").fillna(0)
    X = d[xcols].copy()
    X = pd.concat(
        [
            X,
            pd.get_dummies(d["month"], prefix="mes", drop_first=True),
            pd.get_dummies(d["dow"], prefix="dow", drop_first=True),
        ],
        axis=1,
    )
    X = sm.add_constant(X, has_constant="add")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = sm.GLM(y, X, family=sm.families.NegativeBinomial()).fit(maxiter=200, disp=0)
    except Exception:
        return None

    rows = []
    for lag in range(8):
        term = f"isHW_lag{lag}"
        if term not in model.params.index:
            continue
        beta = float(model.params[term])
        se = float(model.bse[term])
        rr = math.exp(beta)
        rows.append(
            {
                "lag": lag,
                "rr": rr,
                "rr_ic95_inf": math.exp(beta - 1.96 * se),
                "rr_ic95_sup": math.exp(beta + 1.96 * se),
                "metodo": "NB_lag_distribuido_aproximado",
                "p_valor": float(model.pvalues[term]),
            }
        )
    return pd.DataFrame(rows)

def compute_rr(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["cod_ibge"] = norm_cod(df["cod_ibge"])
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])
    df["isHW"] = pd.to_numeric(df["isHW"], errors="coerce").fillna(0).astype(int)

    available_outcomes = [o for o in OUTCOMES if o in df.columns]
    if not available_outcomes:
        return pd.DataFrame(), pd.DataFrame([{"status": "insuficiente", "detalhe": "Nenhum desfecho cardiorrespiratório encontrado."}])

    rows = []
    status_rows = []

    for cod, dm0 in df.groupby("cod_ibge"):
        dm = dm0.copy()
        municipio = dm["municipio"].dropna().astype(str).iloc[0] if "municipio" in dm.columns and dm["municipio"].notna().any() else ""
        regional = dm["regional_saude"].dropna().astype(str).iloc[0] if "regional_saude" in dm.columns and dm["regional_saude"].notna().any() else ""

        n_days = dm["data"].nunique()
        n_hw = int(dm["isHW"].sum())

        for outcome in available_outcomes:
            dm[outcome] = pd.to_numeric(dm[outcome], errors="coerce").fillna(0)

            if n_days < 365 or n_hw < 3:
                for lag in range(8):
                    rows.append({
                        "cod_ibge": cod,
                        "municipio": municipio,
                        "regional_saude": regional,
                        "desfecho": outcome,
                        "desfecho_label": OUTCOMES[outcome],
                        "lag": lag,
                        "rr": np.nan,
                        "rr_ic95_inf": np.nan,
                        "rr_ic95_sup": np.nan,
                        "metodo": "insuficiente",
                        "status_modelagem": "insuficiente_serie_diaria",
                        "detalhe": f"{n_days} dias e {n_hw} dias de OC; mínimo operacional sugerido: >=365 dias e >=3 dias OC.",
                    })
                continue

            nb = fit_nb_distributed_lag(dm, outcome)
            if nb is not None and not nb.empty:
                for _, rrrow in nb.iterrows():
                    rows.append({
                        "cod_ibge": cod,
                        "municipio": municipio,
                        "regional_saude": regional,
                        "desfecho": outcome,
                        "desfecho_label": OUTCOMES[outcome],
                        "lag": int(rrrow["lag"]),
                        "rr": rrrow["rr"],
                        "rr_ic95_inf": rrrow["rr_ic95_inf"],
                        "rr_ic95_sup": rrrow["rr_ic95_sup"],
                        "metodo": rrrow["metodo"],
                        "p_valor": rrrow.get("p_valor", np.nan),
                        "status_modelagem": "ok",
                        "detalhe": "Modelo binomial negativo com lags 0-7 e controles disponíveis.",
                    })
            else:
                for lag in range(8):
                    rr = crude_rr_lag(dm, outcome, lag)
                    rows.append({
                        "cod_ibge": cod,
                        "municipio": municipio,
                        "regional_saude": regional,
                        "desfecho": outcome,
                        "desfecho_label": OUTCOMES[outcome],
                        **rr,
                        "metodo": "rr_operacional_crude_lag",
                        "p_valor": np.nan,
                        "status_modelagem": "ok_aproximado",
                        "detalhe": "RR operacional por lag. Não substitui DLNM completo.",
                    })

        status_rows.append({
            "cod_ibge": cod,
            "municipio": municipio,
            "regional_saude": regional,
            "dias_serie": n_days,
            "dias_onda_calor": n_hw,
            "desfechos_disponiveis": ", ".join(available_outcomes),
        })

    return pd.DataFrame(rows), pd.DataFrame(status_rows)

def create_insufficient_from_resumo(con, motivo: str):
    resumo = pd.read_sql("SELECT * FROM resumo_municipal_atual", con) if table_exists(con, "resumo_municipal_atual") else pd.DataFrame()
    rows = []
    if resumo.empty:
        resumo = pd.DataFrame([{"cod_ibge": COD_CUIABA, "municipio": "Cuiabá", "regional_saude": "ERS Cuiabá"}])

    for _, r in resumo.iterrows():
        cod = str(r.get("cod_ibge", "")).replace(".0", "")
        mun = r.get("municipio", "")
        reg = r.get("regional_saude", "")
        for outcome, label in OUTCOMES.items():
            for lag in range(8):
                rows.append({
                    "cod_ibge": cod,
                    "municipio": mun,
                    "regional_saude": reg,
                    "desfecho": outcome,
                    "desfecho_label": label,
                    "lag": lag,
                    "rr": np.nan,
                    "rr_ic95_inf": np.nan,
                    "rr_ic95_sup": np.nan,
                    "metodo": "DLNM_NB_requer_serie_diaria",
                    "status_modelagem": "insuficiente_dados_diarios",
                    "detalhe": motivo,
                })
    return pd.DataFrame(rows)

def main():
    print("=" * 70)
    print("V11.12 - GEOCALOR CARDIORRESPIRATORIO")
    print("=" * 70)

    if not DB.exists():
        raise SystemExit(f"ERRO: banco não encontrado: {DB}")

    con = sqlite3.connect(DB)

    input_name, df_in = read_first_input(con)

    if df_in.empty:
        motivo = (
            "Não foi encontrada tabela diária com exposição isHW e desfechos cardiorrespiratórios. "
            "Para RR GeoCalor/DLNM, criar geocalor_model_input_diario com cod_ibge, data, isHW, "
            "internacoes_cardio, internacoes_resp, obitos_cardio e obitos_resp."
        )
        rr = create_insufficient_from_resumo(con, motivo)
        status = pd.DataFrame([{
            "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fonte": "indisponivel",
            "status": "insuficiente_dados_diarios",
            "detalhe": motivo,
        }])
    else:
        required = {"cod_ibge", "data", "isHW"}
        missing = sorted(required - set(df_in.columns))
        if missing:
            motivo = f"Tabela {input_name} existe, mas faltam colunas obrigatórias: {missing}"
            rr = create_insufficient_from_resumo(con, motivo)
            status = pd.DataFrame([{
                "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fonte": input_name,
                "status": "estrutura_incompleta",
                "detalhe": motivo,
            }])
        else:
            rr, status_mun = compute_rr(df_in)
            status = pd.DataFrame([{
                "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fonte": input_name,
                "status": "processado" if not rr.empty else "sem_resultado",
                "detalhe": f"Linhas de entrada: {len(df_in)}; municípios: {df_in['cod_ibge'].astype(str).nunique()}",
            }])
            if not status_mun.empty:
                status_mun.to_sql("geocalor_status_municipios_v11_12", con, if_exists="replace", index=False)

    rr.to_sql("geocalor_cardioresp_rr_municipal_v11_12", con, if_exists="replace", index=False)
    status.to_sql("geocalor_status_modelagem_v11_12", con, if_exists="replace", index=False)

    cuiaba = rr[rr["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).eq(COD_CUIABA)].copy()
    if cuiaba.empty and "municipio" in rr.columns:
        cuiaba = rr[rr["municipio"].astype(str).str.contains("Cuiab", case=False, na=False)].copy()
    cuiaba.to_sql("geocalor_cuiaba_cardioresp_v11_12", con, if_exists="replace", index=False)

    rr.to_csv(OUT_DIR / "geocalor_cardioresp_rr_municipal_v11_12.csv", index=False, encoding="utf-8-sig")
    cuiaba.to_csv(OUT_DIR / "geocalor_cuiaba_cardioresp_v11_12.csv", index=False, encoding="utf-8-sig")
    status.to_csv(OUT_DIR / "geocalor_status_modelagem_v11_12.csv", index=False, encoding="utf-8-sig")

    print("Tabela: geocalor_cardioresp_rr_municipal_v11_12")
    print(f"Linhas: {len(rr)}")
    print("Tabela: geocalor_cuiaba_cardioresp_v11_12")
    print(f"Linhas Cuiabá: {len(cuiaba)}")
    print("Status:")
    print(status.to_string(index=False))

    if not cuiaba.empty:
        cols = [c for c in ["municipio", "desfecho_label", "lag", "rr", "rr_ic95_inf", "rr_ic95_sup", "metodo", "status_modelagem", "detalhe"] if c in cuiaba.columns]
        print("Cuiabá:")
        print(cuiaba[cols].head(32).to_string(index=False))

    con.close()
    print("OK: módulo GeoCalor cardiorrespiratório concluído.")

if __name__ == "__main__":
    main()
