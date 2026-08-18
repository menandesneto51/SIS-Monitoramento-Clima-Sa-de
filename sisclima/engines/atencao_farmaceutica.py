# -*- coding: utf-8 -*-
"""Atenção farmacêutica estadual (SAF/SES) e municipal (CBAF/Visa) segundo o cenário."""
from __future__ import annotations

from typing import Any

import pandas as pd

# Limiares alinhados a config/settings.yaml (qualidade_ar.pm25_ugm3).
PM25_MASCARA_SENSIVEIS = 15.0
PM25_MASCARA_GRUPO_RISCO = 25.0
PM25_MASCARA_EXTERNO = 50.0
PM25_MASCARA_POPULACAO = 75.0


def _num(v) -> float | None:
    x = pd.to_numeric(v, errors="coerce")
    if x is None or pd.isna(x):
        return None
    return float(x)


def _nivel_ar(row: pd.Series | dict[str, Any]) -> str:
    nv = str(row.get("qualidade_ar_nivel") or "").strip().lower()
    if nv in {"amarela", "laranja", "vermelha", "roxa"}:
        return nv
    iq = _num(row.get("iq_ar_score"))
    if iq is None:
        pm = _num(row.get("pm25_ugm3"))
        if pm is None:
            return ""
        if pm >= PM25_MASCARA_POPULACAO:
            return "roxa"
        if pm >= PM25_MASCARA_EXTERNO:
            return "vermelha"
        if pm >= PM25_MASCARA_GRUPO_RISCO:
            return "laranja"
        if pm >= PM25_MASCARA_SENSIVEIS:
            return "amarela"
        return "verde"
    if iq >= 4:
        return "roxa"
    if iq >= 3:
        return "vermelha"
    if iq >= 2:
        return "laranja"
    if iq >= 1:
        return "amarela"
    return "verde"


def _inundacao(row: pd.Series | dict[str, Any]) -> bool:
    blob = " ".join(
        str(row.get(c) or "").lower()
        for c in ("situacao_hidro", "risco_predominante", "nivel_alerta_hidro", "nivel_chuva", "motivo", "motivo_integrado")
    )
    if any(k in blob for k in ("inund", "cheia", "alag", "enchente")):
        return True
    hidro = str(row.get("nivel_alerta_hidro") or "").lower()
    chuva = str(row.get("nivel_chuva") or "").lower()
    if hidro in {"laranja", "vermelha", "roxa"} or chuva in {"laranja", "vermelha", "roxa"}:
        sat = _num(row.get("indice_saturacao_solo"))
        if sat is not None and sat >= 70:
            return True
    return False


def cenario_flags(row: pd.Series | dict[str, Any]) -> dict[str, bool]:
    pm = _num(row.get("pm25_ugm3"))
    utci = _num(row.get("utci_proxy"))
    tmax = _num(row.get("tmax"))
    arbo = _num(row.get("incidencia_arbovirus_100k")) or _num(row.get("casos_arbovirus_7d"))
    srag = _num(row.get("casos_srag"))
    risco = _num(row.get("risco_cumulativo_3d"))
    nv_ar = _nivel_ar(row)
    focos = _num(row.get("focos_queimadas_24h")) or _num(row.get("focos_24h")) or _num(row.get("focos_inpe_24h"))
    return {
        "fumaca": nv_ar in {"laranja", "vermelha", "roxa"} or (pm is not None and pm >= PM25_MASCARA_GRUPO_RISCO) or (focos is not None and focos > 0),
        "iqa_atencao": nv_ar in {"amarela", "laranja", "vermelha", "roxa"} or (pm is not None and pm >= PM25_MASCARA_SENSIVEIS),
        "inundacao": _inundacao(row),
        "calor": (utci is not None and utci >= 32) or (tmax is not None and tmax >= 35) or (risco is not None and risco >= 10),
        "arbovirose": arbo is not None and arbo > 0,
        "srag": srag is not None and srag > 0,
    }


