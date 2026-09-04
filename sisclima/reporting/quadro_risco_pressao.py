# -*- coding: utf-8 -*-
"""Snapshot estadual de risco operacional e pressão assistencial."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

_NIVEL_ORDEM = ["roxa", "vermelha", "laranja", "amarela", "verde", "cinza"]
_SEMAFORO_ORDEM = ["vermelha", "amarela", "verde"]


def _num(v: Any) -> float | None:
    try:
        x = float(pd.to_numeric(v, errors="coerce"))
    except (TypeError, ValueError):
        return None
    if pd.isna(x):
        return None
    return float(x)


def _br(v: float | None, nd: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{nd}f}".replace(".", ",")


def _tem_indice_pressao(df: pd.DataFrame) -> bool:
    if df is None or df.empty or "indice_pressao_saude" not in df.columns:
        return False
    return pd.to_numeric(df["indice_pressao_saude"], errors="coerce").notna().any()


def _leitos_por_ibge() -> dict[str, tuple[float, float]]:
    """cod_ibge → (leitos_existentes, leitos_ocupados) a partir do IndicaSUS municipal."""
    out: dict[str, tuple[float, float]] = {}
    try:
        from sisclima.core.db import read_table, table_exists

        if not table_exists("hospital_ocupacao_municipio"):
            return out
        mun = read_table("hospital_ocupacao_municipio")
        if mun is None or mun.empty or "cod_ibge" not in mun.columns:
            return out
        for _, row in mun.iterrows():
            ibge = str(row.get("cod_ibge") or "").strip()
            if not ibge or ibge in ("nan", "None"):
                continue
            lt = _num(row.get("leitos_existentes"))
            lo = _num(row.get("leitos_ocupados"))
            if lt is None or lt <= 0:
                continue
            out[ibge] = (float(lt), float(lo or 0.0))
    except Exception:
        return out
    return out


def agregar_ocupacao_por_regional(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Termômetro assistencial IndicaSUS por regional de saúde (ponderado por leitos).

    Municípios SEM_LEITOS contam na cobertura, mas não entram no % ponderado.
    Sem tabela de leitos, usa média simples dos % municipais disponíveis.
    """
    if df is None or df.empty or "regional_saude" not in df.columns:
        return []

    beds = _leitos_por_ibge()
    fonte = (
        df["fonte_ocupacao"].astype(str)
        if "fonte_ocupacao" in df.columns
        else pd.Series([""] * len(df), index=df.index)
    )
    ocup = (
        pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce")
        if "ocupacao_leitos_pct" in df.columns
        else pd.Series(dtype=float, index=df.index)
    )
    work = df.assign(
        _reg=df["regional_saude"].fillna("—").astype(str).str.strip().replace("", "—"),
        _fonte=fonte,
        _ocup=ocup,
    )

    rows: list[dict[str, Any]] = []
    for reg, g in work.groupby("_reg", sort=True):
        n = int(len(g))
        n_sem = int(g["_fonte"].str.contains("SEM_LEITOS", case=False, na=False).sum())
        if n_sem == 0 and g["_ocup"].isna().any() and g["_fonte"].eq("").all():
            n_sem = int(g["_ocup"].isna().sum())
        n_com = int(g["_ocup"].notna().sum())

        leitos_tot = 0.0
        leitos_oc = 0.0
        n_com_leitos = 0
        for _, row in g.iterrows():
            ibge = str(row.get("cod_ibge") or "").strip()
            pair = beds.get(ibge)
            if not pair:
                continue
            lt, lo = pair
            leitos_tot += lt
            leitos_oc += lo
            n_com_leitos += 1

        if leitos_tot > 0:
            ocup_pond = 100.0 * leitos_oc / leitos_tot
            modo = "ponderada_leitos"
        elif g["_ocup"].notna().any():
            ocup_pond = float(g["_ocup"].mean())
            leitos_tot = None
            leitos_oc = None
            modo = "media_municipal"
        else:
            ocup_pond = None
            leitos_tot = None
            leitos_oc = None
            modo = "sem_dado"

        rows.append(
            {
                "regional": str(reg),
                "n_municipios": n,
                "n_com_taxa": n_com,
                "n_sem_leitos": n_sem,
                "n_com_leitos_indicasus": n_com_leitos,
                "leitos_total": leitos_tot,
                "leitos_ocupados": leitos_oc,
                "ocupacao_ponderada": ocup_pond,
                "ocupacao_ponderada_txt": _br(ocup_pond),
                "modo": modo,
            }
        )

    rows.sort(
        key=lambda r: (
            r.get("ocupacao_ponderada") is None,
            -(r.get("ocupacao_ponderada") or -1.0),
            str(r.get("regional") or ""),
        )
    )
    return rows


