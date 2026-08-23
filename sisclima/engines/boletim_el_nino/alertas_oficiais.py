# -*- coding: utf-8 -*-
"""Alertas oficiais INMET, CEMADEN e síntese TITAN para o boletim."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from sisclima.core.recorte_mt import RECORTE_NOME, RECORTE_UF
from sisclima.core.logging_utils import get_logger
from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL, SELPREV, SELOBS
from sisclima.engines.boletim_el_nino.formatters import fmt_int, md_table
from sisclima.engines.boletim_el_nino.inmet_section import _norm_severidade
from sisclima.engines.boletim_el_nino.referencias import cite
from sisclima.ingestion.cemaden import fetch_cemaden_alerts, normalize_cemaden_alerts
from sisclima.ingestion.inmet import fetch_inmet_alerts, normalize_inmet_alerts

log = get_logger(__name__)


def _parse_dt(val: Any) -> datetime | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    ts = pd.to_datetime(val, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def _classificar_vigencia(
    df: pd.DataFrame,
    *,
    semana_inicio: date,
    semana_fim: date,
    agora: datetime,
) -> pd.DataFrame:
    """Vigente somente se inicio e fim existirem e agora ∈ [inicio, fim]."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ini_col = next((c for c in ("inicio_vigencia", "inicio") if c in out.columns), None)
    fim_col = next((c for c in ("fim_vigencia", "fim") if c in out.columns), None)

    def _rotulo(row: pd.Series) -> str:
        if not ini_col or not fim_col:
            return "vigencia_nao_validada"
        ini = _parse_dt(row.get(ini_col))
        fim = _parse_dt(row.get(fim_col))
        if ini is None or fim is None:
            return "vigencia_nao_validada"
        ini_d, fim_d = ini.date(), fim.date()
        if ini_d > semana_fim or fim_d < semana_inicio:
            return "fora_semana"
        if agora < ini:
            return "futuro"
        if agora > fim:
            return "encerrado"
        return "vigente"

    out["classe_vigencia"] = out.apply(_rotulo, axis=1)
    return out


