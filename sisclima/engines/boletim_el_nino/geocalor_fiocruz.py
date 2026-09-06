# -*- coding: utf-8 -*-
"""Monitoramento de ondas de calor — metodologia GeoCalor / EHF (Fiocruz–LAGAS).

Definição operacional (Nairn & Fawcett, adotada no GeoCalor):
- Tmédia diária; T3d = média móvel de 3 dias; T30d = média dos 30 dias anteriores.
- EHIsig = T3d − P95(Tmédia local)
- EHIaccl = T3d − T30d
- EHF = EHIsig × max(1, EHIaccl)
- Evento: ≥ 3 dias consecutivos com EHF > 0
- Intensidade (dias com EHF > 0): baixa ≤ EHF85; severa ≤ 3×EHF85; extrema > 3×EHF85

Fonte de dados no ARARAS: tabelas ``star_clima_geocalor_diario`` e ``star_ondas_calor_evento``
(cálculo estadual para os 142 municípios; o portal GeoCalor não publica Cuiabá/MT).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from sisclima.engines.ehf_geocalor import METODOLOGIA, MIN_DIAS_EVENTO

COD_CUIABA = "5103403"


def _ibge7(val: object) -> str:
    s = str(val or "").replace(".0", "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(7)[:7]


def resumo_geocalor_fiocruz(
    *,
    janela_dias: int = 14,
    data_fim: str | None = None,
) -> dict[str, Any]:
    """Consolida EHF/GeoCalor para a janela do boletim."""
    out: dict[str, Any] = {
        "ok": False,
        "metodologia": METODOLOGIA,
        "metodologia_rotulo": "GeoCalor / EHF (Fiocruz–LAGAS / Nairn & Fawcett)",
        "min_dias_evento": MIN_DIAS_EVENTO,
        "markdown": "",
    }
    try:
        from sisclima.core.db import read_table

        daily = read_table("star_clima_geocalor_diario")
        eventos = read_table("star_ondas_calor_evento")
    except Exception as exc:  # noqa: BLE001
        out["motivo"] = f"tabelas indisponíveis: {exc}"
        out["markdown"] = markdown_geocalor_fiocruz(out)
        return out

    if daily is None or daily.empty:
        out["motivo"] = "star_clima_geocalor_diario vazia"
        out["markdown"] = markdown_geocalor_fiocruz(out)
        return out

    df = daily.copy()
    df["cod_ibge"] = df["cod_ibge"].map(_ibge7)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["ehf"] = pd.to_numeric(df.get("ehf"), errors="coerce")
    df["is_hw_day"] = pd.to_numeric(df.get("is_hw_day"), errors="coerce").fillna(0).astype(int)
    df = df.dropna(subset=["data", "cod_ibge"])
    if df.empty:
        out["motivo"] = "sem datas válidas"
        out["markdown"] = markdown_geocalor_fiocruz(out)
        return out

    fim = pd.to_datetime(data_fim, errors="coerce") if data_fim else df["data"].max()
    if pd.isna(fim):
        fim = df["data"].max()
    fim = min(fim, df["data"].max())
    ini = fim - timedelta(days=max(1, int(janela_dias) - 1))
    w = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
    if w.empty:
        out["motivo"] = "janela sem dados"
        out["markdown"] = markdown_geocalor_fiocruz(out)
        return out

    last_day = w["data"].max()
    last = w[w["data"] == last_day]
    n_mun = int(w["cod_ibge"].nunique())
    n_hw_last = int((last["is_hw_day"] > 0).sum())
    ints_last = (
        last.loc[last["is_hw_day"] > 0, "intensidade"].fillna("baixa").astype(str).str.casefold().value_counts().to_dict()
        if n_hw_last
        else {}
    )

    # Municípios com ≥1 dia de onda na janela
    mun_hw = w.loc[w["is_hw_day"] > 0].groupby("cod_ibge", as_index=False).agg(
        dias_onda=("is_hw_day", "sum"),
        ehf_max=("ehf", "max"),
        municipio=("municipio", "first") if "municipio" in w.columns else ("cod_ibge", "first"),
    )
    n_mun_hw = int(len(mun_hw))

    # Série diária: n municípios em onda
    serie = (
        w.groupby("data", as_index=False)
        .agg(n_onda=("is_hw_day", lambda s: int((s > 0).sum())), n=("cod_ibge", "nunique"))
        .sort_values("data")
    )
    serie["data"] = serie["data"].dt.strftime("%Y-%m-%d")

    # Eventos sobrepostos à janela
    ev_rows: list[dict[str, Any]] = []
    n_ev = 0
    n_ev_mun = 0
    ints_ev: dict[str, int] = {}
    if eventos is not None and not eventos.empty:
        ev = eventos.copy()
        ev["cod_ibge"] = ev["cod_ibge"].map(_ibge7)
        ev["data_inicio"] = pd.to_datetime(ev["data_inicio"], errors="coerce")
        ev["data_fim"] = pd.to_datetime(ev["data_fim"], errors="coerce")
        ev["ehf_max"] = pd.to_numeric(ev.get("ehf_max"), errors="coerce")
        ov = ev[(ev["data_fim"] >= ini) & (ev["data_inicio"] <= fim)].copy()
        n_ev = int(len(ov))
        n_ev_mun = int(ov["cod_ibge"].nunique()) if n_ev else 0
        if n_ev:
            ints_ev = ov["intensidade"].fillna("baixa").astype(str).str.casefold().value_counts().to_dict()
            top = ov.nlargest(10, "ehf_max")
            for _, r in top.iterrows():
                ev_rows.append(
                    {
                        "municipio": str(r.get("municipio") or "—"),
                        "cod_ibge": str(r.get("cod_ibge") or ""),
                        "data_inicio": r["data_inicio"].strftime("%Y-%m-%d") if pd.notna(r["data_inicio"]) else "—",
                        "data_fim": r["data_fim"].strftime("%Y-%m-%d") if pd.notna(r["data_fim"]) else "—",
                        "duracao_dias": int(r.get("duracao_dias") or 0),
                        "ehf_max": float(r["ehf_max"]) if pd.notna(r["ehf_max"]) else None,
                        "intensidade": str(r.get("intensidade") or "—"),
                    }
                )

    # Cuiabá
    cui = w[w["cod_ibge"] == COD_CUIABA].sort_values("data")
    cuiaba: dict[str, Any] = {"ok": not cui.empty}
    if not cui.empty:
        cui_hw = cui[cui["is_hw_day"] > 0]
        last_c = cui.iloc[-1]
        ints = cui_hw["intensidade"].dropna().astype(str).str.casefold() if not cui_hw.empty else pd.Series(dtype=str)
        if (ints == "extrema").any():
            pico_int = "extrema"
        elif (ints == "severa").any():
            pico_int = "severa"
        elif not ints.empty:
            pico_int = "baixa"
        else:
            pico_int = None
        cuiaba.update(
            {
                "dias_onda_janela": int(len(cui_hw)),
                "ehf_max": float(cui["ehf"].max()) if cui["ehf"].notna().any() else None,
                "ultimo_dia": last_c["data"].strftime("%Y-%m-%d"),
                "ehf_ultimo": float(last_c["ehf"]) if pd.notna(last_c["ehf"]) else None,
                "em_onda_ultimo": bool(int(last_c["is_hw_day"]) > 0),
                "intensidade_pico": pico_int,
            }
        )

    out.update(
        {
            "ok": True,
            "janela_inicio": ini.strftime("%Y-%m-%d"),
            "janela_fim": fim.strftime("%Y-%m-%d"),
            "data_referencia_serie": last_day.strftime("%Y-%m-%d"),
            "n_municipios": n_mun,
            "n_mun_onda_ultimo_dia": n_hw_last,
            "intensidade_ultimo_dia": {
                "baixa": int(ints_last.get("baixa") or 0),
                "severa": int(ints_last.get("severa") or 0),
                "extrema": int(ints_last.get("extrema") or 0),
            },
            "n_mun_com_onda_janela": n_mun_hw,
            "n_eventos_janela": n_ev,
            "n_mun_com_evento_janela": n_ev_mun,
            "intensidade_eventos": {
                "baixa": int(ints_ev.get("baixa") or 0),
                "severa": int(ints_ev.get("severa") or 0),
                "extrema": int(ints_ev.get("extrema") or 0),
            },
            "ranking_eventos": ev_rows,
            "serie_diaria_n_onda": serie.to_dict(orient="records"),
            "cuiaba": cuiaba,
            "fonte_tabelas": ["star_clima_geocalor_diario", "star_ondas_calor_evento"],
            "nota": (
                "Cálculo estadual ARARAS com a mesma definição EHF do GeoCalor. "
                "O portal GeoCalor não publica Cuiabá/MT; a série local é derivada da grade municipal."
            ),
        }
    )
    out["markdown"] = markdown_geocalor_fiocruz(out)
    return out


def markdown_geocalor_fiocruz(resumo: dict[str, Any] | None = None) -> str:
    a = resumo or {}
    if not a.get("ok"):
        return (
            "\n### Monitoramento climático — metodologia GeoCalor / EHF (Fiocruz)\n\n"
            f"Indisponível nesta rodada ({a.get('motivo') or 'sem dados'}).\n"
        )

    ini = a.get("janela_inicio") or "—"
    fim = a.get("janela_fim") or "—"
    n = a.get("n_municipios")
    iu = a.get("intensidade_ultimo_dia") or {}
    ie = a.get("intensidade_eventos") or {}
    cui = a.get("cuiaba") or {}
    linhas = [
        "",
        "### Monitoramento climático — metodologia GeoCalor / EHF (Fiocruz)",
        "",
        f"**Método:** {a.get('metodologia_rotulo')} — evento = ≥ {a.get('min_dias_evento', 3)} dias "
        "consecutivos com EHF > 0; intensidade pela distribuição local dos EHF positivos (EHF85).",
        "",
        f"- **Janela:** {ini} a {fim} · **{n}** municípios com série EHF.",
        f"- **Último dia da série ({a.get('data_referencia_serie')}):** "
        f"**{a.get('n_mun_onda_ultimo_dia')}** municípios em dia de onda "
        f"(baixa **{iu.get('baixa', 0)}** · severa **{iu.get('severa', 0)}** · extrema **{iu.get('extrema', 0)}**).",
        f"- **Na janela:** **{a.get('n_mun_com_onda_janela')}** municípios com ≥ 1 dia de onda · "
        f"**{a.get('n_eventos_janela')}** eventos (≥ 3 dias) em **{a.get('n_mun_com_evento_janela')}** municípios "
        f"(baixa **{ie.get('baixa', 0)}** · severa **{ie.get('severa', 0)}** · extrema **{ie.get('extrema', 0)}**).",
    ]
    if cui.get("ok"):
        em = "sim" if cui.get("em_onda_ultimo") else "não"
        linhas.append(
            f"- **Cuiabá (EHF):** {cui.get('dias_onda_janela', 0)} dia(s) de onda na janela · "
            f"EHF máx. **{_fmt(cui.get('ehf_max'))}** · pico de intensidade **{cui.get('intensidade_pico') or '—'}** · "
            f"em onda no último dia da série: **{em}**."
        )
    ranking = a.get("ranking_eventos") or []
    if ranking:
        from sisclima.engines.boletim_el_nino.formatters import fmt_num, md_table

        rows = [
            [
                str(r.get("municipio") or "—"),
                f"{r.get('data_inicio')}–{r.get('data_fim')}",
                str(r.get("duracao_dias") or "—"),
                fmt_num(r.get("ehf_max"), 2),
                str(r.get("intensidade") or "—"),
            ]
            for r in ranking[:8]
        ]
        linhas.extend(
            [
                "",
                "**Eventos com maiores valores máximos de EHF na janela**",
                "",
                md_table(["Município", "Período", "Dias", "EHF máx.", "Intensidade"], rows),
                "",
                "A categoria de intensidade é relativa ao limiar local de cada município; "
                "valores brutos de EHF não devem ser utilizados isoladamente para ordenar "
                "severidade entre municípios. Tabela ordenada pelo EHF máximo bruto.",
                "",
                "Fonte: cálculo EHF estadual ARARAS (definição GeoCalor / Nairn & Fawcett). "
                "Não substitui avisos do INMET.",
            ]
        )
    linhas.extend(
        [
            "",
            f"Nota: {a.get('nota') or ''}",
            "",
        ]
    )
    return "\n".join(linhas)


def _fmt(val: Any) -> str:
    try:
        if val is None:
            return "—"
        return f"{float(val):.2f}"
    except (TypeError, ValueError):
        return "—"