def quadro_risco_pressao(resumo: pd.DataFrame | None = None) -> dict[str, Any]:
    """Registro estadual: distribuição de risco + pressão assistencial + ranking."""
    from_db = resumo is None
    if resumo is None:
        from sisclima.core.db import read_table

        resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty:
        return {"disponivel": False, "motivo": "Resumo municipal ausente nesta rodada."}

    df = resumo.copy()
    if not _tem_indice_pressao(df):
        try:
            from sisclima.engines.indice_pressao_saude import persist_indice_pressao_resumo

            df = persist_indice_pressao_resumo(df, write=from_db)
        except Exception:
            pass
    n = len(df)
    dist_nivel: dict[str, int] = {}
    if "nivel" in df.columns:
        dist_nivel = (
            df["nivel"].astype(str).str.lower().str.strip().value_counts().to_dict()
        )
    dist_nivel_txt = (
        " · ".join(f"{k} {int(dist_nivel.get(k, 0))}" for k in _NIVEL_ORDEM if dist_nivel.get(k))
        or "—"
    )

    pressao = (
        pd.to_numeric(df["indice_pressao_saude"], errors="coerce")
        if "indice_pressao_saude" in df.columns
        else pd.Series(dtype=float)
    )
    ocup = (
        pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce")
        if "ocupacao_leitos_pct" in df.columns
        else pd.Series(dtype=float)
    )
    fonte_ocup = (
        df["fonte_ocupacao"].astype(str)
        if "fonte_ocupacao" in df.columns
        else pd.Series(dtype=str)
    )
    n_ocup_real = int(fonte_ocup.str.contains("TEMPO_REAL", case=False, na=False).sum()) if not fonte_ocup.empty else int(ocup.notna().sum())
    n_sem_leitos = int(fonte_ocup.str.contains("SEM_LEITOS", case=False, na=False).sum()) if not fonte_ocup.empty else int(ocup.isna().sum())

    sis_sol = (
        pd.to_numeric(df["kpi_sisreg_solicitacoes"], errors="coerce")
        if "kpi_sisreg_solicitacoes" in df.columns
        else pd.Series(dtype=float)
    )
    if "kpi_sisreg_disponivel" in df.columns:
        n_sisreg = int(df["kpi_sisreg_disponivel"].fillna(False).astype(bool).sum())
    else:
        n_sisreg = int(sis_sol.notna().sum())

    calor = (
        pd.to_numeric(df["pressao_calor_pct"], errors="coerce")
        if "pressao_calor_pct" in df.columns
        else pd.Series(dtype=float)
    )
    dist_semaforo: dict[str, int] = {}
    if "semaforo_pressao" in df.columns:
        dist_semaforo = (
            df["semaforo_pressao"].astype(str).str.lower().str.strip().value_counts().to_dict()
        )
    semaforo_txt = (
        " · ".join(
            f"{k} {int(dist_semaforo.get(k, 0))}" for k in _SEMAFORO_ORDEM if dist_semaforo.get(k)
        )
        or "—"
    )

    rank = df["nivel"].map(lambda x: STAGE_ORDER.get(str(x).lower().strip(), -1)) if "nivel" in df.columns else pd.Series([-1] * n)
    df = df.assign(_rank=rank)
    if pressao.notna().any():
        df["_pressao"] = pd.to_numeric(df["indice_pressao_saude"], errors="coerce")
    elif calor.notna().any():
        df["_pressao"] = pd.to_numeric(df["pressao_calor_pct"], errors="coerce")
    elif ocup.notna().any():
        df["_pressao"] = pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce")
    else:
        df["_pressao"] = 0.0
    top = df.sort_values(["_rank", "_pressao"], ascending=False).head(10)
    registros: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        registros.append(
            {
                "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                "cod_ibge": str(row.get("cod_ibge") or ""),
                "regional": str(row.get("regional_saude") or "—"),
                "nivel": str(row.get("nivel") or "cinza").lower().strip(),
                "indice_pressao_saude": _num(row.get("indice_pressao_saude")),
                "semaforo_pressao": str(row.get("semaforo_pressao") or "—").lower().strip(),
                "ocupacao_leitos_pct": _num(row.get("ocupacao_leitos_pct")),
                "fonte_ocupacao": str(row.get("fonte_ocupacao") or ""),
                "kpi_sisreg_solicitacoes": _num(row.get("kpi_sisreg_solicitacoes")),
                "kpi_sisreg_semaforo": str(row.get("kpi_sisreg_semaforo") or "—").lower().strip(),
                "pressao_calor_pct": _num(row.get("pressao_calor_pct")),
            }
        )

    # Totais IndicaSUS ponderados (filtros SIEGES) + tops para boletim/relatório
    leitos_total = None
    leitos_ocupados = None
    ocupacao_ponderada = None
    unidades_n = None
    try:
        from sisclima.core.db import read_table, table_exists

        if table_exists("hospital_ocupacao_estado"):
            est = read_table("hospital_ocupacao_estado")
            if est is not None and not est.empty:
                row = est.iloc[-1]
                leitos_total = _num(row.get("leitos_existentes"))
                leitos_ocupados = _num(row.get("leitos_ocupados"))
                ocupacao_ponderada = _num(row.get("ocupacao_pct"))
                unidades_n = _num(row.get("unidades_com_localidade")) or _num(row.get("unidades"))
        if (leitos_total is None or leitos_ocupados is None) and table_exists("hospital_ocupacao_municipio"):
            mun = read_table("hospital_ocupacao_municipio")
            if mun is not None and not mun.empty:
                leitos_total = float(pd.to_numeric(mun.get("leitos_existentes"), errors="coerce").fillna(0).sum())
                leitos_ocupados = float(pd.to_numeric(mun.get("leitos_ocupados"), errors="coerce").fillna(0).sum())
                if leitos_total:
                    ocupacao_ponderada = 100.0 * leitos_ocupados / leitos_total
    except Exception:
        pass

    nome_col = next((c for c in ("municipio", "municipio_base") if c in df.columns), None)
    top_ocup: list[dict[str, Any]] = []
    if ocup.notna().any() and nome_col:
        sub = df.loc[ocup.notna(), [nome_col, "cod_ibge", "ocupacao_leitos_pct"]].copy()
        if "kpi_sisreg_solicitacoes" in df.columns:
            sub["kpi_sisreg_solicitacoes"] = sis_sol
        sub = sub.sort_values("ocupacao_leitos_pct", ascending=False).head(10)
        for _, row in sub.iterrows():
            top_ocup.append(
                {
                    "municipio": str(row.get(nome_col) or "—"),
                    "cod_ibge": str(row.get("cod_ibge") or ""),
                    "ocupacao_leitos_pct": _num(row.get("ocupacao_leitos_pct")),
                    "kpi_sisreg_solicitacoes": _num(row.get("kpi_sisreg_solicitacoes")),
                }
            )

    top_sem_sisreg: list[dict[str, Any]] = []
    if nome_col and n_sem_leitos and sis_sol.notna().any():
        sem_mask = fonte_ocup.str.contains("SEM_LEITOS", case=False, na=False) if not fonte_ocup.empty else ocup.isna()
        sub = df.loc[sem_mask].copy()
        sub["_sis"] = sis_sol
        sub = sub.loc[sub["_sis"].notna()].sort_values("_sis", ascending=False).head(10)
        for _, row in sub.iterrows():
            top_sem_sisreg.append(
                {
                    "municipio": str(row.get(nome_col) or "—"),
                    "cod_ibge": str(row.get("cod_ibge") or ""),
                    "kpi_sisreg_solicitacoes": _num(row.get("_sis")),
                    "regional": str(row.get("regional_saude") or "—"),
                }
            )

    return {
        "disponivel": True,
        "n_municipios": n,
        "dist_nivel": {k: int(dist_nivel.get(k, 0)) for k in _NIVEL_ORDEM},
        "dist_nivel_txt": dist_nivel_txt,
        "pressao_media": float(pressao.mean()) if pressao.notna().any() else None,
        "pressao_max": float(pressao.max()) if pressao.notna().any() else None,
        "pressao_n": int(pressao.notna().sum()),
        # Ocupação hospitalar = IndicaSUS (recorte SIEGES)
        "ocupacao_media": float(ocup.mean()) if ocup.notna().any() else None,
        "ocupacao_max": float(ocup.max()) if ocup.notna().any() else None,
        "ocupacao_n": int(ocup.notna().sum()),
        "ocupacao_n_tempo_real": n_ocup_real,
        "ocupacao_n_sem_leitos": n_sem_leitos,
        "ocupacao_ponderada": ocupacao_ponderada,
        "ocupacao_ponderada_txt": _br(ocupacao_ponderada),
        "leitos_total": leitos_total,
        "leitos_ocupados": leitos_ocupados,
        "leitos_total_txt": _br(leitos_total, 0),
        "leitos_ocupados_txt": _br(leitos_ocupados, 0),
        "unidades_n": int(unidades_n) if unidades_n is not None else None,
        "top_ocupacao": top_ocup,
        "top_sem_leitos_sisreg": top_sem_sisreg,
        "ocupacao_por_regional": agregar_ocupacao_por_regional(df),
        # Pressão hospitalar = SISREG (demanda/regulação)
        "sisreg_n": n_sisreg,
        "sisreg_solicitacoes_media": float(sis_sol.mean()) if sis_sol.notna().any() else None,
        "sisreg_solicitacoes_max": float(sis_sol.max()) if sis_sol.notna().any() else None,
        "sisreg_solicitacoes_media_txt": _br(float(sis_sol.mean()) if sis_sol.notna().any() else None, 0),
        "sisreg_solicitacoes_max_txt": _br(float(sis_sol.max()) if sis_sol.notna().any() else None, 0),
        "calor_media": float(calor.mean()) if calor.notna().any() else None,
        "calor_max": float(calor.max()) if calor.notna().any() else None,
        "dist_semaforo": {k: int(dist_semaforo.get(k, 0)) for k in _SEMAFORO_ORDEM},
        "semaforo_txt": semaforo_txt,
        "registros": registros,
        "pressao_media_txt": _br(float(pressao.mean()) if pressao.notna().any() else None),
        "pressao_max_txt": _br(float(pressao.max()) if pressao.notna().any() else None),
        "ocupacao_media_txt": _br(float(ocup.mean()) if ocup.notna().any() else None),
        "ocupacao_max_txt": _br(float(ocup.max()) if ocup.notna().any() else None),
        "calor_media_txt": _br(float(calor.mean()) if calor.notna().any() else None),
        "calor_max_txt": _br(float(calor.max()) if calor.notna().any() else None),
        "nota_separacao": (
            "Ocupação hospitalar (IndicaSUS, filtros SIEGES) ≠ pressão hospitalar (SISREG). "
            "Sem leitos elegíveis no recorte não inventamos %; use SISREG para demanda territorial."
        ),
        "filtros_sieges_txt": (
            "SituacaoAtual≠Bloqueado · Tipo SUS Habilitado/Não Habilitado · "
            "TipoLeito≠Pronto Atendimento · exclusão UPA/PA/unidade mista (lista institucional)"
        ),
    }