def _tabela_inmet(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Nenhum aviso na categoria._"
    from sisclima.engines.boletim_el_nino.formatters import fmt_date_pt

    rows: list[list[str]] = []
    for _, row in df.iterrows():
        ini = row.get("inicio_vigencia")
        fim = row.get("fim_vigencia")
        rows.append(
            [
                str(row.get("evento") or "—"),
                _norm_severidade(str(row.get("nivel_alerta") or row.get("severidade") or "")),
                fmt_date_pt(ini) if pd.notna(ini) else "não informado",
                fmt_date_pt(fim) if pd.notna(fim) else "não informado",
                str(row.get("area_mt") or row.get("municipio") or row.get("area_abrangencia") or "—"),
            ]
        )
    return md_table(
        ["Fenômeno", "Severidade", "Início da validade", "Fim da validade", "Área em Mato Grosso"],
        rows,
    )


def _tabela_cemaden(df: pd.DataFrame) -> str:
    if df.empty:
        return "_Nenhum alerta aberto do CEMADEN para Mato Grosso nesta consulta._"
    rows: list[list[str]] = []
    for _, row in df.iterrows():
        rows.append(
            [
                str(row.get("evento") or "—"),
                str(row.get("nivel_alerta") or row.get("nivel") or "—"),
                str(row.get("tipo_risco") or "—"),
                str(row.get("data") or "—")[:16],
                str(row.get("municipio") or "—"),
                str(row.get("status") or "aberto"),
            ]
        )
    return md_table(
        ["Evento", "Nível", "Tipo", "Emissão/atualização", "Município", "Status"],
        rows,
    )


def _rotulo_nivel_alerta(k: Any) -> str:
    s = str(k or "").strip().lower()
    mapa = {
        "verde": "verde",
        "amarela": "amarela",
        "laranja": "laranja",
        "vermelha": "vermelha",
        "roxa": "roxa",
        "cinza": "cinza",
    }
    return mapa.get(s, str(k))


def _sintese_titan(titan: pd.DataFrame | None) -> dict[str, Any]:
    if titan is None or titan.empty:
        return {"disponivel": False, "resumo_md": INDISPONIVEL}
    niv = titan["nivel_alerta_integrado"].value_counts().to_dict() if "nivel_alerta_integrado" in titan.columns else {}
    partes_niv = [f"{_rotulo_nivel_alerta(k)}: {fmt_int(v)}" for k, v in sorted(niv.items(), key=lambda kv: str(kv[0]))]
    linhas = [
        f"- Municípios no recorte: **{fmt_int(len(titan))}**",
        f"- Distribuição da classificação integrada: {'; '.join(partes_niv) or '—'}",
    ]
    return {"disponivel": True, "resumo_md": "\n".join(linhas), "niveis": niv, "componentes": {}}


def build_alertas_oficiais(
    semana: dict[str, Any],
    *,
    hoje: date | None = None,
    uf: str | None = None,
    consulta_em: datetime | None = None,
    inmet_db: pd.DataFrame | None = None,
    cemaden_db: pd.DataFrame | None = None,
    titan_db: pd.DataFrame | None = None,
    fetch_live: bool = True,
) -> dict[str, Any]:
    """Monta pacote de alertas oficiais para a semana do relatório."""
    ts = consulta_em or datetime.now()
    consulta_pt = ts.strftime("%d/%m/%Y às %Hh%M")
    ref = hoje or date.today()
    uf = RECORTE_UF
    sem_ini = date.fromisoformat(str(semana.get("inicio")))
    sem_fim = date.fromisoformat(str(semana.get("fim")))

    fonte_inmet = "indisponivel"
    inmet = pd.DataFrame()
    fetch_inmet_ok = False
    if fetch_live:
        try:
            inmet = normalize_inmet_alerts(fetch_inmet_alerts())
            fetch_inmet_ok = True
            fonte_inmet = "live"
        except Exception as exc:  # noqa: BLE001
            log.warning("Fetch INMET live falhou: %s", exc)
            fetch_inmet_ok = False
    if inmet.empty and inmet_db is not None and not inmet_db.empty:
        inmet = inmet_db.copy()
        fonte_inmet = "base_local"

    fonte_cemaden = "indisponivel"
    cemaden = pd.DataFrame()
    if fetch_live:
        try:
            cemaden = normalize_cemaden_alerts(fetch_cemaden_alerts(uf))
            fonte_cemaden = "live"
        except Exception as exc:  # noqa: BLE001
            log.warning("Fetch CEMADEN live falhou: %s", exc)
    if cemaden.empty and cemaden_db is not None and not cemaden_db.empty:
        cemaden = cemaden_db.copy()
        fonte_cemaden = "base_local"

    inmet_sem = _classificar_vigencia(inmet, semana_inicio=sem_ini, semana_fim=sem_fim, agora=ts)
    vigentes = inmet_sem[inmet_sem["classe_vigencia"] == "vigente"] if not inmet_sem.empty else pd.DataFrame()
    futuros = inmet_sem[inmet_sem["classe_vigencia"] == "futuro"] if not inmet_sem.empty else pd.DataFrame()
    nao_validados = inmet_sem[inmet_sem["classe_vigencia"] == "vigencia_nao_validada"] if not inmet_sem.empty else pd.DataFrame()

    titan = _sintese_titan(titan_db)

    cite_inmet = cite("inmet_alertas")
    cite_cem = cite("cemaden_alertas")
    cite_araras = cite("araras_mt")

    resumo_clim = []
    if not fetch_inmet_ok and inmet.empty:
        resumo_clim.append(
            "Consulta aos alertas do Instituto Nacional de Meteorologia (INMET) **indisponível nesta rodada**. "
            "A ausência de registros **não** foi convertida em zero alertas."
        )
    elif not vigentes.empty:
        n_v = len(vigentes)
        resumo_clim.append(
            f"**Situação climática de referência (avisos vigentes):** "
            f"{n_v} {'aviso' if n_v == 1 else 'avisos'} INMET "
            f"com validade contendo o horário de emissão deste relatório {cite_inmet}."
        )
    elif not inmet.empty:
        n_i = len(inmet)
        resumo_clim.append(
            f"Não há avisos INMET com validade confirmada no horário da consulta; "
            f"{n_i} {'aviso' if n_i == 1 else 'avisos'} recuperado{'s' if n_i != 1 else ''} {cite_inmet}."
        )
        if not nao_validados.empty:
            n_nv = len(nao_validados)
            resumo_clim.append(
                f"Vigência do alerta não validada em {n_nv} "
                f"{'registro' if n_nv == 1 else 'registros'} — "
                f"não classificado{'s' if n_nv != 1 else ''} como alerta ativo."
            )
    else:
        resumo_clim.append(
            f"Consulta INMET concluída sem avisos vigentes para {uf} no horário da emissão {cite_inmet}."
        )

    if not futuros.empty:
        n_f = len(futuros)
        resumo_clim.append(
            f"**Projeção operacional (avisos futuros na semana):** "
            f"{n_f} {'aviso' if n_f == 1 else 'avisos'} com início "
            f"posterior à data de referência — leitura de tendência imediata {SELPREV} {cite_inmet}."
        )

    if not cemaden.empty:
        n_c = len(cemaden)
        resumo_clim.append(
            f"**CEMADEN:** {n_c} {'alerta' if n_c == 1 else 'alertas'} aberto{'s' if n_c != 1 else ''} em {uf} {cite_cem}."
        )
    else:
        resumo_clim.append(
            f"**CEMADEN:** nenhum alerta aberto em {uf} na consulta {cite_cem}."
        )

    if titan.get("disponivel"):
        resumo_clim.append(
            f"**Síntese integrada de alertas:** classificação municipal disponível {cite_araras}."
        )

    return {
        "disponivel": not (inmet.empty and cemaden.empty and not titan.get("disponivel")),
        "consulta_em": consulta_pt,
        "semana": semana.get("rotulo"),
        "recorte_uf": RECORTE_UF,
        "recorte_nome": RECORTE_NOME,
        "fonte_inmet": fonte_inmet,
        "fonte_cemaden": fonte_cemaden,
        "n_inmet_total": len(inmet),
        "n_inmet_vigentes": len(vigentes),
        "n_inmet_futuros": len(futuros),
        "n_cemaden": len(cemaden),
        "resumo_climatico_md": "\n\n".join(resumo_clim),
        "inmet_vigentes_md": _tabela_inmet(vigentes),
        "inmet_futuros_md": _tabela_inmet(futuros),
        "cemaden_md": _tabela_cemaden(cemaden),
        "titan": titan,
        "titan_md": titan.get("resumo_md", INDISPONIVEL),
        "citacao_inmet": cite_inmet,
        "citacao_cemaden": cite_cem,
    }
