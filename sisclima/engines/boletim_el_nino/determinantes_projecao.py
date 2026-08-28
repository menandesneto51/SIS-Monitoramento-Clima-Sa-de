# -*- coding: utf-8 -*-
"""Determinantes do agravamento projetado (~7 dias) — boletim El Niño."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import bloco_tabela, fmt_frac, fmt_int, fmt_num, md_table
from sisclima.engines.predicao_skill_7d import documentacao_regra_projecao_md
from sisclima.engines.stages import STAGE_ORDER

log = get_logger(__name__)


def _cod7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False).str[:6]


def _ord(nivel: Any) -> int | None:
    if nivel is None or (isinstance(nivel, float) and pd.isna(nivel)):
        return None
    return STAGE_ORDER.get(str(nivel).lower().strip())


def _pct_txt(n_aff: int, n_base: int) -> str:
    if n_base <= 0:
        return "—"
    return f"{fmt_int(n_aff)} ({fmt_num(100.0 * n_aff / n_base, 1, '%')} dos que agravam)"


def quadro_determinantes_projecao(
    resumo: pd.DataFrame | None,
    predicao: pd.DataFrame | None = None,
    *,
    snap: dict[str, Any] | None = None,
) -> str:
    """Drivers do modelo vs contexto concomitante — sem atribuir contribuição a variáveis fora do cálculo."""
    snap = snap or {}
    delta = snap.get("delta_projecao") or {}
    n_up = int(snap.get("n_agravadores") or 0) or (
        int(delta.get("aumento_1") or 0) + int(delta.get("aumento_2plus") or 0)
    )
    n_d = snap.get("delta_n_comparavel") or snap.get("n_municipios")
    proj = snap.get("niveis_projecao_7d") or {}
    proj_crit = int(proj.get("vermelha") or 0) + int(proj.get("roxa") or 0)
    n = snap.get("n_municipios")
    crit = snap.get("n_vermelha_roxa")

    if resumo is None or resumo.empty:
        return (
            "### Determinantes do agravamento projetado\n\n"
            f"_{INDISPONIVEL}_\n\n"
            f"{documentacao_regra_projecao_md()}"
        )

    work = resumo.copy()
    if "cod_ibge" in work.columns:
        work["_cod"] = _cod7(work["cod_ibge"])
    else:
        work["_cod"] = pd.Series([pd.NA] * len(work), index=work.index)

    if predicao is not None and not predicao.empty:
        p = predicao.copy()
        if "cod_ibge" in p.columns:
            p["_cod"] = _cod7(p["cod_ibge"])
            keep = [
                c
                for c in (
                    "_cod",
                    "tmax_max_7d",
                    "utci_proxy_max_7d",
                    "risco_cumulativo_3d_max_7d",
                    "dias_onda_calor_prevista_7d",
                    "risco_termico_projetado_0_100",
                    "fonte_predicao",
                    "nivel_predicao_7d",
                )
                if c in p.columns or c == "_cod"
            ]
            p = p[[c for c in keep if c in p.columns]].drop_duplicates("_cod")
            work = work.merge(p, on="_cod", how="left", suffixes=("", "_pred"))

    if work["_cod"].notna().any():
        work = work.dropna(subset=["_cod"]).drop_duplicates("_cod")

    if "nivel" in work.columns and "nivel_predicao_7d" in work.columns:
        o_a = work["nivel"].map(_ord)
        o_p = work["nivel_predicao_7d"].map(_ord)
        mask_up = o_a.notna() & o_p.notna() & (o_p > o_a)
        agravados = work.loc[mask_up].copy()
    else:
        agravados = work.iloc[0:0].copy()

    n_agr = int(agravados["_cod"].nunique()) if "_cod" in agravados.columns else int(len(agravados))
    if n_up:
        n_agr = int(n_up)
    elif n_agr <= 0:
        n_agr = 1

    def _n_ge(col: str, thr: float) -> int:
        if col not in agravados.columns or agravados.empty:
            return 0
        s = pd.to_numeric(agravados[col], errors="coerce")
        n_hit = int((s >= thr).sum())
        if n_hit > n_agr:
            log.warning("QA_FAIL driver %s=%s > n_agravadores=%s", col, n_hit, n_agr)
            n_hit = n_agr
        return n_hit

    n_tmax37 = _n_ge("tmax_max_7d", 37)
    n_utci36 = _n_ge("utci_proxy_max_7d", 36)
    n_risco7 = _n_ge("risco_cumulativo_3d_max_7d", 7)
    n_onda = _n_ge("dias_onda_calor_prevista_7d", 1)
    snap["n_onda_calor_agravadores"] = n_onda
    mediana_onda = None
    if "dias_onda_calor_prevista_7d" in agravados.columns and not agravados.empty:
        s_onda = pd.to_numeric(agravados["dias_onda_calor_prevista_7d"], errors="coerce")
        if s_onda.notna().any():
            mediana_onda = float(s_onda.median())

    n_pm = 0
    if "pm25_ugm3" in agravados.columns and not agravados.empty:
        n_pm = int((pd.to_numeric(agravados["pm25_ugm3"], errors="coerce") >= 25).sum())
    n_umi = 0
    if "umidade_media" in agravados.columns and not agravados.empty:
        n_umi = int((pd.to_numeric(agravados["umidade_media"], errors="coerce") <= 30).sum())
    n_fogo = 0
    fcol = next((c for c in ("focos_queimadas_7d", "focos_7d") if c in agravados.columns), None)
    if fcol and not agravados.empty:
        n_fogo = int((pd.to_numeric(agravados[fcol], errors="coerce") >= 1).sum())

    rodada = snap.get("rodada_em_pt") or snap.get("rodada_em")
    fonte_t2 = (
        f"previsão meteorológica integrada ao ARARAS MT, rodada de {rodada}."
        if rodada
        else "previsão meteorológica integrada ao ARARAS MT."
    )
    fonte_t3 = (
        f"ARARAS MT/CIEVS-MT, rodada de {rodada}."
        if rodada
        else "ARARAS MT/CIEVS-MT."
    )

    intro = (
        f"A projeção operacional (~7 dias) eleva o território de **{fmt_frac(crit, n)}** para "
        f"**{fmt_frac(proj_crit, n)}** municípios nas classes vermelha ou roxa"
        if crit is not None and proj_crit and n
        else "A projeção operacional (~7 dias) indica agravamento territorial."
    )
    if n_up and n_d:
        intro += f", com **{fmt_frac(n_up, n_d)}** municípios comparáveis em elevação de classe."

    onda_extra = (
        f" (mediana {fmt_num(mediana_onda, 1)} dias)"
        if mediana_onda is not None
        else ""
    )

    rows_drivers = [
        ["Tmáx prevista (máx. 7d ≥ 37 °C)", _pct_txt(n_tmax37, n_agr), "↑ aumento"],
        ["UTCI previsto (máx. 7d ≥ 36 °C)", _pct_txt(n_utci36, n_agr), "↑ aumento"],
        ["Risco térmico cumulativo (máx. 7d ≥ 7 pontos)", _pct_txt(n_risco7, n_agr), "↑ aumento"],
        [f"Onda de calor prevista no horizonte{onda_extra}", _pct_txt(n_onda, n_agr), "↑ aumento"],
    ]
    def _leitura_ctx(n_hit: int | None, presente: str, ausente: str | None = None) -> str:
        if n_hit is None:
            return presente
        if int(n_hit) == 0:
            return ausente or (
                "Limiar não observado entre os municípios em agravamento nesta rodada."
            )
        return presente

    rows_ctx = [
        [
            "Umidade relativa ≤ 30%",
            _pct_txt(n_umi, n_agr),
            _leitura_ctx(n_umi, "Baixa umidade presente no cenário atual"),
        ],
        [
            "PM2,5 ≥ 25 µg/m³",
            _pct_txt(n_pm, n_agr),
            _leitura_ctx(n_pm, "Exposição atual; sem projeção específica de 7 dias"),
        ],
        [
            "Focos de calor (7 dias)",
            _pct_txt(n_fogo, n_agr),
            _leitura_ctx(n_fogo, "Detecção atual; sem projeção específica de 7 dias"),
        ],
    ]

    tab_a = bloco_tabela(
        "Determinantes do agravamento projetado em aproximadamente sete dias",
        md_table(
            ["Driver do modelo", "Municípios afetados", "Direção"],
            rows_drivers,
        ),
        fonte_t2,
    )
    tab_b = bloco_tabela(
        "Contexto ambiental concomitante nos municípios com elevação projetada da classificação",
        md_table(
            ["Contexto concomitante", "Municípios afetados", "Leitura"],
            rows_ctx,
        ),
        fonte_t3,
        nota="Ausência de previsão específica não equivale a estabilidade.",
    )

    return (
        f"### Determinantes do agravamento projetado\n\n"
        f"{intro}\n\n"
        f"### A. Drivers que entram no modelo\n\n"
        f"{tab_a}\n\n"
        f"### B. Contexto concomitante\n\n"
        f"Descreve a situação atual dos municípios que sobem de classe; "
        f"**não** constitui contribuição matemática para a projeção nesta versão.\n\n"
        f"{tab_b}\n\n"
        "A classe projetada utiliza o maior nível entre intensidade térmica, estresse térmico, "
        "persistência e onda de calor, evitando a soma de sinais correlacionados. "
        "Classes: 0–24 verde; 25–49 amarela; 50–69 laranja; 70–84 vermelha; 85–100 roxa. "
        "Detalhamento dos limiares na seção de notas metodológicas."
    )
