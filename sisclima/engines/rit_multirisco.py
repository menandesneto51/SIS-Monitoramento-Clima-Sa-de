# -*- coding: utf-8 -*-
"""RIT — Risco Integrado Territorial (multirisco observado).

Produto paralelo ao MODELO ~7 DIAS (risco térmico projetado).
Composição v1: máximo entre escores de domínio válidos (anti-redundância).
Ver docs/adr/ADR-RIT-multirisco.md.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

# Limiar de frescor para domínio pressão (dias). Acima disso: domínio omitido.
MAX_IDADE_PRESSAO_DIAS = 14

DOMINIOS = ("termico", "ar", "hidro", "ehf", "pressao", "rede")

DOMINIO_ROTULOS = {
    "termico": "Térmico",
    "ar": "Ar/PM2,5",
    "hidro": "Hidrologia",
    "ehf": "EHF",
    "pressao": "Pressão assistencial",
    "rede": "Fragilidade de rede",
}

RIT_COLS = [
    "rit_0_100",
    "rit_faixa",
    "rit_dominio_dominante",
    "rit_completude_pct",
    "rit_score_termico",
    "rit_score_ar",
    "rit_score_hidro",
    "rit_score_ehf",
    "rit_score_pressao",
    "rit_score_rede",
    "rit_pressao_omitida_defasagem",
]

# Mesmas faixas do risco térmico projetado (comparabilidade visual)
_LIMIARES_FAIXA = ((85, "roxa"), (70, "vermelha"), (50, "laranja"), (25, "amarela"), (0, "verde"))

_LIMIARES_PM25 = ((25.0, 50), (50.0, 75), (75.0, 100))
_LIMIARES_EHF = ((0.0, 70), (2.0, 85), (5.0, 100))  # >0 → ≥70; valores altos → 85–100


def _num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(x):
        return None
    return x


def _score_from_thresholds(value: float | None, limiares: tuple[tuple[float, int], ...]) -> float:
    if value is None:
        return 0.0
    score = 0
    for thr, pts in limiares:
        if value >= thr:
            score = pts
    return float(score)


def faixa_rit(score: float | None) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "—"
    s = float(score)
    for thr, nome in _LIMIARES_FAIXA:
        if s >= thr:
            return nome
    return "verde"


def _nivel_to_score(nivel: Any) -> float | None:
    if nivel is None or (isinstance(nivel, float) and np.isnan(nivel)):
        return None
    key = str(nivel).strip().lower()
    if key not in STAGE_ORDER:
        return None
    ord_ = int(STAGE_ORDER[key])
    if ord_ < 0:
        return None
    # verde=0 … roxa=4 → 0, 25, 50, 75, 100
    return float(ord_ * 25)


def score_dominio_termico(row: pd.Series | dict) -> float | None:
    """Térmico observado: classe atual ou proxy UTCI/Tmáx do dia."""
    n = _nivel_to_score(row.get("nivel"))
    if n is not None:
        return n
    utci = _num(row.get("utci_proxy"))
    tmax = _num(row.get("tmax"))
    scores: list[float] = []
    if utci is not None:
        scores.append(_score_from_thresholds(utci, ((44.0, 100), (40.0, 75), (36.0, 50), (32.0, 25))))
    if tmax is not None:
        scores.append(_score_from_thresholds(tmax, ((42.0, 100), (40.0, 75), (37.0, 50), (34.0, 25))))
    if not scores:
        return None
    return float(max(scores))


def score_dominio_ar(row: pd.Series | dict) -> float | None:
    pm = _num(row.get("pm25_ugm3"))
    if pm is None:
        return None
    return _score_from_thresholds(pm, _LIMIARES_PM25)


def score_dominio_hidro(row: pd.Series | dict) -> float | None:
    for key in ("nivel_alerta_hidro", "nivel_cemaden"):
        s = _nivel_to_score(row.get(key))
        if s is not None:
            return s
    sit = str(row.get("situacao_hidro") or "").strip().lower()
    if not sit or sit in {"nan", "none", ""}:
        return None
    if sit in {"habitual", "normal"}:
        return 0.0
    if sit in {"seca_baixa", "estiagem", "estiagem_rio_baixo"}:
        return 50.0
    if sit in {"inundacao_alta", "cheia", "cheia_subida_rio"}:
        return 75.0
    return 25.0


def score_dominio_ehf(row: pd.Series | dict) -> float | None:
    """EHF observado (GeoCalor). Ausência de coluna/valor → domínio omitido."""
    ehf = _num(row.get("ehf_geocalor"))
    if ehf is None:
        ehf = _num(row.get("ehf"))
    if ehf is None:
        ehf = _num(row.get("ehf_adaptado"))
    if ehf is None:
        ehf = _num(row.get("ehf_max"))
    if ehf is None:
        return None
    if ehf <= 0:
        return 0.0
    return _score_from_thresholds(ehf, _LIMIARES_EHF)


def _idade_pressao_dias(row: pd.Series | dict, ref_hoje: pd.Timestamp | None = None) -> int | None:
    """Idade da carga de pressão/APS em dias, se inferível."""
    hoje = (ref_hoje or pd.Timestamp.today()).normalize()
    # Não usar data_referencia climática da rodada — senão pressão “parece” fresca.
    for key in (
        "pressao_data_referencia",
        "data_carga_pressao",
        "esus_data_carga",
        "data_carga_esus",
    ):
        raw = row.get(key)
        if raw is None or (isinstance(raw, float) and np.isnan(raw)):
            continue
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.isna(ts):
            continue
        return int((hoje - pd.Timestamp(ts).normalize()).days)
    idade = _num(row.get("pressao_idade_dias"))
    if idade is not None:
        return int(idade)
    idade = _num(row.get("esus_idade_dias"))
    if idade is not None:
        return int(idade)
    return None


def score_dominio_pressao(
    row: pd.Series | dict,
    *,
    max_idade_dias: int = MAX_IDADE_PRESSAO_DIAS,
    ref_hoje: pd.Timestamp | None = None,
) -> tuple[float | None, bool]:
    """Retorna (score|None, omitida_por_defasagem)."""
    idade = _idade_pressao_dias(row, ref_hoje=ref_hoje)
    if idade is not None and idade > int(max_idade_dias):
        return None, True
    press = _num(row.get("indice_pressao_saude"))
    if press is None:
        return None, False
    return float(np.clip(press, 0.0, 100.0)), False


def score_dominio_rede(row: pd.Series | dict) -> float | None:
    """Fragilidade de rede = 100 − IRM (capacidade). Omitido se IRM nulo."""
    from sisclima.engines.indice_resiliencia_municipal import fragilidade_rede_from_irm

    irm = _num(row.get("indice_resiliencia_municipal_0_100"))
    return fragilidade_rede_from_irm(irm)


def rit_municipal(
    row: pd.Series | dict,
    *,
    max_idade_pressao_dias: int = MAX_IDADE_PRESSAO_DIAS,
    ref_hoje: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Calcula RIT e metadados para um município."""
    scores: dict[str, float | None] = {
        "termico": score_dominio_termico(row),
        "ar": score_dominio_ar(row),
        "hidro": score_dominio_hidro(row),
        "ehf": score_dominio_ehf(row),
    }
    press, omit_defasagem = score_dominio_pressao(
        row, max_idade_dias=max_idade_pressao_dias, ref_hoje=ref_hoje
    )
    scores["pressao"] = press
    scores["rede"] = score_dominio_rede(row)

    valid = {k: float(v) for k, v in scores.items() if v is not None}
    n_dom = len(DOMINIOS)
    completude = 100.0 * len(valid) / float(n_dom) if n_dom else 0.0
    base_scores = {
        "rit_score_termico": scores["termico"],
        "rit_score_ar": scores["ar"],
        "rit_score_hidro": scores["hidro"],
        "rit_score_ehf": scores["ehf"],
        "rit_score_pressao": scores["pressao"],
        "rit_score_rede": scores["rede"],
        "rit_pressao_omitida_defasagem": bool(omit_defasagem),
        "regra_composicao": "max_dominios_validos",
    }
    if not valid:
        return {
            "rit_0_100": np.nan,
            "rit_faixa": "—",
            "rit_dominio_dominante": "—",
            "rit_completude_pct": float(completude),
            **base_scores,
        }

    dominante = max(valid.items(), key=lambda kv: kv[1])[0]
    rit = float(max(valid.values()))
    return {
        "rit_0_100": rit,
        "rit_faixa": faixa_rit(rit),
        "rit_dominio_dominante": dominante,
        "rit_completude_pct": float(round(completude, 1)),
        **base_scores,
    }