def orientacao_mascara(pm25: float | None, nivel_ar: str = "") -> str:
    """Uso de máscara segundo IQA/PM2,5 operacional (não substitui boletim CETESB/INMET)."""
    nv = (nivel_ar or "").lower()
    if nv == "roxa" or (pm25 is not None and pm25 >= PM25_MASCARA_POPULACAO):
        return (
            "IQA péssimo/roxo: PFF2/N95 para toda a população ao sair; evitar exercício ao ar livre; "
            "priorizar ambientes internos e grupos vulneráveis."
        )
    if nv == "vermelha" or (pm25 is not None and pm25 >= PM25_MASCARA_EXTERNO):
        return (
            "IQA ruim/vermelho: PFF2/N95 em atividade externa; suspender educação física ao ar livre; "
            "grupos de risco permanecem em ambiente protegido."
        )
    if nv == "laranja" or (pm25 is not None and pm25 >= PM25_MASCARA_GRUPO_RISCO):
        return (
            "IQA moderado-alto/laranja: PFF2/N95 recomendada a asmáticos, DPOC, crianças, idosos, gestantes "
            "e trabalhadores externos; reduzir exposição à fumaça."
        )
    if nv == "amarela" or (pm25 is not None and pm25 >= PM25_MASCARA_SENSIVEIS):
        return (
            "IQA atenção/amarelo: máscara opcional a grupos sensíveis em exposição prolongada ao ar livre; "
            "monitorar sintomas respiratórios."
        )
    return "IQA em faixa boa: manter rotina; máscara não é prioridade populacional."


def acao_municipal(row: pd.Series | dict[str, Any]) -> str:
    """CBAF / farmácia das UBS / Visa municipal — o que o município pode executar."""
    flags = cenario_flags(row)
    pm = _num(row.get("pm25_ugm3"))
    partes: list[str] = []
    if flags["iqa_atencao"] or flags["fumaca"] or flags["srag"]:
        partes.append(
            "Farmácia básica/UBS: conferir estoque de broncodilatadores (salbutamol spray e solução, "
            "ipratrópio), corticoides sistêmicos (prednisolona/prednisona) e inalatórios, espaçadores "
            "e oxigênio nas portas de urgência."
        )
        partes.append(orientacao_mascara(pm, _nivel_ar(row)))
        partes.append(
            "APS: busca ativa de asmáticos/DPOC cadastrados; orientar hidratação e evitar queima de lixo/biomassa."
        )
    if flags["inundacao"]:
        partes.append(
            "Visa/almoxarifado municipal: conferir hipoclorito de sódio 2,5% para tratamento de água, "
            "SRO, cloro residual e comunicação de água segura; não usar água de enchente para consumo."
        )
        partes.append(
            "Farmácia/UBS: SRO, sais de reidratação, antitérmicos; articular antitetânica e, se houver, "
            "soro antiofídico com a regional."
        )
    if flags["calor"]:
        partes.append(
            "Farmácia/UBS: autonomia de SRO, soro oral/EV e antitérmicos; pontos de hidratação com insumo visível."
        )
    if flags["arbovirose"]:
        partes.append(
            "Componente básico: paracetamol/dipirona e SRO para arboviroses; não dispensar AINE em suspeita de dengue; "
            "fluxo para dengue grave com a regulação."
        )
    if not partes:
        partes.append(
            "Rotina CBAF: revisar validade e posição de SRO, broncodilatadores e corticoides; "
            "manter hipoclorito da Visa em quantidade de pronta entrega."
        )
    return " ".join(partes)


def acao_estadual(row: pd.Series | dict[str, Any] | None = None, *, agreg: dict[str, Any] | None = None) -> str:
    """SAF/SES — programação, redistribuição e orientação técnica (não substitui a farmácia municipal)."""
    flags = cenario_flags({} if row is None else row)
    if agreg:
        flags = {k: bool(flags.get(k) or agreg.get(k)) for k in flags}
    partes: list[str] = []
    partes.append(
        "Competência estadual (SAF/CEME/regionais): programar e redistribuir estoque estratégico "
        "entre regionais; emitir nota técnica às farmácias municipais; não substituir a dispensação do CBAF."
    )
    if flags.get("iqa_atencao") or flags.get("fumaca") or flags.get("srag"):
        partes.append(
            "Linha respiratória: posicionar/redistribuir broncodilatadores, corticoides e insumos de inalação "
            "às regionais com IQA laranja+ ou SRAG em alta; orientar PFF2 aos trabalhadores da saúde em fumaça."
        )
    if flags.get("inundacao"):
        partes.append(
            "Visa/SAF estadual: checar e antecipar hipoclorito 2,5%, SRO e materiais de tratamento de água "
            "às regionais em risco de cheia; articular soro antiofídico e imunobiológicos com CEME/PNI."
        )
    if flags.get("calor"):
        partes.append(
            "Estoque estratégico de SRO, soro EV e antitérmicos para regionais em calor extremo; "
            "apoiar pontos de hidratação sem deslocar a responsabilidade municipal."
        )
    if flags.get("arbovirose"):
        partes.append(
            "Protocolo de dengue grave: insumos de hidratação venosa e orientação para não usar AINE; "
            "reforço de programação do componente básico nas regionais com incidência elevada."
        )
    return " ".join(partes)


