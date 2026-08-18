# -*- coding: utf-8 -*-
"""Prontidão Climática Municipal — Nível 1 (sem BNAFAR).

Fluxo: cenário → impacto sanitário → população vulnerável → demanda →
insumos críticos → estoque (se houver) → consumo previsto → ruptura → plano.

Os cinco motores permanecem auditáveis: a IA só consulta a matriz YAML.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.db import read_table, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.atencao_farmaceutica import acao_estadual, acao_municipal, orientacao_mascara

log = get_logger(__name__)

_CFG: dict[str, Any] | None = None
FASE1 = ("seca_estiagem", "baixa_umidade", "queimadas_fumaca")


def load_matriz() -> dict[str, Any]:
    global _CFG
    if _CFG is not None:
        return _CFG
    path = ROOT / "config" / "prontidao_climatica.yaml"
    with path.open("r", encoding="utf-8") as fh:
        _CFG = yaml.safe_load(fh) or {}
    return _CFG


def _n(s, default=np.nan) -> pd.Series:
    return pd.to_numeric(s, errors="coerce") if s is not None else pd.Series(dtype=float)


def _clip01(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").clip(lower=0, upper=1).fillna(0)


def _cod(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


# ---------------------------------------------------------------------------
# Motor 1 — Cenários climático-sanitários
# ---------------------------------------------------------------------------
def motor_cenarios(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["cod_ibge"] = _cod(out["cod_ibge"]) if "cod_ibge" in out.columns else pd.NA
    umid = _n(out["umidade_media"]) if "umidade_media" in out.columns else pd.Series(np.nan, index=out.index)
    solo = _n(out["indice_saturacao_solo"]) if "indice_saturacao_solo" in out.columns else pd.Series(np.nan, index=out.index)
    chuva = _n(out["precipitacao_mm"]) if "precipitacao_mm" in out.columns else pd.Series(np.nan, index=out.index)
    tmax = _n(out["tmax"]) if "tmax" in out.columns else pd.Series(np.nan, index=out.index)
    utci = _n(out["utci_proxy"]) if "utci_proxy" in out.columns else pd.Series(np.nan, index=out.index)
    pm = _n(out["pm25_ugm3"]) if "pm25_ugm3" in out.columns else pd.Series(np.nan, index=out.index)
    focos = _n(out["focos_queimadas_7d"]) if "focos_queimadas_7d" in out.columns else pd.Series(0.0, index=out.index)
    tmin = _n(out["tmin"]) if "tmin" in out.columns else pd.Series(np.nan, index=out.index)
    hidro = out["situacao_hidro"].astype(str).str.lower() if "situacao_hidro" in out.columns else pd.Series("", index=out.index)
    niv_hidro = out["nivel_alerta_hidro"].astype(str).str.lower() if "nivel_alerta_hidro" in out.columns else pd.Series("", index=out.index)
    arbo = _n(out["casos_arbovirus_7d"]) if "casos_arbovirus_7d" in out.columns else pd.Series(0.0, index=out.index)

    seca_i = np.nanmax(
        [
            _clip01((45.0 - umid) / 35.0).to_numpy(),
            _clip01((25.0 - solo) / 25.0).to_numpy() if solo.notna().any() else np.zeros(len(out)),
            _clip01((2.0 - chuva.fillna(2.0)) / 2.0).to_numpy() * 0.4,
        ],
        axis=0,
    )
    umid_i = _clip01((40.0 - umid) / 30.0).to_numpy()
    fuma_i = np.clip(
        np.nanmax(
            [
                _clip01((pm - 15.0) / 60.0).to_numpy(),
                _clip01(focos.fillna(0) / 40.0).to_numpy(),
            ],
            axis=0,
        ),
        0,
        1,
    )
    calor_i = np.nanmax(
        [
            _clip01((tmax - 34.0) / 8.0).to_numpy(),
            _clip01((utci - 32.0) / 10.0).to_numpy(),
        ],
        axis=0,
    )
    ench_i = np.clip(
        np.maximum(
            _clip01((solo - 70.0) / 30.0).to_numpy(),
            hidro.str.contains("inund|cheia|alag", regex=True, na=False).astype(float).to_numpy(),
        ),
        0,
        1,
    )
    ench_i = np.maximum(ench_i, niv_hidro.isin(["laranja", "vermelha", "roxa"]).astype(float).to_numpy() * 0.7)
    frio_i = _clip01((12.0 - tmin) / 10.0).to_numpy()
    vet_i = np.clip(
        0.4 * ench_i + 0.4 * _clip01(arbo.fillna(0) / 20.0).to_numpy() + 0.2 * _clip01((tmax - 28.0) / 8.0).to_numpy(),
        0,
        1,
    )

    out["int_seca_estiagem"] = np.round(seca_i, 3)
    out["int_baixa_umidade"] = np.round(umid_i, 3)
    out["int_queimadas_fumaca"] = np.round(fuma_i, 3)
    out["int_onda_calor"] = np.round(calor_i, 3)
    out["int_chuva_enchente"] = np.round(ench_i, 3)
    out["int_tempestade_vendaval"] = np.round(ench_i * 0.6, 3)
    out["int_frio_extremo"] = np.round(frio_i, 3)
    out["int_pos_chuva_vetores"] = np.round(np.nan_to_num(vet_i, nan=0.0), 3)

    ints = [c for c in out.columns if c.startswith("int_")]
    for c in ints:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    out["cenario_dominante"] = out[ints].idxmax(axis=1).str.replace("int_", "", regex=False)
    out["intensidade_dominante"] = out[ints].max(axis=1)
    ativos = []
    for _, row in out.iterrows():
        on = [c.replace("int_", "") for c in ints if float(row.get(c) or 0) >= 0.35]
        ativos.append(",".join(on) if on else "")
    out["cenarios_ativos"] = ativos
    return out


def _rotulo_risco(x: float) -> str:
    if pd.isna(x):
        return "sem dado"
    if x >= 0.75:
        return "muito_alto"
    if x >= 0.55:
        return "alto"
    if x >= 0.35:
        return "moderado"
    if x >= 0.15:
        return "baixo"
    return "muito_baixo"


# ---------------------------------------------------------------------------
# Motor 2 — Impacto epidemiológico
# ---------------------------------------------------------------------------
def motor_impacto(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cfg = load_matriz()["cenarios"]
    srag = _n(out["casos_srag"]) if "casos_srag" in out.columns else pd.Series(0.0, index=out.index)
    out["risco_respiratorio"] = np.clip(
        0.55 * _n(out.get("int_queimadas_fumaca")).fillna(0)
        + 0.25 * _n(out.get("int_baixa_umidade")).fillna(0)
        + 0.20 * _clip01(srag / 8.0),
        0,
        1,
    )
    out["risco_hidrico_dda"] = np.clip(
        0.6 * _n(out.get("int_seca_estiagem")).fillna(0) + 0.4 * _n(out.get("int_chuva_enchente")).fillna(0),
        0,
        1,
    )
    out["risco_calor_saude"] = _n(out.get("int_onda_calor")).fillna(0)
    pop = _n(out["populacao"]) if "populacao" in out.columns else pd.Series(np.nan, index=out.index)
    idoso = _n(out["idosos_pct"]) if "idosos_pct" in out.columns else pd.Series(np.nan, index=out.index)
    cri = _n(out["criancas_0_4_pct"]) if "criancas_0_4_pct" in out.columns else pd.Series(np.nan, index=out.index)
    rural = _n(out["rural_pct"]) if "rural_pct" in out.columns else pd.Series(np.nan, index=out.index)
    frac = (idoso.fillna(12) + cri.fillna(8) + rural.fillna(20) * 0.35) / 100.0
    out["populacao_vulneravel_estimada"] = (pop * frac.clip(0.08, 0.55)).round(0)
    impactos = []
    for _, row in out.iterrows():
        names = []
        for cid in str(row.get("cenarios_ativos") or "").split(","):
            meta = cfg.get(cid) or {}
            names.extend(meta.get("impactos") or [])
        impactos.append("; ".join(dict.fromkeys(names)) if names else "monitorar agravos do cenário dominante")
    out["impactos_prioritarios"] = impactos
    out["risco_climatico_rotulo"] = out["intensidade_dominante"].map(_rotulo_risco)
    out["risco_respiratorio_rotulo"] = out["risco_respiratorio"].map(_rotulo_risco)
    return out


def _fator_historico_respiratorio() -> tuple[float, str]:
    """rho PM2,5×SRAG na série municipal, se houver; senão a regra YAML."""
    try:
        corr = read_table("analise_clima_saude_correlacoes_v8")
    except Exception:
        corr = pd.DataFrame()
    if corr is None or corr.empty:
        return 1.0, "regra"
    work = corr.copy()
    cols = {c.lower(): c for c in work.columns}
    exp = cols.get("exposicao") or cols.get("variavel_x") or cols.get("x")
    des = cols.get("desfecho") or cols.get("variavel_y") or cols.get("y")
    rho_c = cols.get("rho") or cols.get("spearman") or cols.get("corr")
    if not exp or not des or not rho_c:
        return 1.0, "regra"
    m = work[work[exp].astype(str).str.contains("pm25", case=False, na=False)]
    m = m[m[des].astype(str).str.contains("srag", case=False, na=False)]
    if m.empty:
        return 1.0, "regra"
    rho = pd.to_numeric(m[rho_c], errors="coerce").abs().max()
    if pd.isna(rho) or rho < 0.05:
        return 1.0, "regra"
    return float(1.0 + min(0.45, rho) * 0.8), "historico_spearman"


# ---------------------------------------------------------------------------
# Motor 3 — Demanda assistencial e farmacêutica
# ---------------------------------------------------------------------------
def motor_demanda(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cfg = load_matriz()
    mes = date.today().month
    saz = float((cfg.get("sazonalidade_mt") or {}).get(mes, 1.0))
    fator_hist, fonte_hist = _fator_historico_respiratorio()
    cen = cfg["cenarios"]
    f_clima = []
    f_regra = []
    fontes = []
    itens = []
    for _, row in out.iterrows():
        ativo = [c for c in str(row.get("cenarios_ativos") or "").split(",") if c]
        if not ativo:
            ativo = [str(row.get("cenario_dominante") or "seca_estiagem")]
        prod = 1.0
        tags = []
        need = []
        for cid in ativo:
            meta = cen.get(cid) or {}
            intens = float(row.get(f"int_{cid}") or 0)
            fr = float(meta.get("fator_regra") or 1.08)
            # interpola 1 → fator_regra conforme intensidade
            prod *= 1.0 + (fr - 1.0) * min(1.0, max(0.0, intens))
            tags.append(str(meta.get("regra") or cid))
            need.extend(meta.get("estoques") or [])
        f_clima.append(round(prod, 4))
        f_regra.append(";".join(tags))
        fontes.append("Ministério da Saúde / matriz ARARAS")
        itens.append("; ".join(dict.fromkeys(need)))
    out["fator_climatico"] = f_clima
    out["fator_sazonal"] = saz
    out["fator_epidemiologico"] = fator_hist
    vuln = _n(out["indice_vulnerabilidade_calor"]) if "indice_vulnerabilidade_calor" in out.columns else pd.Series(50.0, index=out.index)
    extra = pd.Series(0.0, index=out.index)
    if "n_territorios_tradicionais" in out.columns:
        extra = (pd.to_numeric(out["n_territorios_tradicionais"], errors="coerce").fillna(0) / 25.0).clip(0, 0.12)
    if "tem_zas_barragem" in out.columns:
        extra = extra + 0.03 * (pd.to_numeric(out["tem_zas_barragem"], errors="coerce").fillna(0) > 0).astype(float)
    out["fator_vulnerabilidade"] = (1.0 + _clip01(vuln.fillna(50) / 100.0) * 0.25 + extra).clip(upper=1.40).round(4)
    out["fator_consumo"] = (
        out["fator_climatico"] * out["fator_sazonal"] * out["fator_epidemiologico"] * out["fator_vulnerabilidade"]
    ).clip(upper=1.80).round(4)
    out["demanda_projetada_pct"] = ((out["fator_consumo"] - 1.0) * 100).round(1)
    out["fonte_fator_epidemiologico"] = fonte_hist
    out["regras_aplicadas"] = f_regra
    out["insumos_criticos"] = itens
    out["fonte_matriz"] = fontes
    return out


# ---------------------------------------------------------------------------
# Motor 4 — Prontidão (IPFC + IPMEC + redistribuição)
# ---------------------------------------------------------------------------
def _estoque_utilizavel(df: pd.DataFrame) -> pd.Series:
    """Nível 1: autonomia_dias se existir. Nível 2 (BNAFAR): físico − vencimentos − reservas + compras."""
    if "estoque_utilizavel" in df.columns:
        return _n(df["estoque_utilizavel"])
    if "autonomia_min_dias" in df.columns:
        return _n(df["autonomia_min_dias"])
    if "autonomia_dias" in df.columns:
        return _n(df["autonomia_dias"])
    return pd.Series(np.nan, index=df.index)


def motor_prontidao(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    cfg = load_matriz()
    lead = float(cfg.get("lead_time_reposicao_dias") or 15)
    horizonte = float(cfg.get("horizonte_dias") or 14)
    estoque = _estoque_utilizavel(out)
    cons_prev_diario = pd.Series(np.nan, index=out.index)
    # Sem BNAFAR não há unidades: cobertura = autonomia / fator_consumo (dias equivalentes).
    cobertura = estoque / out["fator_consumo"].replace(0, np.nan)
    out["estoque_nivel"] = np.where(estoque.notna(), "nivel_2_parcial", "nivel_1_conferir")
    out["cobertura_dias"] = cobertura.round(1)
    out["lead_time_reposicao_dias"] = lead
    out["horizonte_dias"] = horizonte
    rupt = []
    ipfc = []
    for i, row in out.iterrows():
        cob = row.get("cobertura_dias")
        intens = float(row.get("intensidade_dominante") or 0)
        if pd.notna(cob):
            if cob < lead * 0.7:
                rupt.append("ALTO")
                ipfc.append(max(5, min(95, cob / lead * 55)))
            elif cob < lead:
                rupt.append("MODERADO")
                ipfc.append(max(20, min(90, cob / lead * 75)))
            else:
                rupt.append("BAIXO")
                ipfc.append(min(95, 55 + (cob - lead)))
        else:
            # Sem estoque: IPFC cai com demanda projetada (indica urgência de conferência, não ruptura confirmada).
            demanda = float(row.get("demanda_projetada_pct") or 0)
            score = 70.0 - demanda * 0.6 - intens * 25.0
            ipfc.append(float(np.clip(score, 8, 78)))
            rupt.append("CONFERIR" if intens >= 0.35 or demanda >= 15 else "INDETERMINADO")
    out["risco_ruptura"] = rupt
    out["ipfc"] = np.round(ipfc, 1)
    out["consumo_previsto_14d_indice"] = (out["fator_consumo"] * horizonte).round(2)

    pesos = cfg.get("ipmec_pesos") or {}
    farm = _clip01(out["ipfc"] / 100.0)
    cnes = _clip01(_n(out["indice_capacidade_cnes"]) / 100.0) if "indice_capacidade_cnes" in out.columns else pd.Series(np.nan, index=out.index)
    ocup = _n(out["ocupacao_leitos_pct"]) if "ocupacao_leitos_pct" in out.columns else pd.Series(np.nan, index=out.index)
    assis = np.nanmean(
        np.vstack(
            [
                cnes.fillna(np.nan).to_numpy(),
                (1.0 - _clip01((ocup - 60.0) / 40.0)).to_numpy(),
            ]
        ),
        axis=0,
    )
    resp = 1.0 - _n(out.get("risco_respiratorio")).fillna(0) * 0.5
    agua = 1.0 - _clip01(_n(out["indice_deficit_wash"]) / 100.0) if "indice_deficit_wash" in out.columns else pd.Series(np.nan, index=out.index)
    vig = _clip01(_n(out["completude_dados_pct"]) / 100.0) if "completude_dados_pct" in out.columns else pd.Series(np.nan, index=out.index)
    vul = 1.0 - _clip01(_n(out["indice_vulnerabilidade_calor"]) / 100.0) if "indice_vulnerabilidade_calor" in out.columns else pd.Series(0.5, index=out.index)
    dim = {
        "farmaceutica": farm,
        "assistencial": pd.Series(assis, index=out.index),
        "profissional": pd.Series(np.nan, index=out.index),
        "respiratoria": resp,
        "laboratorial": pd.Series(np.nan, index=out.index),
        "transporte": pd.Series(np.nan, index=out.index),
        "energia": 1.0 - _clip01(_n(out["falhas_infra_pct"]) / 100.0) if "falhas_infra_pct" in out.columns else pd.Series(np.nan, index=out.index),
        "agua": agua,
        "vigilancia": vig,
        "vulnerabilidade": vul,
    }
    obs = pd.Series(0.0, index=out.index)
    acc = pd.Series(0.0, index=out.index)
    wsum = pd.Series(0.0, index=out.index)
    lacunas = []
    for name, series in dim.items():
        w = float(pesos.get(name, 0.1))
        present = series.notna()
        obs = obs + present.astype(float)
        acc = acc + series.fillna(0) * w * present.astype(float)
        wsum = wsum + w * present.astype(float)
        out[f"ipmec_{name}"] = (series * 100).round(1)
    out["ipmec"] = np.where(wsum > 0, (acc / wsum * 100).round(1), np.nan)
    out["ipmec_dimensoes_observadas"] = obs.astype(int)
    out["ipmec_completude_pct"] = (obs / len(dim) * 100).round(1)
    for _, row in out.iterrows():
        miss = [n for n, s in dim.items() if pd.isna(s.loc[row.name] if row.name in s.index else np.nan)]
        lacunas.append(",".join(miss))
    out["ipmec_lacunas"] = lacunas
    out["nivel_prontidao"] = pd.cut(
        out["ipmec"].fillna(50),
        bins=[-1, 40, 55, 70, 101],
        labels=["vermelho", "laranja", "amarelo", "verde"],
    ).astype(str)
    return out


def redistribuicao_regional(df: pd.DataFrame) -> pd.DataFrame:
    """Doadores → receptores na mesma regional. Sem BNAFAR: sinal técnico, sem quantidade de unidades."""
    if df is None or df.empty or "regional_saude" not in df.columns:
        return pd.DataFrame()
    rows = []
    gcol = "regional_saude"
    for reg, g in df.groupby(gcol):
        if len(g) < 2:
            continue
        cob = _n(g["cobertura_dias"]) if "cobertura_dias" in g.columns else pd.Series(np.nan, index=g.index)
        ipmec = _n(g["ipmec"])
        if cob.notna().sum() >= 2:
            rec = g.loc[cob.idxmin()]
            don = g.loc[cob.idxmax()]
            if float(cob.min()) < 10 and float(cob.max()) >= 28:
                rows.append(_linha_redist(reg, don, rec, "cobertura_dias", float(cob.max()), float(cob.min()), "estoque"))
        elif ipmec.notna().sum() >= 2:
            rec = g.loc[ipmec.idxmin()]
            don = g.loc[ipmec.idxmax()]
            if float(ipmec.min()) < 55 and float(ipmec.max()) >= 68:
                rows.append(_linha_redist(reg, don, rec, "ipmec", float(ipmec.max()), float(ipmec.min()), "capacidade"))
    return pd.DataFrame(rows)


def _linha_redist(reg, don, rec, metrica, vdon, vrec, tipo) -> dict[str, Any]:
    return {
        "regional_saude": str(reg),
        "doador_municipio": don.get("municipio"),
        "doador_ibge": don.get("cod_ibge"),
        "receptor_municipio": rec.get("municipio"),
        "receptor_ibge": rec.get("cod_ibge"),
        "metrica": metrica,
        "valor_doador": round(vdon, 1),
        "valor_receptor": round(vrec, 1),
        "tipo": tipo,
        "orientacao": (
            f"{don.get('municipio')} → {rec.get('municipio')}: avaliar remanejamento, "
            "preservando estoque/capacidade mínima de segurança do doador. Quantidade só com BNAFAR (nível 2)."
        ),
    }


# ---------------------------------------------------------------------------
# Motor 5 — Plano de ação 0–24h / 24–72h / 3–7d
# ---------------------------------------------------------------------------
def motor_orientacao(row: pd.Series) -> list[dict[str, Any]]:
    cfg = load_matriz()
    cen = cfg["cenarios"]
    mun = str(row.get("municipio") or row.get("cod_ibge") or "Município")
    ativo = [c for c in str(row.get("cenarios_ativos") or "").split(",") if c]
    fase1 = set(cfg.get("fase1") or FASE1)
    intensivos = [c for c in ativo if c in fase1]
    regras = str(row.get("regras_aplicadas") or "CLIMA-SECA-017")
    conf = "alta" if int(row.get("ipmec_dimensoes_observadas") or 0) >= 6 else (
        "media" if int(row.get("ipmec_dimensoes_observadas") or 0) >= 4 else "baixa"
    )
    farm_mun = acao_municipal(row)
    farm_est = acao_estadual(row.to_dict())
    pm = pd.to_numeric(row.get("pm25_ugm3"), errors="coerce")
    mascara = orientacao_mascara(None if pd.isna(pm) else float(pm), str(row.get("qualidade_ar_nivel") or ""))
    base_meta = {
        "cod_ibge": row.get("cod_ibge"),
        "municipio": mun,
        "cenarios": ",".join(ativo),
        "nivel": row.get("nivel_prontidao"),
        "regra": regras,
        "fonte": "Ministério da Saúde / protocolo estadual / REMUME-RENAME (classes)",
        "confianca": conf,
        "validador": cfg.get("validador"),
        "data_analise": date.today().isoformat(),
        "estoque_nivel": row.get("estoque_nivel"),
    }
    acoes = []

    def _add(horizonte, acao, publico):
        rec = dict(base_meta)
        rec.update({"horizonte": horizonte, "acao": acao, "publico": publico})
        acoes.append(rec)

    _add("0-24h", f"Instalar/manter sala de situação municipal ({mun}). Cenário: {row.get('cenario_dominante')}.", "gestor")
    _add("0-24h", farm_mun, "farmacia_municipal")
    _add("0-24h", farm_est, "saf_estadual")
    if "queimadas_fumaca" in ativo or "baixa_umidade" in ativo:
        _add("0-24h", mascara, "populacao")
        _add("0-24h", "Alertar APS/UPA; busca ativa de asmáticos, DPOC, idosos e crianças.", "aps")
    if "seca_estiagem" in ativo:
        _add("0-24h", "Acionar Vigiagua; conferir hipoclorito 2,5% e pontos de água segura.", "visa")
    _add("24-72h", "Mapear rupturas do CBAF e reportar à Regional/SAF; não aguardar desabastecimento clínico.", "farmacia_municipal")
    if row.get("risco_ruptura") in {"ALTO", "CONFERIR"}:
        _add("24-72h", "Antecipar reposição ou avaliar redistribuição regional; revisar oxigênio e dispositivos inalatórios.", "saf_regional")
    _add("24-72h", "Localizar grupos vulneráveis (idosos, gestantes, rurais, rua) e checar continuidade de tratamentos crônicos.", "aps")
    _add("3-7d", "Revisar cobertura estimada vs lead time de 15 dias; atualizar o plano se PM2,5/focos/umidade piorarem.", "gestor")
    _add("3-7d", "Manutenção: escolas, ILPI e unidades sentinelas com protocolo de baixa umidade/fumaça.", "aps")
    if not intensivos and ativo:
        _add("manutencao", "Cenário fora da fase 1 (seca/umidade/queimadas): manter vigilância; plano detalhado em expansão.", "gestor")
    if any((cen.get(c) or {}).get("usa_kit_calamidade") for c in ativo):
        _add(
            "24-72h",
            f"Conferir Kit Calamidade MS ({cfg.get('kit_calamidade_referencia')}) — referência para desabrigados, não lista universal de estoque climático.",
            "farmacia_municipal",
        )
    try:
        from sisclima.engines.vigibarragens_clima import acoes_territoriais

        for item in acoes_territoriais(row):
            _add(item.get("horizonte") or "24-72h", item.get("acao") or "", item.get("publico") or "aps")
    except Exception as exc:  # noqa: BLE001
        log.warning("Ações territoriais Vigibarragens não aplicadas em %s: %s", mun, exc)
    return acoes


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def run_prontidao_climatica(resumo: pd.DataFrame | None = None, persist: bool = True) -> dict[str, Any]:
    if resumo is None or resumo.empty:
        resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty:
        return {"ok": False, "motivo": "resumo vazio"}
    df = motor_cenarios(resumo)
    df = motor_impacto(df)
    try:
        from sisclima.ingestion.vigibarragens import persistir
        from sisclima.engines.vigibarragens_clima import anexar_territorios

        persistir()
        df = anexar_territorios(df)
    except Exception as exc:  # noqa: BLE001
        log.warning("Vigibarragens/territórios não anexados: %s", exc)
    df = motor_demanda(df)
    df = motor_prontidao(df)
    redist = redistribuicao_regional(df)
    planos: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        planos.extend(motor_orientacao(row))
    plano_df = pd.DataFrame(planos)

    keep = [
        c
        for c in [
            "cod_ibge",
            "municipio",
            "regional_saude",
            "cenario_dominante",
            "cenarios_ativos",
            "intensidade_dominante",
            "risco_climatico_rotulo",
            "risco_respiratorio",
            "risco_respiratorio_rotulo",
            "populacao_vulneravel_estimada",
            "demanda_projetada_pct",
            "fator_consumo",
            "fator_climatico",
            "fator_sazonal",
            "fator_epidemiologico",
            "fonte_fator_epidemiologico",
            "cobertura_dias",
            "lead_time_reposicao_dias",
            "risco_ruptura",
            "ipfc",
            "ipmec",
            "nivel_prontidao",
            "ipmec_completude_pct",
            "ipmec_lacunas",
            "estoque_nivel",
            "regras_aplicadas",
            "insumos_criticos",
            "impactos_prioritarios",
            "int_seca_estiagem",
            "int_baixa_umidade",
            "int_queimadas_fumaca",
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
            "cuidados_territoriais",
        ]
        if c in df.columns
    ]
    snap = df[keep].copy()

    inj_cols = [
        "cenario_dominante",
        "cenarios_ativos",
        "ipfc",
        "ipmec",
        "nivel_prontidao",
        "risco_ruptura",
        "demanda_projetada_pct",
        "populacao_vulneravel_estimada",
        "cobertura_dias",
        "estoque_nivel",
        "n_aldeias",
        "n_quilombos",
        "n_assentamentos",
        "n_territorios_tradicionais",
        "n_barragens_dpa_alto",
        "cuidados_territoriais",
    ]
    resumo_out = resumo.copy()
    resumo_out["cod_ibge"] = _cod(resumo_out["cod_ibge"]) if "cod_ibge" in resumo_out.columns else resumo_out.get("cod_ibge")
    snap["cod_ibge"] = _cod(snap["cod_ibge"])
    add = snap[["cod_ibge"] + [c for c in inj_cols if c in snap.columns]].drop_duplicates("cod_ibge")
    for c in add.columns:
        if c != "cod_ibge" and c in resumo_out.columns:
            resumo_out = resumo_out.drop(columns=[c])
    resumo_out = resumo_out.merge(add, on="cod_ibge", how="left")

    if persist:
        write_df(snap, "prontidao_municipal")
        write_df(redist, "prontidao_redistribuicao_regional")
        write_df(plano_df, "prontidao_plano_acao")
        write_df(resumo_out, "resumo_municipal_atual")
        log.info(
            "Prontidão climática: %s municípios, redistribuições %s, ações %s",
            len(snap),
            len(redist),
            len(plano_df),
        )
    return {
        "ok": True,
        "municipios": len(snap),
        "redistribuicoes": len(redist),
        "acoes": len(plano_df),
        "nivel_1": int((snap["estoque_nivel"] == "nivel_1_conferir").sum()) if "estoque_nivel" in snap.columns else len(snap),
        "snap": snap,
        "redist": redist,
        "plano": plano_df,
        "resumo": resumo_out,
    }