def scorecard_rit(
    row: pd.Series | dict | None = None,
    *,
    rit: dict[str, Any] | None = None,
    max_idade_pressao_dias: int = MAX_IDADE_PRESSAO_DIAS,
    ref_hoje: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Scorecard RIT: geral + domínio dominante + faixa/score de cada fator.

    Aceita linha bruta do resumo ou dict já calculado por ``rit_municipal``.
    """
    if rit is None:
        if row is None:
            return {
                "disponivel": False,
                "rit_0_100": None,
                "rit_faixa": "—",
                "dominio_dominante": "—",
                "explicacao_dominante": "RIT indisponível.",
                "dominios": [],
                "radar_compacto": "—",
            }
        rit = rit_municipal(
            row, max_idade_pressao_dias=max_idade_pressao_dias, ref_hoje=ref_hoje
        )
    else:
        rit = dict(rit)

    omit_pressao = bool(rit.get("rit_pressao_omitida_defasagem"))
    score_map = {
        "termico": rit.get("rit_score_termico"),
        "ar": rit.get("rit_score_ar"),
        "hidro": rit.get("rit_score_hidro"),
        "ehf": rit.get("rit_score_ehf"),
        "pressao": rit.get("rit_score_pressao"),
        "rede": rit.get("rit_score_rede"),
    }

    dominios: list[dict[str, Any]] = []
    for did in DOMINIOS:
        sc = score_map.get(did)
        if did == "pressao" and omit_pressao and sc is None:
            status = "omitido_defasagem"
            faixa = "—"
        elif sc is None or (isinstance(sc, float) and np.isnan(sc)):
            status = "indisponivel"
            faixa = "—"
            sc = None
        else:
            status = "valido"
            sc = float(sc)
            faixa = faixa_rit(sc)
        dominios.append(
            {
                "id": did,
                "rotulo": DOMINIO_ROTULOS.get(did, did),
                "score": sc,
                "faixa": faixa,
                "status": status,
            }
        )

    rit_score = rit.get("rit_0_100")
    if rit_score is None or (isinstance(rit_score, float) and np.isnan(rit_score)):
        return {
            "disponivel": False,
            "rit_0_100": None,
            "rit_faixa": "—",
            "dominio_dominante": "—",
            "explicacao_dominante": "RIT indisponível (nenhum domínio válido).",
            "dominios": dominios,
            "radar_compacto": radar_compacto(dominios),
            "rit_completude_pct": rit.get("rit_completude_pct"),
            "rit_pressao_omitida_defasagem": omit_pressao,
        }

    dominante = str(rit.get("rit_dominio_dominante") or "—")
    faixa_geral = str(rit.get("rit_faixa") or faixa_rit(float(rit_score)))
    dom_item = next((d for d in dominios if d["id"] == dominante), None)
    if dom_item and dom_item.get("status") == "valido":
        explicacao = (
            f"RIT puxado por {dom_item['rotulo']} "
            f"({_fmt_score(dom_item['score'])} → {dom_item['faixa']})"
        )
    else:
        explicacao = f"RIT puxado por {DOMINIO_ROTULOS.get(dominante, dominante)}"

    demais = [
        d
        for d in dominios
        if d["id"] != dominante
    ]
    partes_demais: list[str] = []
    for d in demais:
        if d["status"] == "valido":
            partes_demais.append(f"{d['rotulo']} {d['faixa']}")
        elif d["status"] == "omitido_defasagem":
            partes_demais.append(f"{d['rotulo']} omitida")
        else:
            partes_demais.append(f"{d['rotulo']} —")
    if partes_demais:
        explicacao = f"{explicacao}; demais: {', '.join(partes_demais)}"

    return {
        "disponivel": True,
        "rit_0_100": float(rit_score),
        "rit_faixa": faixa_geral,
        "dominio_dominante": dominante,
        "explicacao_dominante": explicacao,
        "dominios": dominios,
        "radar_compacto": radar_compacto(dominios),
        "rit_completude_pct": rit.get("rit_completude_pct"),
        "rit_pressao_omitida_defasagem": omit_pressao,
    }


def _fmt_score(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    try:
        f = float(v)
        if abs(f - int(f)) < 1e-9:
            return str(int(f))
        return f"{f:.0f}"
    except (TypeError, ValueError):
        return "—"


def radar_compacto(dominios: list[dict[str, Any]]) -> str:
    """String curta para alertas: EHF:roxa · Térmico:laranja · Ar:verde …"""
    parts: list[str] = []
    for d in dominios or []:
        rot = d.get("rotulo") or d.get("id") or "?"
        st = d.get("status")
        if st == "omitido_defasagem":
            parts.append(f"{rot}:omitida")
        elif st == "indisponivel" or d.get("faixa") in (None, "—", ""):
            parts.append(f"{rot}:—")
        else:
            parts.append(f"{rot}:{d.get('faixa')}")
    return " · ".join(parts) if parts else "—"


def enrich_rit_multirisco(
    resumo: pd.DataFrame,
    *,
    max_idade_pressao_dias: int = MAX_IDADE_PRESSAO_DIAS,
    ref_hoje: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Acrescenta colunas RIT ao resumo municipal."""
    if resumo is None or resumo.empty:
        return resumo
    df = resumo.copy()
    # Garante EHF GeoCalor antes do scorecard (join leve se ainda não houver)
    if "ehf_geocalor" not in df.columns or pd.to_numeric(df.get("ehf_geocalor"), errors="coerce").notna().sum() < max(
        1, int(0.5 * len(df))
    ):
        try:
            from sisclima.engines.ehf_geocalor import inject_ehf_geocalor

            df = inject_ehf_geocalor(df, prefer_geocalor=True)
        except Exception:
            pass
    rows = [
        rit_municipal(r, max_idade_pressao_dias=max_idade_pressao_dias, ref_hoje=ref_hoje)
        for _, r in df.iterrows()
    ]
    extra = pd.DataFrame(rows, index=df.index)
    for c in RIT_COLS:
        if c in df.columns:
            df = df.drop(columns=[c])
        df[c] = extra[c]
    return df


def resumo_rit_estadual(resumo: pd.DataFrame, top_n: int = 10) -> dict[str, Any]:
    """Agregados para snapshot/boletim."""
    if resumo is None or resumo.empty or "rit_0_100" not in resumo.columns:
        return {"disponivel": False, "markdown": "", "top": [], "faixas": {}}

    df = resumo.copy()
    df["_rit"] = pd.to_numeric(df["rit_0_100"], errors="coerce")
    n = len(df)
    faixas = (
        df["rit_faixa"].astype(str).str.lower().value_counts().to_dict()
        if "rit_faixa" in df.columns
        else {}
    )
    crit = (
        int(df["rit_faixa"].astype(str).str.lower().isin(["vermelha", "roxa"]).sum())
        if "rit_faixa" in df.columns
        else 0
    )
    omit_p = (
        int(df["rit_pressao_omitida_defasagem"].fillna(False).astype(bool).sum())
        if "rit_pressao_omitida_defasagem" in df.columns
        else 0
    )
    med_comp = (
        float(pd.to_numeric(df.get("rit_completude_pct"), errors="coerce").median())
        if "rit_completude_pct" in df.columns
        else None
    )

    top_df = df.dropna(subset=["_rit"]).sort_values("_rit", ascending=False).head(int(top_n))
    top: list[dict[str, Any]] = []
    for _, r in top_df.iterrows():
        top.append(
            {
                "municipio": r.get("municipio"),
                "regional": r.get("regional") or r.get("regional_saude"),
                "rit": float(r["_rit"]),
                "faixa": r.get("rit_faixa"),
                "dominante": r.get("rit_dominio_dominante"),
                "completude": r.get("rit_completude_pct"),
            }
        )

    from sisclima.engines.boletim_el_nino.formatters import (
        bloco_tabela,
        fmt_frac,
        fmt_int,
        fmt_num,
        md_table,
    )

    linhas = [
        [
            str(t.get("municipio") or "—"),
            str(t.get("regional") or "—"),
            fmt_num(t.get("rit"), 0),
            str(t.get("faixa") or "—").title(),
            str(t.get("dominante") or "—"),
        ]
        for t in top
    ]
    tab = ""
    if linhas:
        tab = bloco_tabela(
            "Municípios com maior RIT (Risco Integrado Territorial)",
            md_table(
                ["Município", "Regional", "RIT", "Faixa", "Domínio dominante"],
                linhas,
            ),
            "ARARAS MT/CIEVS-MT — RIT = máximo entre domínios válidos (térmico, ar, hidro, EHF, pressão fresca, fragilidade de rede).",
        )

    if omit_p == 1:
        nota_def = (
            f" Pressão assistencial omitida por defasagem em {fmt_int(omit_p)} município "
            f"(limite {MAX_IDADE_PRESSAO_DIAS} dias) — não eleva o RIT."
        )
    elif omit_p > 1:
        nota_def = (
            f" Pressão assistencial omitida por defasagem em {fmt_int(omit_p)} municípios "
            f"(limite {MAX_IDADE_PRESSAO_DIAS} dias) — não eleva o RIT."
        )
    else:
        nota_def = ""

    irm_med = None
    if "indice_resiliencia_municipal_0_100" in df.columns:
        irm_s = pd.to_numeric(df["indice_resiliencia_municipal_0_100"], errors="coerce")
        if irm_s.notna().any():
            irm_med = float(irm_s.median())
    nota_irm = (
        f" IRM mediano (capacidade CNES): {fmt_num(irm_med, 0)} — no RIT entra só a fragilidade (100−IRM)."
        if irm_med is not None
        else ""
    )

    md = f"""### RIT multirisco (observado)

**RIT** = Risco Integrado Territorial (0–100): leitura **observada multidomínio** na rodada.  
**Não** substitui a projeção ~7 dias (térmica) nem a classe ARARAS operacional.

| RIT (faixa vermelha/roxa) | Completude mediana | Domínios |
| --- | --- | --- |
| **{fmt_frac(crit, n)}** | {fmt_num(med_comp, 0, '%') if med_comp is not None else '—'} | térmico · ar/PM2,5 · hidro · EHF · pressão (se fresca) · fragilidade de rede |

{tab}

> RIT = observado multidomínio; projeção ~7d = térmica. Composição: máximo entre domínios válidos.{nota_def}{nota_irm}
"""
    return {
        "disponivel": True,
        "markdown": md,
        "top": top,
        "faixas": faixas,
        "n_critico": crit,
        "n": n,
        "completude_mediana": med_comp,
        "n_pressao_omitida": omit_p,
        "irm_mediana": irm_med,
        "card_md": (
            f"| RIT MULTIRISCO | MODELO ~7 DIAS |\n"
            f"| --- | --- |\n"
            f"| **{fmt_int(crit)}/{fmt_int(n)}** faixa vermelha ou roxa | classe projetada **térmica** |\n"
            f"| Observado (máx. entre 6 domínios, incl. rede) | Não incorpora IRM como elevador — só fragilidade |"
        ),
    }


def documentacao_rit_md() -> str:
    """Quadro metodológico público para o boletim."""
    from sisclima.engines.boletim_el_nino.formatters import bloco_tabela, md_table

    tab = bloco_tabela(
        "Componentes do RIT (Risco Integrado Territorial)",
        md_table(
            ["Domínio", "Variável principal", "Regra v1"],
            [
                ["Térmico atual", "Classe ARARAS / UTCI / Tmáx do dia", "Estágio → 0–100 (passo 25) ou limiares UTCI/Tmáx"],
                ["Ar / fumaça", "PM2,5 (µg/m³)", "≥25 → 50; ≥50 → 75; ≥75 → 100"],
                ["Hidrologia", "nível alerta hidro / situação", "Mapeamento de estágio ou situação seca/cheia"],
                ["EHF observado", "ehf_adaptado / EHF", ">0 → ≥70; valores altos → 85–100"],
                ["Pressão assistencial", "indice_pressao_saude", "0–100 se carga ≤14 dias; senão omitido"],
                ["Fragilidade de rede", "100 − IRM (CNES)", "Capacidade IRM alta → fragilidade baixa; IRM nulo → domínio omitido"],
            ],
        ),
        "Elaboração CIEVS-MT/ARARAS MT. ADR-RIT-multirisco.",
    )
    return f"""### Como o RIT é calculado

O **RIT (Risco Integrado Territorial)** é um índice **observado** na rodada (0–100), paralelo à projeção térmica ~7 dias.

{tab}

**Composição:** máximo entre os domínios válidos (sem soma). Domínios ausentes, pressão defasada (>14 dias) ou IRM nulo (completude < 40% / CNES off) são omitidos e reduzem a completude.

**IRM (capacidade):** `indice_resiliencia_municipal_0_100` é produto próprio da Sala (alto = melhor rede). No RIT entra **só o inverso** (`rit_score_rede`). Alta capacidade **não** eleva o RIT.

**Faixas:** 0–24 verde; 25–49 amarela; 50–69 laranja; 70–84 vermelha; 85–100 roxa.

**Fora do RIT v1 como elevadores:** vulnerabilidade cadastral (idosos, gestantes, asma, povos tradicionais) — narrativa/prioridade apenas. A projeção ~7 dias permanece térmica e **não** usa o RIT.
"""