def acao_regional(row: pd.Series | dict[str, Any] | None = None, *, agreg: dict[str, Any] | None = None) -> str:
    flags = cenario_flags({} if row is None else row)
    if agreg:
        flags = {k: bool(flags.get(k) or agreg.get(k)) for k in flags}
    partes = [
        "Apoiar municípios na conferência do CBAF e na logística de última milha; reportar rupturas à SAF/SES."
    ]
    if flags.get("fumaca") or flags.get("iqa_atencao"):
        partes.append(
            "Mapear farmácias/UBS com baixo estoque de broncodilatadores/corticoides nos municípios com IQA elevado; "
            "reforçar orientação de máscara conforme IQA."
        )
    if flags.get("inundacao"):
        partes.append("Checar hipoclorito e SRO nos municípios com alerta hidro/cheia antes do pico da cota.")
    return " ".join(partes)


def flags_from_resumo(resumo: pd.DataFrame | None) -> dict[str, bool]:
    if resumo is None or resumo.empty:
        return cenario_flags({})
    acc = {k: False for k in cenario_flags({})}
    amostra = resumo.head(400)
    for _, row in amostra.iterrows():
        f = cenario_flags(row)
        for k, v in f.items():
            acc[k] = acc[k] or v
    return acc


def recomendacoes_pipeline(stage: str, resumo: pd.DataFrame | None = None) -> list[tuple[str, str]]:
    """Eixos gravados em recomendacoes_operacionais (além do checklist de estágio)."""
    flags = flags_from_resumo(resumo)
    dummy = {}
    recs = [
        ("Atenção farmacêutica estadual", acao_estadual(dummy, agreg=flags)),
        ("Atenção farmacêutica municipal", acao_municipal(_row_pior(resumo) if resumo is not None else {})),
    ]
    pm_max = None
    nv = ""
    if resumo is not None and not resumo.empty:
        if "pm25_ugm3" in resumo.columns:
            pm_max = _num(pd.to_numeric(resumo["pm25_ugm3"], errors="coerce").max())
        if "qualidade_ar_nivel" in resumo.columns:
            ordem = {"roxa": 4, "vermelha": 3, "laranja": 2, "amarela": 1, "verde": 0}
            ranked = resumo["qualidade_ar_nivel"].astype(str).str.lower().map(ordem).fillna(-1)
            if ranked.notna().any() and float(ranked.max()) >= 0:
                nv = str(resumo.loc[ranked.idxmax(), "qualidade_ar_nivel"]).lower()
    recs.append(("Comunicação IQA / máscaras", orientacao_mascara(pm_max, nv)))
    _ = stage
    return recs


def _row_pior(resumo: pd.DataFrame) -> dict[str, Any]:
    if resumo is None or resumo.empty:
        return {}
    df = resumo.copy()
    if "pm25_ugm3" in df.columns:
        df["_pm"] = pd.to_numeric(df["pm25_ugm3"], errors="coerce")
        if df["_pm"].notna().any():
            return df.sort_values("_pm", ascending=False).iloc[0].to_dict()
    return df.iloc[0].to_dict()


def aplicar_acoes_farmaceuticas(resumo: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return resumo
    out = resumo.copy()
    flags_est = flags_from_resumo(out)
    txt_est = acao_estadual({}, agreg=flags_est)
    mun, est = [], []
    for _, row in out.iterrows():
        mun.append(acao_municipal(row))
        est.append(txt_est)
    out["acao_farmaceutica_municipal"] = mun
    out["acao_farmaceutica_estadual"] = est
    out["orientacao_mascara_iqa"] = [
        orientacao_mascara(_num(r.get("pm25_ugm3")), _nivel_ar(r)) for _, r in out.iterrows()
    ]
    return out
