# -*- coding: utf-8 -*-
"""Pacote CSV/JSON para homologar ocupação IndicaSUS (filtros SIEGES) × SISREG."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.db import read_table, table_exists

OUT_DIR = ROOT / "data" / "output" / "validacao_ocupacao_sieges"

FILTROS_SIEGES = {
    "SituacaoAtual": "<> Bloqueado (TipoAcompanhamento)",
    "Tipo": ["SUS Habilitado", "SUS Não Habilitado"],
    "TipoLeito": "<> Pronto Atendimento (CategoriaCNES)",
    "unidades": "lista institucional + padrões UPA/PA/Unidade Mista",
}


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False)


def _save(df: pd.DataFrame | None, out: Path, name: str, ts: str) -> str | None:
    if df is None or df.empty:
        return None
    stable = out / f"{name}.csv"
    stamped = out / f"{name}_{ts}.csv"
    df.to_csv(stable, index=False, encoding="utf-8-sig")
    df.to_csv(stamped, index=False, encoding="utf-8-sig")
    return str(stable.relative_to(ROOT)).replace("\\", "/")


def gerar_pacote_validacao_ocupacao(*, out_dir: Path | None = None) -> dict[str, Any]:
    """Gera CSVs de validação a partir das tabelas operacionais atuais."""
    out = out_dir or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    resumo = read_table("resumo_municipal_atual") if table_exists("resumo_municipal_atual") else pd.DataFrame()
    occ_mun = read_table("hospital_ocupacao_municipio") if table_exists("hospital_ocupacao_municipio") else pd.DataFrame()
    occ_un = read_table("hospital_ocupacao_unidade") if table_exists("hospital_ocupacao_unidade") else pd.DataFrame()
    occ_est = read_table("hospital_ocupacao_estado") if table_exists("hospital_ocupacao_estado") else pd.DataFrame()
    sisreg = read_table("ops_sisreg_municipio") if table_exists("ops_sisreg_municipio") else pd.DataFrame()

    for df in (resumo, occ_mun, occ_un, sisreg):
        if df is not None and not df.empty and "cod_ibge" in df.columns:
            df["cod_ibge"] = _ibge7(df["cod_ibge"])

    paths: dict[str, str] = {}

    com_out = pd.DataFrame()
    if occ_mun is not None and not occ_mun.empty:
        nome_col = next((c for c in ("municipio_base", "municipio", "municipio_indicasus") if c in occ_mun.columns), None)
        cols = [
            c
            for c in [
                "cod_ibge",
                nome_col,
                "regional_saude",
                "unidades",
                "leitos_existentes",
                "leitos_sus",
                "leitos_ocupados",
                "ocupacao_pct",
                "leitos_bloqueados_movimento",
                "leitos_higienizacao",
                "leitos_reservados",
                "ultima_movimentacao",
                "fonte",
            ]
            if c and c in occ_mun.columns
        ]
        com_out = occ_mun[cols].sort_values("ocupacao_pct", ascending=False) if "ocupacao_pct" in cols else occ_mun[cols]
        p = _save(com_out, out, "01_municipios_com_ocupacao_sieges", ts)
        if p:
            paths["01_municipios_com_ocupacao_sieges"] = p

    sem_out = pd.DataFrame()
    if resumo is not None and not resumo.empty and "fonte_ocupacao" in resumo.columns:
        fonte = resumo["fonte_ocupacao"].fillna("").astype(str)
        sem = resumo.loc[~fonte.str.contains("INDICASUS_TEMPO_REAL", case=False, na=False)].copy()
        nome_r = next((c for c in ("municipio", "municipio_base", "nome_municipio") if c in resumo.columns), None)
        cols_sem = [
            c
            for c in ["cod_ibge", nome_r, "regional_saude", "fonte_ocupacao", "ocupacao_leitos_pct"]
            if c and c in resumo.columns
        ]
        sem_out = sem[cols_sem].sort_values(nome_r or "cod_ibge") if cols_sem else sem
        if sisreg is not None and not sisreg.empty and "cod_ibge" in sisreg.columns:
            kpi = [
                c
                for c in sisreg.columns
                if any(x in c.lower() for x in ("solicit", "pendente", "fila", "kpi", "hosp", "volume", "total"))
            ]
            keep_s = ["cod_ibge"] + [c for c in kpi if c != "cod_ibge"][:8]
            keep_s = [c for c in keep_s if c in sisreg.columns]
            sem_out = sem_out.merge(sisreg[keep_s].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        p = _save(sem_out, out, "02_municipios_sem_leitos_elegiveis", ts)
        if p:
            paths["02_municipios_sem_leitos_elegiveis"] = p

    un_out = pd.DataFrame()
    if occ_un is not None and not occ_un.empty:
        gcols = [
            c
            for c in (
                "UnidadeNotificadoraId",
                "NomeUnidade",
                "cod_ibge",
                "municipio_base",
                "municipio_indicasus",
                "LocalidadeId",
            )
            if c in occ_un.columns
        ]
        num = [
            c
            for c in (
                "leitos_existentes",
                "leitos_sus",
                "leitos_ocupados",
                "leitos_bloqueados_movimento",
                "leitos_higienizacao",
                "leitos_reservados",
            )
            if c in occ_un.columns
        ]
        if gcols and num:
            un_out = occ_un.groupby(gcols, dropna=False)[num].sum().reset_index()
            if "leitos_existentes" in un_out.columns and "leitos_ocupados" in un_out.columns:
                un_out["ocupacao_pct"] = (
                    100 * un_out["leitos_ocupados"] / un_out["leitos_existentes"].replace({0: pd.NA})
                ).astype(float)
            un_out = un_out.sort_values(
                ["ocupacao_pct", "leitos_existentes"], ascending=[False, False], na_position="last"
            )
            p = _save(un_out, out, "03_unidades_ocupacao_sieges", ts)
            if p:
                paths["03_unidades_ocupacao_sieges"] = p

    comp = pd.DataFrame()
    if resumo is not None and not resumo.empty:
        nome_r = next((c for c in ("municipio", "municipio_base") if c in resumo.columns), None)
        rcols = [
            c
            for c in [
                "cod_ibge",
                nome_r,
                "regional_saude",
                "fonte_ocupacao",
                "ocupacao_leitos_pct",
                "leitos_total",
                "leitos_ocupados",
            ]
            if c and c in resumo.columns
        ]
        comp = resumo[rcols].copy()
        if sisreg is not None and not sisreg.empty:
            kpi = [
                c
                for c in sisreg.columns
                if any(x in c.lower() for x in ("solicit", "pendente", "fila", "kpi_sisreg", "hosp"))
            ]
            keep_s = ["cod_ibge"] + [c for c in kpi if c != "cod_ibge"][:10]
            keep_s = [c for c in keep_s if c in sisreg.columns]
            comp = comp.merge(sisreg[keep_s].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if not com_out.empty and "cod_ibge" in com_out.columns:
            flag = com_out[["cod_ibge"]].drop_duplicates().assign(tem_ocupacao_sieges=1)
            comp = comp.merge(flag, on="cod_ibge", how="left")
            comp["tem_ocupacao_sieges"] = comp["tem_ocupacao_sieges"].fillna(0).astype(int)
        p = _save(comp, out, "04_comparativo_ocupacao_x_sisreg_142", ts)
        if p:
            paths["04_comparativo_ocupacao_x_sisreg_142"] = p

    est_row: dict[str, Any] = {}
    if occ_est is not None and not occ_est.empty:
        est_row = occ_est.iloc[-1].to_dict()

    leitos_e = float(com_out["leitos_existentes"].sum()) if not com_out.empty and "leitos_existentes" in com_out.columns else None
    leitos_o = float(com_out["leitos_ocupados"].sum()) if not com_out.empty and "leitos_ocupados" in com_out.columns else None
    pct = est_row.get("ocupacao_pct")
    if pct is None and leitos_e:
        pct = 100.0 * (leitos_o or 0) / leitos_e

    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "filtros_sieges": FILTROS_SIEGES,
        "totais": {
            "municipios_mt": int(len(resumo)) if resumo is not None and not resumo.empty else None,
            "com_ocupacao": int(len(com_out)),
            "sem_leitos_elegiveis": int(len(sem_out)),
            "unidades": (
                int(un_out["UnidadeNotificadoraId"].nunique())
                if not un_out.empty and "UnidadeNotificadoraId" in un_out.columns
                else None
            ),
            "leitos_existentes": leitos_e,
            "leitos_ocupados": leitos_o,
            "ocupacao_pct_estadual": float(pct) if pct is not None and pd.notna(pct) else None,
        },
        "arquivos": paths,
        "como_validar_com_sieges": [
            "Comparar ocupação estadual e top 10 de 01_* com o dash SIEGES (mesmos filtros).",
            "Conferir amostra de unidades em 03_*; UPA/PA não devem aparecer.",
            "Usar 02_* no ofício STI/assistência (ampliar notificação).",
            "Usar 04_* para pressão SISREG onde não há ocupação IndicaSUS.",
        ],
    }
    (out / "00_metodo_validacao.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    (out / "00_checklist_homologacao.txt").write_text(
        (
            "Checklist homologação ocupação ARARAS × SIEGES\n"
            "================================================\n"
            f"Gerado: {meta['gerado_em']}\n\n"
            f"Municípios com ocupação: {meta['totais']['com_ocupacao']}\n"
            f"Sem leitos elegíveis: {meta['totais']['sem_leitos_elegiveis']}\n"
            f"Unidades: {meta['totais']['unidades']}\n"
            f"Leitos elegíveis / ocupados: {meta['totais']['leitos_existentes']} / {meta['totais']['leitos_ocupados']}\n"
            f"Ocupação estadual: {meta['totais']['ocupacao_pct_estadual']}%\n\n"
            "[ ] Conferir % estadual no dash SIEGES (±1 pp)\n"
            "[ ] Conferir top 10 municípios (01_*)\n"
            "[ ] Amostra de 5 unidades (03_*)\n"
            "[ ] UPA/Pronto Atendimento fora do recorte\n"
            "[ ] Encaminhar 02_* à assistência/STI\n"
            f"Pasta: {out}\n"
        ),
        encoding="utf-8",
    )
    meta["outdir"] = str(out)
    return meta


if __name__ == "__main__":
    print(json.dumps(gerar_pacote_validacao_ocupacao(), ensure_ascii=False, indent=2, default=str))
