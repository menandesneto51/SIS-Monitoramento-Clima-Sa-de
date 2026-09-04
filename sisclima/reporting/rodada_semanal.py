# -*- coding: utf-8 -*-
"""Export da rodada semanal do boletim — memória para validação projeção × observado."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_OUT_DIR = ROOT / "data" / "output" / "boletim"

_NIVEL_ORDEM = {"verde": 1, "amarela": 2, "laranja": 3, "vermelha": 4, "roxa": 5, "cinza": 0}

# Colunas canônicas do template de monitoramento (consultoria / Sala)
RODADA_COLS = [
    "semana_epidemiologica",
    "data_referencia",
    "cod_ibge",
    "municipio",
    "regional_saude",
    "classe_atual",
    "classe_projetada_7d",
    "tmax",
    "ur_pct",
    "pm25_ugm3",
    "utci_c",
    "focos_calor_7d",
    "iqa_classe",
    "indice_prioridade",
    "faixa_prioridade",
    "determinante_principal",
]


def _nivel(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in {"nan", "none", ""}:
        return ""
    return s


def _pick_proj(row: pd.Series) -> str:
    for c in ("nivel_predicao_7d", "pred_nivel_clima_7d", "nivel_projecao_7d"):
        if c in row.index:
            n = _nivel(row.get(c))
            if n:
                return n
    return ""


def _pick_determinante(row: pd.Series) -> str:
    for c in (
        "risco_predominante",
        "exposicao_principal",
        "determinante",
        "orientacao_prioridade",
        "pilares_prioridade",
    ):
        if c in row.index:
            v = row.get(c)
            if v is not None and str(v).strip() and str(v).lower() not in {"nan", "none"}:
                return str(v).strip()
    return ""


def build_rodada_semanal(
    resumo: pd.DataFrame | None = None,
    *,
    ref: date | None = None,
) -> pd.DataFrame:
    """Uma linha por município: classe atual × projetada + indicadores da rodada."""
    from sisclima.engines.boletim_el_nino.cenario import semana_iso

    if resumo is None:
        from sisclima.core.db import read_table

        resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty:
        return pd.DataFrame(columns=RODADA_COLS)

    hoje = ref or date.today()
    se = semana_iso(hoje)
    df = resumo.copy()
    if "cod_ibge" not in df.columns:
        return pd.DataFrame(columns=RODADA_COLS)

    # Enriquece com predicao_calor se existir e nivel_predicao_7d ausente
    if "nivel_predicao_7d" not in df.columns:
        try:
            from sisclima.core.db import read_table, table_exists

            for tab in ("predicao_calor_7d_municipal_v6", "predicao_municipal_7d"):
                if table_exists(tab):
                    pred = read_table(tab)
                    if pred is not None and not pred.empty and "cod_ibge" in pred.columns:
                        from sisclima.engines.boletim_el_nino.snapshot import merge_predicao_7d

                        df = merge_predicao_7d(df, pred)
                        break
        except Exception as exc:  # noqa: BLE001
            log.debug("Predição auxiliar indisponível para rodada semanal: %s", exc)

    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        ibge = str(row.get("cod_ibge") or "").strip()
        if not ibge or ibge in {"nan", "None"}:
            continue
        ur = row.get("umidade_media") if "umidade_media" in row.index else row.get("umidade")
        focos = (
            row.get("focos_queimadas_7d")
            if "focos_queimadas_7d" in row.index
            else row.get("focos_calor_7d")
        )
        iqa = row.get("iqa_classe") if "iqa_classe" in row.index else row.get("orientacao_mascara_iqa")
        idx = row.get("indice_prioridade_global")
        if idx is None or (isinstance(idx, float) and pd.isna(idx)):
            idx = row.get("indice_prioridade")
        faixa = row.get("faixa_prioridade_global")
        if faixa is None or (isinstance(faixa, float) and pd.isna(faixa)):
            faixa = row.get("faixa_prioridade")

        rows.append(
            {
                "semana_epidemiologica": se["rotulo"],
                "data_referencia": hoje.isoformat(),
                "cod_ibge": ibge[:7] if len(ibge) >= 7 else ibge,
                "municipio": str(row.get("municipio") or row.get("municipio_base") or ""),
                "regional_saude": str(row.get("regional_saude") or ""),
                "classe_atual": _nivel(row.get("nivel")),
                "classe_projetada_7d": _pick_proj(row),
                "tmax": pd.to_numeric(row.get("tmax"), errors="coerce"),
                "ur_pct": pd.to_numeric(ur, errors="coerce"),
                "pm25_ugm3": pd.to_numeric(row.get("pm25_ugm3"), errors="coerce"),
                "utci_c": pd.to_numeric(row.get("utci_proxy"), errors="coerce"),
                "focos_calor_7d": pd.to_numeric(focos, errors="coerce"),
                "iqa_classe": str(iqa).strip() if iqa is not None and str(iqa).lower() not in {"nan", "none"} else "",
                "indice_prioridade": pd.to_numeric(idx, errors="coerce"),
                "faixa_prioridade": str(faixa).strip().lower() if faixa is not None and str(faixa).lower() not in {"nan", "none"} else "",
                "determinante_principal": _pick_determinante(row),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=RODADA_COLS)
    return out[RODADA_COLS].sort_values(["regional_saude", "municipio"]).reset_index(drop=True)


def agregar_rodada_regional(rodada: pd.DataFrame) -> pd.DataFrame:
    """Agrega a rodada por regional (visão Sala)."""
    if rodada is None or rodada.empty:
        return pd.DataFrame()
    work = rodada.copy()
    work["_crit"] = work["classe_atual"].isin(["vermelha", "roxa"]).astype(int)
    work["_agrav"] = work.apply(
        lambda r: int(
            _NIVEL_ORDEM.get(str(r.get("classe_projetada_7d") or ""), 0)
            > _NIVEL_ORDEM.get(str(r.get("classe_atual") or ""), 0)
        ),
        axis=1,
    )
    g = (
        work.groupby("regional_saude", dropna=False)
        .agg(
            n_municipios=("cod_ibge", "count"),
            n_vermelha_roxa=("_crit", "sum"),
            n_agravamento_projetado=("_agrav", "sum"),
            tmax_mediana=("tmax", "median"),
            pm25_max=("pm25_ugm3", "max"),
        )
        .reset_index()
    )
    g["pct_vermelha_roxa"] = (100.0 * g["n_vermelha_roxa"] / g["n_municipios"]).round(1)
    return g.sort_values("pct_vermelha_roxa", ascending=False).reset_index(drop=True)


def build_validacao_modelo(rodada_proj: pd.DataFrame, rodada_obs: pd.DataFrame) -> pd.DataFrame:
    """Compara classe_projetada_7d (SE anterior) × classe_atual (SE atual)."""
    if rodada_proj is None or rodada_obs is None or rodada_proj.empty or rodada_obs.empty:
        return pd.DataFrame()
    left = rodada_proj[
        ["cod_ibge", "municipio", "regional_saude", "semana_epidemiologica", "classe_projetada_7d"]
    ].rename(
        columns={
            "semana_epidemiologica": "semana_projecao",
            "classe_projetada_7d": "classe_projetada",
        }
    )
    right = rodada_obs[["cod_ibge", "semana_epidemiologica", "classe_atual"]].rename(
        columns={
            "semana_epidemiologica": "semana_observacao",
            "classe_atual": "classe_observada",
        }
    )
    m = left.merge(right, on="cod_ibge", how="inner")
    if m.empty:
        return m
    m["nivel_projetado"] = m["classe_projetada"].map(lambda x: _NIVEL_ORDEM.get(_nivel(x), 0))
    m["nivel_observado"] = m["classe_observada"].map(lambda x: _NIVEL_ORDEM.get(_nivel(x), 0))
    m["acertou"] = m["classe_projetada"].map(_nivel) == m["classe_observada"].map(_nivel)
    m["diferenca_niveis"] = m["nivel_observado"] - m["nivel_projetado"]
    return m


def persist_rodada_hist(rodada: pd.DataFrame) -> int:
    """Upsert em hist_boletim_rodada_semanal (se schema disponível)."""
    if rodada is None or rodada.empty:
        return 0
    try:
        from sisclima.core.db import init_db, upsert_df

        init_db()
        return int(upsert_df(rodada, "hist_boletim_rodada_semanal", ["semana_epidemiologica", "cod_ibge"]))
    except Exception as exc:  # noqa: BLE001
        log.warning("Persistência hist_boletim_rodada_semanal falhou: %s", exc)
        return 0


def export_rodada_semanal(
    *,
    resumo: pd.DataFrame | None = None,
    ref: date | None = None,
    out_dir: Path | None = None,
    persist_hist: bool = True,
) -> dict[str, Any]:
    """Gera CSVs da rodada (+ regional) e opcionalmente persiste no histórico."""
    hoje = ref or date.today()
    from sisclima.engines.boletim_el_nino.cenario import semana_iso

    se = semana_iso(hoje)
    dest = Path(out_dir or DEFAULT_OUT_DIR)
    dest.mkdir(parents=True, exist_ok=True)

    rodada = build_rodada_semanal(resumo, ref=hoje)
    tag = se["rotulo"].replace(" ", "_").replace("/", "-")
    path_mun = dest / f"rodada_semanal_{tag}.csv"
    path_reg = dest / f"rodada_regional_{tag}.csv"
    path_val = dest / f"validacao_modelo_{tag}.csv"

    rodada.to_csv(path_mun, index=False, encoding="utf-8-sig")
    agregar_rodada_regional(rodada).to_csv(path_reg, index=False, encoding="utf-8-sig")

    n_hist = persist_rodada_hist(rodada) if persist_hist else 0

    # Validação: tenta CSV da semana anterior no mesmo diretório
    path_val_out = None
    n_val = 0
    prev_files = sorted(dest.glob("rodada_semanal_SE_*.csv"))
    prev = [p for p in prev_files if p.resolve() != path_mun.resolve()]
    if prev and not rodada.empty:
        try:
            anterior = pd.read_csv(prev[-1], dtype={"cod_ibge": str})
            valid = build_validacao_modelo(anterior, rodada)
            if not valid.empty:
                valid.to_csv(path_val, index=False, encoding="utf-8-sig")
                path_val_out = path_val
                n_val = len(valid)
                acerto = float(valid["acertou"].mean()) if "acertou" in valid.columns else None
            else:
                acerto = None
        except Exception as exc:  # noqa: BLE001
            log.debug("Validação automática indisponível: %s", exc)
            acerto = None
    else:
        acerto = None

    return {
        "semana": se["rotulo"],
        "n_municipios": int(len(rodada)),
        "path_municipal": str(path_mun),
        "path_regional": str(path_reg),
        "path_validacao": str(path_val_out) if path_val_out else None,
        "n_validacao": n_val,
        "acuracia": acerto,
        "n_hist_upsert": n_hist,
    }
