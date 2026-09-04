"""Exporta tabela municipal ampliada e resumo JSON para o levantamento STAR Ondas de Calor."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from sisclima.core.db import read_table

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "output" / "star"
RODADA = ROOT / "data" / "output" / "boletim" / "rodada_semanal_SE_35-2026.csv"


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)


def _slug(name: object) -> str:
    text = str(name).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "grupo"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rod = pd.read_csv(RODADA)
    r = read_table("resumo_municipal_atual")
    r["cod_ibge"] = _ibge7(r["cod_ibge"])
    rod["cod_ibge"] = _ibge7(rod["cod_ibge"])

    extra_cols = [
        "tmax",
        "tmin",
        "utci_proxy",
        "umidade_media",
        "risco_cumulativo_3d",
        "duracao_onda_calor_dias",
        "onda_calor_p95_2d",
        "evento_onda_calor_id",
        "intensidade_onda_calor",
        "severidade_onda_calor",
        "ehf_adaptado",
        "pm25_ugm3",
        "focos_queimadas_7d",
        "focos_queimadas_24h",
        "nivel",
        "pred_nivel_clima_7d",
        "ocupacao_leitos_pct",
        "fonte_ocupacao",
        "pressao_calor_pct",
        "fonte_pressao",
        "indice_pressao_saude",
        "semaforo_pressao",
        "populacao",
        "idosos_pct",
        "criancas_0_4_pct",
        "rural_pct",
        "densidade",
        "indice_vulnerabilidade_calor",
        "populacao_vulneravel_estimada",
        "n_territorios_tradicionais",
        "risco_adaptasus_dominante_nome",
        "nivel_prontidao",
    ]
    extra_cols = [c for c in extra_cols if c in r.columns]
    base = r[["cod_ibge"] + extra_cols].copy()
    m = rod.merge(base, on="cod_ibge", how="left", suffixes=("", "_res"))

    for c in ["tmax", "pm25_ugm3", "umidade_media"]:
        res_col = f"{c}_res"
        if c in m.columns and res_col in m.columns:
            m[c] = m[c].fillna(m[res_col])

    umid = m["umidade_media"] if "umidade_media" in m.columns else m.get("ur_pct")
    m["tmax_ge_37"] = (pd.to_numeric(m["tmax"], errors="coerce") >= 37).astype("Int64")
    m["pm25_ge_25"] = (pd.to_numeric(m["pm25_ugm3"], errors="coerce") >= 25).astype("Int64")
    m["ur_le_30"] = (pd.to_numeric(umid, errors="coerce") <= 30).astype("Int64")
    m["onda_calor_flag"] = (
        pd.to_numeric(m.get("onda_calor_p95_2d"), errors="coerce").fillna(0).astype(int)
    )

    sc = read_table("saude_calor_municipio")
    if sc is not None and not sc.empty:
        sc = sc.copy()
        sc["cod_ibge"] = _ibge7(sc["cod_ibge"])
        piv = (
            sc.pivot_table(
                index="cod_ibge",
                columns="grupo_agravo_calor",
                values="eventos",
                aggfunc="sum",
            )
            .reset_index()
        )
        piv.columns = ["cod_ibge"] + [f"saude_calor_{_slug(c)}" for c in piv.columns[1:]]
        m = m.merge(piv, on="cod_ibge", how="left")

    sim = read_table("epi_sim_obitos_calor")
    if sim is not None and not sim.empty:
        sim = sim.copy()
        sim["cod_ibge"] = _ibge7(sim["cod_ibge"])
        sim["data"] = pd.to_datetime(sim["data"], errors="coerce")
        g = sim.groupby("cod_ibge", as_index=False).agg(
            obitos_total_sim=("obitos_total", "sum"),
            obitos_calor_suspeitos_sim=("obitos_calor_suspeitos", "sum"),
        )
        m = m.merge(g, on="cod_ibge", how="left")

    front = [
        "semana_epidemiologica",
        "data_referencia",
        "cod_ibge",
        "municipio",
        "regional_saude",
        "classe_atual",
        "classe_projetada_7d",
        "nivel",
        "pred_nivel_clima_7d",
        "tmax",
        "tmin",
        "utci_proxy",
        "umidade_media",
        "risco_cumulativo_3d",
        "onda_calor_flag",
        "duracao_onda_calor_dias",
        "onda_calor_p95_2d",
        "intensidade_onda_calor",
        "severidade_onda_calor",
        "ehf_adaptado",
        "pm25_ugm3",
        "focos_queimadas_7d",
        "tmax_ge_37",
        "pm25_ge_25",
        "ur_le_30",
        "ocupacao_leitos_pct",
        "fonte_ocupacao",
        "pressao_calor_pct",
        "semaforo_pressao",
        "indice_pressao_saude",
        "populacao",
        "idosos_pct",
        "criancas_0_4_pct",
        "rural_pct",
        "densidade",
        "indice_vulnerabilidade_calor",
        "populacao_vulneravel_estimada",
        "n_territorios_tradicionais",
        "risco_adaptasus_dominante_nome",
        "nivel_prontidao",
        "indice_prioridade",
        "faixa_prioridade",
        "determinante_principal",
    ]
    front = [c for c in front if c in m.columns]
    rest = [c for c in m.columns if c not in front and not str(c).endswith("_res")]
    out = m[front + rest].sort_values(["regional_saude", "municipio"]).reset_index(drop=True)
    csv_path = OUT_DIR / "STAR_ondas_calor_municipal_SE35_2026.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    resumo: dict = {
        "n_mun": int(len(out)),
        "vr_atual": int(out["classe_atual"].isin(["vermelha", "roxa"]).sum()),
        "vr_proj": int(out["classe_projetada_7d"].isin(["vermelha", "roxa"]).sum()),
        "dist_atual": out["classe_atual"].value_counts().to_dict(),
        "tmax_max": float(pd.to_numeric(out["tmax"], errors="coerce").max()),
        "n_tmax_ge37": int(out["tmax_ge_37"].fillna(0).sum()),
        "n_pm25_ge25": int(out["pm25_ge_25"].fillna(0).sum()),
        "n_onda_flag": int(out["onda_calor_flag"].sum()),
        "n_com_ocupacao": int(pd.to_numeric(out["ocupacao_leitos_pct"], errors="coerce").notna().sum()),
        "top_tmax": out.nlargest(10, "tmax")[
            ["municipio", "regional_saude", "tmax", "classe_atual", "pm25_ugm3"]
        ].to_dict("records"),
        "top_prioridade": out.nlargest(10, "indice_prioridade")[
            ["municipio", "regional_saude", "indice_prioridade", "classe_atual", "tmax"]
        ].to_dict("records"),
        "top_pm25": out.nlargest(10, "pm25_ugm3")[
            ["municipio", "regional_saude", "pm25_ugm3", "classe_atual", "tmax"]
        ].to_dict("records"),
        "top_vuln": out.nlargest(10, "indice_vulnerabilidade_calor")[
            [
                "municipio",
                "regional_saude",
                "indice_vulnerabilidade_calor",
                "idosos_pct",
                "classe_atual",
            ]
        ].to_dict("records"),
    }

    se = read_table("saude_calor_serie_estado")
    if se is not None and not se.empty:
        resumo["saude_calor_grupos"] = (
            se.groupby("grupo_agravo_calor")["eventos"].sum().sort_values(ascending=False).head(20).to_dict()
        )
        meses = sorted(se["mes"].astype(str).unique().tolist())
        resumo["saude_calor_meses"] = {"primeiro": meses[:3], "ultimo": meses[-3:]}

    if sim is not None and not sim.empty:
        resumo["sim_obitos_total"] = int(pd.to_numeric(sim["obitos_total"], errors="coerce").fillna(0).sum())
        resumo["sim_obitos_calor_susp"] = int(
            pd.to_numeric(sim["obitos_calor_suspeitos"], errors="coerce").fillna(0).sum()
        )
        resumo["sim_periodo"] = [str(sim["data"].min())[:10], str(sim["data"].max())[:10]]

    he = read_table("hospital_ocupacao_estado")
    if he is not None and not he.empty:
        row = he.iloc[0]
        resumo["ocup_estado"] = {
            "ocupacao_pct": float(row["ocupacao_pct"]),
            "leitos_existentes": int(row["leitos_existentes"]),
            "leitos_ocupados": int(row["leitos_ocupados"]),
            "municipios_com_ocupacao": int(row["municipios_com_ocupacao"]),
            "fonte": str(row["fonte"]),
        }

    hc = read_table("hist_clima_municipal_diario")
    if hc is not None and not hc.empty:
        d = pd.to_datetime(hc["data"], errors="coerce")
        resumo["hist_clima_n"] = int(len(hc))
        resumo["hist_clima_periodo"] = [str(d.min())[:10], str(d.max())[:10]]

    ia = read_table("inmet_alertas")
    if ia is not None and not ia.empty:
        resumo["inmet_n"] = int(len(ia))
        resumo["inmet_eventos"] = ia["evento"].value_counts().head(8).to_dict()

    met = read_table("met_biometeo")
    if met is not None and not met.empty:
        met = met.copy()
        met["data"] = met["data"].astype(str).str[:10]
        met["precip"] = pd.to_numeric(met.get("precipitacao_mm"), errors="coerce")
        met["tmax_m"] = pd.to_numeric(met["tmax"], errors="coerce")
        chuva = []
        for day in ["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]:
            day_df = met[met["data"] == day].groupby("cod_ibge", as_index=False).tail(1)
            chuva.append(
                {
                    "data": day,
                    "n": int(len(day_df)),
                    "chuva_ge1": int((day_df["precip"].fillna(0) >= 1).sum()),
                    "chuva_ge5": int((day_df["precip"].fillna(0) >= 5).sum()),
                    "tmax_med": float(day_df["tmax_m"].mean()) if len(day_df) else None,
                    "n_tmax_ge37": int((day_df["tmax_m"] >= 37).sum()) if len(day_df) else 0,
                }
            )
        resumo["chuva_recente"] = chuva
        cui = met[met["cod_ibge"].astype(str).str.startswith("5103403")].sort_values("data")
        cols_c = [c for c in ["data", "tmax", "umidade_media", "precipitacao_mm"] if c in cui.columns]
        resumo["cuiaba"] = cui[cols_c].drop_duplicates("data").tail(8).to_dict("records")

    (OUT_DIR / "STAR_resumo_indicadores.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"CSV={csv_path}")
    print(f"JSON={OUT_DIR / 'STAR_resumo_indicadores.json'}")
    print(
        json.dumps(
            {
                k: resumo[k]
                for k in [
                    "n_mun",
                    "vr_atual",
                    "vr_proj",
                    "dist_atual",
                    "tmax_max",
                    "n_tmax_ge37",
                    "n_pm25_ge25",
                    "n_onda_flag",
                    "sim_obitos_total",
                    "sim_obitos_calor_susp",
                    "hist_clima_periodo",
                    "ocup_estado",
                ]
                if k in resumo
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
