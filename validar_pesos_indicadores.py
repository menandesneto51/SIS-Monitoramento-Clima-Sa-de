# -*- coding: utf-8 -*-
"""Valida distribuição de pesos dos indicadores compostos do painel."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sisclima.core.db import read_table
from sisclima.engines.panel_indicators import enrich_panel_indicators, get_indicator_config

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "apresentacoes" / "assets" / "weight_validation.json"

LEVEL = {"cinza": -1, "verde": 0, "amarela": 1, "laranja": 2, "vermelha": 3, "roxa": 4}


def num(s):
    return pd.to_numeric(s, errors="coerce")


def clip01(s):
    return num(s).clip(0, 1).fillna(0)


def spearman(a, b) -> float:
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def scale(parts, weights):
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    acc = np.zeros(len(parts[0]))
    for s, wi in zip(parts, w):
        acc = acc + np.asarray(s, float) * wi
    return pd.Series(np.clip(acc * 100, 0, 100), index=parts[0].index)


def main() -> int:
    resumo = read_table("resumo_municipal_atual")
    pred = read_table("predicao_calor_7d_municipal_v6")
    df = enrich_panel_indicators(resumo, pred)
    df["nivel_n"] = df["nivel"].astype(str).str.lower().map(LEVEL).fillna(0)

    risco = clip01(num(df["risco_cumulativo_3d"]) / 15.0)
    utci = clip01((num(df["utci_proxy"]) - 26) / 16.0)
    tmax = clip01((num(df["tmax"]) - 30) / 12.0)
    umid = clip01((55 - num(df["umidade_media"])) / 40.0)
    srag = clip01(num(df["incidencia_srag_100k"]) / 40.0)
    arbo = clip01(num(df["casos_arbovirus_7d"]) / 30.0)
    pm = clip01(num(df["pm25_ugm3"]) / 75.0)
    press = clip01(num(df["pressao_calor_pct"]) / 12.0)
    score = num(df["score"])
    nivel = df["nivel_n"]

    blocks = {
        "risco_cumulativo": risco,
        "utci": utci,
        "tmax": tmax,
        "umidade_seca": umid,
        "srag": srag,
        "arbovirus": arbo,
        "pm25": pm,
        "pressao": press,
    }

    corr_rows = []
    for k, s in blocks.items():
        r_n = spearman(s, nivel)
        r_s = spearman(s, score)
        corr_rows.append(
            {
                "bloco": k,
                "rho_nivel": round(r_n, 3),
                "rho_score": round(r_s, 3),
                "mean": round(float(s.mean()), 3),
                "std": round(float(s.std()), 3),
                "nonzero_pct": round(100 * float((s > 0).mean()), 1),
            }
        )

    def eval_scheme(name, tensao_w, carga_w, vig_w):
        tensao = scale([risco, utci, tmax, umid], tensao_w)
        carga = scale([srag, arbo, pm, press], carga_w)
        vig = scale([tensao / 100.0, carga / 100.0, press], vig_w)
        r_n = spearman(vig, nivel)
        r_s = spearman(vig, score)
        tmp = pd.DataFrame({"nivel": df["nivel"].astype(str).str.lower(), "vig": vig})
        high = tmp[tmp.nivel.isin(["vermelha", "roxa"])]["vig"].mean()
        low = tmp[tmp.nivel.isin(["verde", "amarela"])]["vig"].mean()
        sep = float(high - low)
        top_vig = set(vig.nlargest(20).index)
        top_score = set(score.nlargest(20).index)
        jacc = len(top_vig & top_score) / max(1, len(top_vig | top_score))
        order = ["verde", "amarela", "laranja", "vermelha", "roxa"]
        means = [tmp[tmp.nivel == o]["vig"].mean() for o in order]
        mono = sum(1 for i in range(len(means) - 1) if means[i + 1] >= means[i] - 0.5)
        tw = np.array(tensao_w, float)
        cw = np.array(carga_w, float)
        vw = np.array(vig_w, float)
        return {
            "esquema": name,
            "rho_nivel": round(r_n, 3),
            "rho_score": round(r_s, 3),
            "sep_criticos": round(sep, 1),
            "jaccard_top20": round(jacc, 3),
            "mono_steps": mono,
            "vig_media": round(float(vig.mean()), 1),
            "vig_p90": round(float(vig.quantile(0.9)), 1),
            "pct_mod_plus": round(100 * float((vig > 30).mean()), 1),
            "pct_alta_plus": round(100 * float((vig > 60).mean()), 1),
            "means_by_nivel": {
                o: (round(float(m), 1) if pd.notna(m) else None) for o, m in zip(order, means)
            },
            "tensao_w": [round(float(x), 3) for x in tw / tw.sum()],
            "carga_w": [round(float(x), 3) for x in cw / cw.sum()],
            "vig_w": [round(float(x), 3) for x in vw / vw.sum()],
        }

    rho = {r["bloco"]: max(abs(r["rho_nivel"]), 0.01) for r in corr_rows}
    c_keys = ["risco_cumulativo", "utci", "tmax", "umidade_seca"]
    c_raw = np.array([rho[k] for k in c_keys], float)
    c_w = c_raw**1.2
    c_w = c_w / c_w.sum()

    cov = {"srag": 1.0, "arbovirus": 34 / 142, "pm25": 12 / 142, "pressao": 1.0}
    s_keys = ["srag", "arbovirus", "pm25", "pressao"]
    s_raw = np.array([rho[k] * np.sqrt(cov[k]) for k in s_keys], float)
    s_raw = np.maximum(s_raw, 0.05)
    s_w = s_raw / s_raw.sum()

    t_strength = float(np.mean([rho[k] for k in c_keys]))
    s_strength = float(np.mean([rho[k] * cov[k] for k in s_keys]))
    v_raw = np.array([t_strength, max(s_strength, 0.15), rho["pressao"] * 0.5])
    v_w = v_raw / v_raw.sum()

    schemes = [
        eval_scheme("atual_settings", [0.40, 0.30, 0.20, 0.10], [0.35, 0.25, 0.20, 0.20], [0.45, 0.40, 0.15]),
        eval_scheme("data_driven_v1", c_w.tolist(), s_w.tolist(), v_w.tolist()),
        eval_scheme("cievs_seca_2026", [0.45, 0.25, 0.20, 0.10], [0.40, 0.20, 0.15, 0.25], [0.55, 0.30, 0.15]),
        eval_scheme("cobertura_robusta", [0.42, 0.28, 0.18, 0.12], [0.45, 0.15, 0.10, 0.30], [0.50, 0.35, 0.15]),
        eval_scheme("saude_first", [0.35, 0.30, 0.25, 0.10], [0.45, 0.25, 0.20, 0.10], [0.30, 0.55, 0.15]),
        eval_scheme("equal_weights", [0.25] * 4, [0.25] * 4, [1 / 3] * 3),
        eval_scheme(
            "recomendado_hibrido",
            [0.42, 0.26, 0.20, 0.12],
            [0.38, 0.18, 0.12, 0.32],
            [0.52, 0.33, 0.15],
        ),
    ]

    def composite(e):
        return (
            e["rho_nivel"] * 0.40
            + e["rho_score"] * 0.20
            + (e["sep_criticos"] / 50) * 0.20
            + e["jaccard_top20"] * 0.10
            + (e["mono_steps"] / 4) * 0.10
        )

    for e in schemes:
        e["composite"] = round(composite(e), 4)

    # Grid search
    grid = []
    for tr in [0.38, 0.42, 0.46, 0.50]:
        for tu in [0.22, 0.26, 0.30]:
            for tt in [0.16, 0.20, 0.24]:
                tu_rest = 1 - tr - tu - tt
                if tu_rest < 0.05 or tu_rest > 0.20:
                    continue
                for cs in [0.30, 0.38, 0.45]:
                    for cp in [0.25, 0.32, 0.38]:
                        ca = 0.18
                        cpm = 1 - cs - ca - cp
                        if cpm < 0.05 or cpm > 0.25:
                            continue
                        for vt in [0.45, 0.52, 0.58]:
                            vc = 0.33
                            vp = 1 - vt - vc
                            if vp < 0.08 or vp > 0.22:
                                continue
                            e = eval_scheme(
                                f"g_{tr}_{tu}_{tt}_{cs}_{cp}_{vt}",
                                [tr, tu, tt, tu_rest],
                                [cs, ca, cpm, cp],
                                [vt, vc, vp],
                            )
                            e["composite"] = round(composite(e), 4)
                            grid.append(e)

    grid_sorted = sorted(grid, key=lambda x: x["composite"], reverse=True)
    schemes_sorted = sorted(schemes, key=lambda x: x["composite"], reverse=True)
    best = schemes_sorted[0]
    grid_best = grid_sorted[0]

    # Prefer grid if meaningfully better, else hybrid/recommended among named
    chosen = grid_best if grid_best["composite"] >= best["composite"] - 0.002 else best

    print("=== Correlação dos blocos com nível operacional ===")
    for r in sorted(corr_rows, key=lambda x: abs(x["rho_nivel"]), reverse=True):
        print(
            f"{r['bloco']:16s} ρ(nível)={r['rho_nivel']:+.3f}  ρ(score)={r['rho_score']:+.3f}  "
            f"mean={r['mean']:.3f} nonzero={r['nonzero_pct']}%"
        )

    print("\n=== Ranking esquemas nomeados ===")
    for e in schemes_sorted:
        print(
            f"{e['esquema']:22s} composite={e['composite']:.4f}  ρnivel={e['rho_nivel']:+.3f}  "
            f"sep={e['sep_criticos']:.1f}  jacc20={e['jaccard_top20']:.3f}  "
            f"mod+={e['pct_mod_plus']}% alta+={e['pct_alta_plus']}%"
        )

    print("\n=== Melhor no grid ===")
    print(grid_best["esquema"], "composite", grid_best["composite"])
    print(" tensao", dict(zip(c_keys, grid_best["tensao_w"])))
    print(" carga ", dict(zip(s_keys, grid_best["carga_w"])))
    print(" vig   ", dict(zip(["tensao", "carga", "pressao"], grid_best["vig_w"])))
    print(" means ", grid_best["means_by_nivel"])

    out = {
        "n_municipios": int(df["cod_ibge"].nunique()) if "cod_ibge" in df.columns else len(df),
        "extracao": "2026-07-28",
        "criterio_composite": "0.40*rho_nivel + 0.20*rho_score + 0.20*(sep/50) + 0.10*jaccard_top20 + 0.10*(mono/4)",
        "corr_blocos": corr_rows,
        "cobertura": {
            "risco_cumulativo_3d": 142,
            "utci_proxy": 142,
            "tmax": 142,
            "umidade_media": 142,
            "incidencia_srag_100k": 142,
            "casos_arbovirus_7d": 34,
            "pm25_ugm3": 12,
            "pressao_calor_pct": 142,
        },
        "schemes": schemes_sorted,
        "data_driven_pesos": {
            "tensao_climatica": dict(zip(c_keys, [round(float(x), 3) for x in c_w])),
            "carga_saude": dict(zip(s_keys, [round(float(x), 3) for x in s_w])),
            "vigilancia_integrada": dict(
                zip(["tensao", "carga", "pressao"], [round(float(x), 3) for x in v_w])
            ),
        },
        "grid_best": grid_best,
        "grid_top5": grid_sorted[:5],
        "chosen": chosen,
        "atual": get_indicator_config(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
