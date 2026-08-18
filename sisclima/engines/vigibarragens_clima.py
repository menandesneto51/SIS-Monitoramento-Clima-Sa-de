# -*- coding: utf-8 -*-
"""Cruza territórios do Vigibarragens com cenário climático municipal.

Não prescreve fármaco. Orienta articulação (SESAI/DSEI, APS rural, Defesa Civil).
Distância ao eixo Manso–Cuiabá ≠ cota de inundação.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.vigibarragens import persistir

log = get_logger(__name__)

CENARIOS_RESP = {"queimadas_fumaca", "baixa_umidade"}
CENARIOS_HIDRO = {"seca_estiagem"}
CENARIOS_ENCH = {"chuva_enchente", "tempestade_vendaval"}
CENARIOS_CALOR = {"onda_calor"}
CENARIOS_VET = {"pos_chuva_vetores"}


def _ativos(row: pd.Series | dict[str, Any]) -> set[str]:
    bruto = str(row.get("cenarios_ativos") or "")
    nomes = {c.strip() for c in bruto.split(",") if c.strip()}
    dom = str(row.get("cenario_dominante") or "").strip()
    if dom:
        nomes.add(dom)
    return nomes


def _tem(row, col: str) -> bool:
    try:
        return float(pd.to_numeric(row.get(col), errors="coerce") or 0) > 0
    except Exception:
        return False


def acoes_territoriais(row: pd.Series | dict[str, Any]) -> list[dict[str, str]]:
    """Itens do plano 24h/72h/7d conforme grupos presentes × cenário ativo."""
    ativo = _ativos(row)
    out: list[dict[str, str]] = []

    def add(horizonte: str, acao: str, publico: str) -> None:
        out.append({"horizonte": horizonte, "acao": acao, "publico": publico})

    if _tem(row, "n_aldeias") or _tem(row, "n_terras_indigenas"):
        add(
            "0-24h",
            "Articular SESAI/DSEI e CR-FUNAI: não separar famílias; comunicar em língua; "
            "confirmar aldeias no território e pontos de água/energia.",
            "sesai_dsei",
        )
        if ativo & CENARIOS_RESP:
            add(
                "0-24h",
                "Aldeias: reduzir exposição à fumaça (ambiente protegido/PFF2 conforme IQA); "
                "busca de idosos, crianças e crônicos respiratórios com o DSEI — não substituir a APS municipal.",
                "sesai_dsei",
            )
        if ativo & CENARIOS_HIDRO:
            add(
                "24-72h",
                "Aldeias: água segura na aldeia (Vigiagua + DSEI); hipoclorito e continuidade de crônicos.",
                "visa",
            )
        if ativo & CENARIOS_CALOR:
            add(
                "0-24h",
                "Aldeias: hidratação, sombra e proteção de idosos no calor; evitar deslocamentos longos nas horas críticas.",
                "sesai_dsei",
            )
        if ativo & CENARIOS_ENCH:
            add(
                "0-24h",
                "Aldeias em área de cheia: plano de retirada com DSEI/Defesa Civil. "
                "Não usar distância ao eixo de barragem como cota de inundação (ZAS/ZSS pública incompleta).",
                "defesa_civil",
            )

    if _tem(row, "n_quilombos"):
        add(
            "24-72h",
            "Quilombos certificados (Palmares): visita APS rural; continuidade de crônicos e hipertensos; "
            "acessibilidade da comunidade (estrada/energia).",
            "aps",
        )
        if ativo & CENARIOS_HIDRO:
            add("24-72h", "Quilombos: água segura e hipoclorito; checar cisternas/poços com Vigiagua.", "visa")
        if ativo & CENARIOS_RESP:
            add("0-24h", "Quilombos: atenção respiratória na fumaça/baixa umidade; orientar ambiente protegido.", "aps")

    if _tem(row, "n_assentamentos"):
        fam = row.get("familias_assentamentos")
        fam_txt = f" (~{int(float(fam)):,} famílias)".replace(",", ".") if pd.notna(pd.to_numeric(fam, errors="coerce")) and float(fam) > 0 else ""
        add(
            "24-72h",
            f"Assentamentos INCRA{fam_txt}: trabalhadores rurais — hidratação, proteção na fumaça/calor, "
            "e ponto de água segura. Isolamento viário pode atrasar busca ativa.",
            "aps",
        )
        if ativo & CENARIOS_ENCH:
            add("0-24h", "Assentamentos: mapear famílias isoladas e desalojados; kit calamidade só se houver deslocados.", "defesa_civil")

    if _tem(row, "n_barragens_dpa_alto") or _tem(row, "tem_zas_barragem"):
        popj = row.get("pop_jusante_sigbm")
        extra = ""
        if pd.notna(pd.to_numeric(popj, errors="coerce")) and float(popj) > 0:
            extra = f" SIGBM declara ~{int(float(popj)):,} pessoas a jusante.".replace(",", ".")
        add(
            "0-24h" if ativo & CENARIOS_ENCH else "3-7d",
            "Barragens com DPA alto: articular Defesa Civil/PAE e vigilância. "
            "Hospitais em várzea não provam inundação (dependência circular). "
            f"Não tratar distância ao eixo Manso–Cuiabá como polígono de mancha.{extra}",
            "defesa_civil",
        )
    return out


def texto_cuidados(row: pd.Series | dict[str, Any]) -> str:
    acoes = acoes_territoriais(row)
    if not acoes:
        return ""
    seen: list[str] = []
    for a in acoes:
        txt = str(a.get("acao") or "").strip()
        if txt and txt not in seen:
            seen.append(txt)
    return " | ".join(seen[:4])


def extrair_territorio(row: pd.Series | dict[str, Any] | None) -> dict[str, Any]:
    row = row if row is not None else {}
    def n(col: str) -> int:
        return int(pd.to_numeric(row.get(col), errors="coerce") or 0)

    return {
        "n_aldeias": n("n_aldeias"),
        "n_quilombos": n("n_quilombos"),
        "n_assentamentos": n("n_assentamentos"),
        "n_terras_indigenas": n("n_terras_indigenas"),
        "familias_assentamentos": n("familias_assentamentos"),
        "n_barragens_dpa_alto": n("n_barragens_dpa_alto"),
        "n_territorios_tradicionais": n("n_territorios_tradicionais"),
        "cenario_dominante": str(row.get("cenario_dominante") or "").strip(),
        "cuidados_territoriais": str(row.get("cuidados_territoriais") or "").strip(),
    }


def sintese_territorial(df: pd.DataFrame | None = None, n_top: int = 6) -> dict[str, Any]:
    """Totais e municípios-prioridade para boletim SES/regional."""
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        try:
            df = read_table("prontidao_municipal")
        except Exception:
            df = pd.DataFrame()
        if df is None or df.empty:
            try:
                df = read_table("resumo_municipal_atual")
            except Exception:
                df = pd.DataFrame()
    if df is None or df.empty:
        return {"ok": False, "texto": "Cadastro Vigibarragens ainda não cruzado neste recorte."}
    work = df.copy()
    for c in (
        "n_aldeias",
        "n_quilombos",
        "n_assentamentos",
        "n_terras_indigenas",
        "n_barragens_dpa_alto",
        "n_territorios_tradicionais",
        "familias_assentamentos",
    ):
        if c in work.columns:
            work[c] = pd.to_numeric(work[c], errors="coerce").fillna(0)
        else:
            work[c] = 0
    n_mun = int((work["n_territorios_tradicionais"] > 0).sum())
    n_dpa = int((work["n_barragens_dpa_alto"] > 0).sum())
    tot = {
        "n_mun_territorio": n_mun,
        "n_mun_dpa": n_dpa,
        "n_aldeias": int(work["n_aldeias"].sum()),
        "n_quilombos": int(work["n_quilombos"].sum()),
        "n_assentamentos": int(work["n_assentamentos"].sum()),
        "n_terras_indigenas": int(work["n_terras_indigenas"].sum()),
        "familias_assentamentos": int(work["familias_assentamentos"].sum()),
        "n_barragens_dpa_alto": int(work["n_barragens_dpa_alto"].sum()),
    }
    rank = work[(work["n_territorios_tradicionais"] > 0) | (work["n_barragens_dpa_alto"] > 0)].copy()
    if "municipio" not in rank.columns or rank["municipio"].isna().all():
        try:
            from sisclima.ingestion.ibge_municipios import catalogo_municipios_mt

            cat = catalogo_municipios_mt()[["cod_ibge", "municipio"]].drop_duplicates("cod_ibge")
            rank = rank.drop(columns=["municipio"], errors="ignore").merge(cat, on="cod_ibge", how="left")
        except Exception:
            pass
    if "intensidade_dominante" in rank.columns:
        rank["_ord"] = pd.to_numeric(rank["intensidade_dominante"], errors="coerce").fillna(0)
    elif "n_territorios_tradicionais" in rank.columns:
        rank["_ord"] = rank["n_territorios_tradicionais"]
    else:
        rank["_ord"] = 0
    top = rank.sort_values(["_ord", "n_aldeias"], ascending=False).head(n_top)
    linhas = []
    for _, r in top.iterrows():
        linhas.append(
            f"{r.get('municipio')}: {int(r.get('n_aldeias') or 0)} aldeias, "
            f"{int(r.get('n_quilombos') or 0)} quilombos, {int(r.get('n_assentamentos') or 0)} assent. "
            f"({r.get('cenario_dominante') or '—'})"
        )
    texto = (
        f"{tot['n_mun_territorio']} município(s) com território tradicional "
        f"({tot['n_aldeias']} aldeias FUNAI, {tot['n_quilombos']} quilombos Palmares, "
        f"{tot['n_assentamentos']} assentamentos INCRA, ~{tot['familias_assentamentos']:,} famílias). ".replace(",", ".")
        + f"{tot['n_mun_dpa']} município(s) com barragem de DPA alto. "
        "Articular SESAI/DSEI, APS rural e Defesa Civil conforme o cenário climático. "
        "Distância ao eixo de barragem não é cota de inundação."
    )
    return {"ok": True, **tot, "top": linhas, "texto": texto}


def texto_orientacao_municipal(row: pd.Series | dict[str, Any]) -> str:
    t = extrair_territorio(row)
    if t["n_territorios_tradicionais"] <= 0 and t["n_barragens_dpa_alto"] <= 0:
        return "Sem território tradicional ou DPA alto no cadastro Vigibarragens deste município."
    partes = [
        f"{t['n_aldeias']} aldeia(s)",
        f"{t['n_quilombos']} quilombo(s)",
        f"{t['n_assentamentos']} assentamento(s)",
    ]
    if t["n_barragens_dpa_alto"]:
        partes.append(f"{t['n_barragens_dpa_alto']} barragem(ns) DPA alto")
    base = "Cadastro: " + ", ".join(partes) + "."
    extra = t["cuidados_territoriais"] or texto_cuidados(row)
    return f"{base} {extra}".strip()


def carregar_municipal(force: bool = False) -> pd.DataFrame:
    if not force and table_exists("vigibarragens_municipal"):
        df = read_table("vigibarragens_municipal")
        if df is not None and not df.empty:
            df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            return df
    out = persistir()
    mun = out.get("municipal_df")
    return mun if isinstance(mun, pd.DataFrame) else pd.DataFrame()


def anexar_territorios(df: pd.DataFrame) -> pd.DataFrame:
    """Injeta contagens Vigibarragens e texto de cuidados no recorte municipal."""
    mun = carregar_municipal(force=False)
    if mun is None or mun.empty or df is None or df.empty or "cod_ibge" not in df.columns:
        return df
    out = df.copy()
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    cols = [
        c
        for c in [
            "cod_ibge",
            "n_aldeias",
            "n_quilombos",
            "n_assentamentos",
            "n_terras_indigenas",
            "familias_assentamentos",
            "moradores_quilombo",
            "n_barragens",
            "n_barragens_dpa_alto",
            "pop_jusante_sigbm",
            "n_territorios_tradicionais",
            "tem_territorio_tradicional",
            "tem_zas_barragem",
        ]
        if c in mun.columns
    ]
    add = mun[cols].drop_duplicates("cod_ibge")
    for c in add.columns:
        if c != "cod_ibge" and c in out.columns:
            out = out.drop(columns=[c])
    out = out.merge(add, on="cod_ibge", how="left")
    for c in cols:
        if c != "cod_ibge" and c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    out["cuidados_territoriais"] = out.apply(texto_cuidados, axis=1)
    return out
