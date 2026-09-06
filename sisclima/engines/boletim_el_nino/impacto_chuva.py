# -*- coding: utf-8 -*-
"""Impacto operacional de pancadas de chuva na semana (alívio térmico temporário)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

# Datas-chave do evento de alívio na SE 35/2026
DATA_PICO = "2026-08-31"
DATA_CHUVA = "2026-09-01"
DATA_POS = "2026-09-02"


def resumo_impacto_chuva(
    *,
    data_pico: str = DATA_PICO,
    data_chuva: str = DATA_CHUVA,
    data_pos: str = DATA_POS,
    cod_cuiaba6: str = "510340",
) -> dict[str, Any]:
    """Compara precipitação × Tmáx nos dias do pico e da pancada."""
    out: dict[str, Any] = {"ok": False, "markdown": "", "dias": []}
    if not table_exists("hist_clima_municipal_diario"):
        return out
    hist = read_table("hist_clima_municipal_diario")
    if hist is None or hist.empty:
        return out
    h = hist.copy()
    h["cod6"] = h["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str[:6]
    h["data"] = pd.to_datetime(h["data"], errors="coerce")
    h["precip"] = pd.to_numeric(h.get("precipitacao_mm"), errors="coerce").fillna(0.0)
    h["tmax"] = pd.to_numeric(h.get("tmax"), errors="coerce")
    h = h.dropna(subset=["data"]).sort_values(["cod6", "data", "fonte" if "fonte" in h.columns else "data"])
    h = h.drop_duplicates(["cod6", "data"], keep="last")

    dias_alvo = [data_pico, data_chuva, data_pos]
    rows: list[dict[str, Any]] = []
    for d in dias_alvo:
        day = h[h["data"] == pd.Timestamp(d)]
        if day.empty:
            continue
        rows.append(
            {
                "data": d,
                "n": int(day["cod6"].nunique()),
                "chuva_ge1": int((day["precip"] >= 1.0).sum()),
                "tmax_ge37": int((day["tmax"] >= 37.0).sum()),
                "tmax_med": float(day["tmax"].mean()) if day["tmax"].notna().any() else None,
                "tmax_max": float(day["tmax"].max()) if day["tmax"].notna().any() else None,
                "precip_med": float(day["precip"].median()),
                "precip_max": float(day["precip"].max()),
            }
        )
    if not rows:
        return out

    cui = h[(h["cod6"] == cod_cuiaba6) & (h["data"].isin([pd.Timestamp(x) for x in dias_alvo]))].copy()
    cui_map: dict[str, dict[str, float]] = {}
    for _, r in cui.iterrows():
        cui_map[str(r["data"].date())] = {
            "tmax": float(r["tmax"]) if pd.notna(r["tmax"]) else None,
            "precip": float(r["precip"]),
        }

    out.update(
        {
            "ok": True,
            "dias": rows,
            "cuiaba": cui_map,
            "data_chuva": data_chuva,
            "data_pico": data_pico,
        }
    )
    out["markdown"] = markdown_impacto_chuva(out)
    return out


def markdown_impacto_chuva(resumo: dict[str, Any] | None = None) -> str:
    from sisclima.engines.boletim_el_nino.formatters import fmt_frac, fmt_int, fmt_num, md_table

    a = resumo or resumo_impacto_chuva()
    if not a.get("ok"):
        return ""
    rows_md = []
    for r in a.get("dias") or []:
        n = r.get("n") or 142
        rows_md.append(
            [
                str(r.get("data") or "—"),
                fmt_frac(r.get("chuva_ge1"), n),
                fmt_frac(r.get("tmax_ge37"), n),
                fmt_num(r.get("tmax_med"), 1),
                fmt_num(r.get("precip_med"), 1),
            ]
        )
    pico = next((x for x in (a.get("dias") or []) if x.get("data") == a.get("data_pico")), None)
    chuva = next((x for x in (a.get("dias") or []) if x.get("data") == a.get("data_chuva")), None)
    cui = a.get("cuiaba") or {}
    cui_pico = cui.get(str(a.get("data_pico")) or "") or {}
    cui_chuva = cui.get(str(a.get("data_chuva")) or "") or {}

    linhas = [
        "",
        "### Impacto da chuva de 01/09/2026 (alívio térmico temporário)",
        "",
        "Pancadas de segunda (01/09) reduziram o calor extremo no estado; a projeção ~7 dias "
        "volta a pressionar. Foi **oscilação**, não encerramento da exposição térmica.",
        "",
    ]
    if pico and chuva:
        linhas.append(
            f"- **Antes (31/08):** {fmt_frac(pico.get('tmax_ge37'), pico.get('n'))} com Tmáx ≥ 37 °C · "
            f"Tmáx média **{fmt_num(pico.get('tmax_med'), 1, ' °C')}** · "
            f"chuva ≥1 mm em {fmt_frac(pico.get('chuva_ge1'), pico.get('n'))}."
        )
        linhas.append(
            f"- **Com chuva (01/09):** {fmt_frac(chuva.get('tmax_ge37'), chuva.get('n'))} com Tmáx ≥ 37 °C · "
            f"Tmáx média **{fmt_num(chuva.get('tmax_med'), 1, ' °C')}** · "
            f"chuva ≥1 mm em {fmt_frac(chuva.get('chuva_ge1'), chuva.get('n'))} "
            f"(mediana **{fmt_num(chuva.get('precip_med'), 1, ' mm')}**, máx. **{fmt_num(chuva.get('precip_max'), 1, ' mm')}**)."
        )
    if cui_pico.get("tmax") is not None and cui_chuva.get("tmax") is not None:
        linhas.append(
            f"- **Cuiabá:** Tmáx **{fmt_num(cui_pico.get('tmax'), 1, ' °C')}** (31/08) → "
            f"**{fmt_num(cui_chuva.get('tmax'), 1, ' °C')}** (01/09, precip. **{fmt_num(cui_chuva.get('precip'), 1, ' mm')}**)."
        )
    if rows_md:
        linhas.extend(
            [
                "",
                md_table(
                    ["Data", "Mun. chuva ≥1 mm", "Mun. Tmáx ≥37 °C", "Tmáx média (°C)", "Precip. mediana (mm)"],
                    rows_md,
                ),
                "",
                "Fonte: grade operacional ARARAS MT / Open-Meteo (um município por dia).",
            ]
        )
    return "\n".join(linhas)
