# -*- coding: utf-8 -*-
"""
Alertas multinível do SIS Clima-Saúde MT.

Quatro escopos de disparo (com o mesmo núcleo de indicadores):
  1. estadual  → SES-MT / CIEVS estadual
  2. regional  → Regional de Saúde + municípios sob jurisdição
  3. municipal → Secretaria Municipal / plantão municipal
  4. cuiaba    → Vigidesastre Cuiabá (IBGE 5103403)

Cada payload traz: ícone/nível, indicadores climáticos e de saúde,
predição ~7d, e orientações para gestor, profissionais e população.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

CUIABA_IBGE = "5103403"

EMOJI = {
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
    "cinza": "⚪",
}

LEVEL_LABEL = {
    "verde": "Verde — rotina",
    "amarela": "Amarela — atenção",
    "laranja": "Laranja — alerta",
    "vermelha": "Vermelha — resposta intensificada",
    "roxa": "Roxa — mobilização plena",
    "cinza": "Cinza — dados insuficientes",
}

ESCOPOS = ("estadual", "regional", "municipal", "cuiaba")

# Orientações por público e nível (texto curto para boletim)
ORIENT = {
    "verde": {
        "gestor": (
            "Manter monitoramento de rotina; revisar estoques e planos locais; "
            "acompanhar boletins INMET/Cemaden e o painel SIS."
        ),
        "profissional": (
            "Reforçar hidratação e identificação precoce de desidratação/hipertermia; "
            "manter notificação de agravos sensíveis ao clima (SRAG, arboviroses, DIID)."
        ),
        "populacao": (
            "Hidrate-se, evite exposição prolongada ao sol no pico de calor e "
            "elimine criadouros do mosquito."
        ),
    },
    "amarela": {
        "gestor": (
            "Ativar sala de situação municipal/regional; boletim diário; "
            "checar autonomia de insumos (SRO, soro, água) e comunicação de risco."
        ),
        "profissional": (
            "Priorizar idosos, gestantes, crianças e pessoas em situação de rua; "
            "orientar hidratação e resfriamento; intensificar busca ativa na APS."
        ),
        "populacao": (
            "Evite atividades físicas no horário mais quente; use roupas leves; "
            "procure UBS/UPA se houver tontura, confusão ou febre alta."
        ),
    },
    "laranja": {
        "gestor": (
            "COE parcial; articular assistência, vigilância e comunicação; "
            "abrir pontos de resfriamento/hidratação; informar a regional e a SES."
        ),
        "profissional": (
            "Expandir observação climatizada; triagem por gravidade; "
            "reforçar investigação de dengue grave e SRAG; fluxos de regulação."
        ),
        "populacao": (
            "Procure pontos de resfriamento e hidratação; não deixe crianças/idosos "
            "sozinhos em ambientes quentes; siga orientações oficiais da SMS/SES."
        ),
    },
    "vermelha": {
        "gestor": (
            "COE pleno; reuniões operacionais ≥2×/dia; priorizar leitos e regulação; "
            "comunicar risco à população e acionar contingência de energia/água."
        ),
        "profissional": (
            "Priorizar hipertermia, desidratação grave e descompensações "
            "cardiorrespiratórias; suspender eletivos se necessário; notificar oportunamente."
        ),
        "populacao": (
            "Situação de alto risco: evite exposição ao calor/fumaça; "
            "procure atendimento imediato em sinais de gravidade; siga canais oficiais."
        ),
    },
    "roxa": {
        "gestor": (
            "Comando unificado e apoio interfederativo; redistribuição emergencial "
            "de insumos/leitos; comunicação de crise e registro para pós-evento."
        ),
        "profissional": (
            "Protocolos de emergência plena; reforço de equipes; "
            "priorização absoluta de risco de vida e notificações imediatas."
        ),
        "populacao": (
            "Emergência sanitária climática: siga orientações oficiais da SES/SMS; "
            "procure abrigo/resfriamento e atendimento urgente se necessário."
        ),
    },
    "cinza": {
        "gestor": "Priorizar coleta/qualidade de dados antes de comunicar alerta definitivo.",
        "profissional": "Registrar lacunas de informação e manter vigilância clínica de rotina.",
        "populacao": "Acompanhe canais oficiais; mantenha cuidados gerais de hidratação e prevenção.",
    },
}

INDICADOR_COLS = [
    ("nivel", "Nível SIS"),
    ("nivel_alerta_integrado", "Nível integrado SIS+TITAN"),
    ("score", "Score operacional"),
    ("score_alerta_integrado", "Score alerta integrado"),
    ("tmax", "Tmáx (°C)"),
    ("utci_proxy", "UTCI/proxy"),
    ("risco_cumulativo_3d", "Risco acumulado 3d"),
    ("ocupacao_leitos_pct", "Ocupação leitos (%)"),
    ("pressao_calor_pct", "Pressão assistencial (%)"),
    ("pm25_ugm3", "PM2,5"),
    ("indice_saturacao_solo", "Índice saturação solo"),
    ("classe_saturacao_solo", "Classe solo"),
    ("incidencia_arbovirus_100k", "Incid. arbovírus /100 mil"),
    ("zscore_arbovirus", "Z-score arboviroses"),
    ("casos_srag", "Casos SRAG"),
    ("incidencia_srag_100k", "Incid. SRAG /100 mil"),
    ("letalidade_pct", "Letalidade (%)"),
    ("indice_tensao_climatica", "Tensão climática"),
    ("indice_carga_saude", "Carga em saúde"),
    ("indice_vigilancia_integrada", "Vigilância integrada"),
    ("tendencia_7d", "Tendência 7d"),
    ("nivel_predicao_7d", "Nível predito 7d"),
    ("componente_dominante", "Componente dominante"),
    ("motivo", "Motivo SIS"),
    ("motivo_integrado", "Motivo integrado"),
]


def _norm_nivel(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in {"amarelo"}:
        s = "amarela"
    if s in {"vermelho"}:
        s = "vermelha"
    if s in {"roxo"}:
        s = "roxa"
    return s if s in EMOJI else "cinza"


def _worst_nivel(series: pd.Series) -> str:
    if series is None or series.empty:
        return "cinza"
    ranks = series.map(lambda x: STAGE_ORDER.get(_norm_nivel(x), -1))
    if ranks.isna().all():
        return "cinza"
    best = int(ranks.max())
    for k, v in STAGE_ORDER.items():
        if v == best:
            return k
    return "cinza"


def _fmt(v: Any, nd: int = 1) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    try:
        f = float(v)
        if abs(f - int(f)) < 1e-9:
            return str(int(f))
        return f"{f:.{nd}f}"
    except Exception:
        s = str(v).strip()
        return s if s else "—"


def _pick_indicadores(row: pd.Series | dict) -> list[dict[str, str]]:
    data = row if isinstance(row, pd.Series) else pd.Series(row)
    out = []
    for col, label in INDICADOR_COLS:
        if col in data.index and pd.notna(data.get(col)):
            out.append({"campo": col, "rotulo": label, "valor": _fmt(data.get(col))})
    return out


def _orientacoes(nivel: str) -> dict[str, str]:
    return dict(ORIENT.get(_norm_nivel(nivel), ORIENT["cinza"]))


def _merge_base(
    resumo: pd.DataFrame,
    alerta_int: pd.DataFrame | None = None,
    pred: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base = resumo.copy() if resumo is not None else pd.DataFrame()
    if base.empty:
        return base
    if "cod_ibge" in base.columns:
        base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    if alerta_int is not None and not alerta_int.empty and "cod_ibge" in alerta_int.columns:
        ai = alerta_int.copy()
        ai["cod_ibge"] = ai["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        keep = [c for c in ai.columns if c == "cod_ibge" or c not in base.columns]
        base = base.merge(ai[keep], on="cod_ibge", how="left")
    if pred is not None and not pred.empty and "cod_ibge" in pred.columns:
        pr = pred.copy()
        pr["cod_ibge"] = pr["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        keep = [c for c in ["cod_ibge", "nivel_predicao_7d", "score_predicao", "horizonte_dias"] if c in pr.columns]
        if len(keep) > 1:
            base = base.merge(pr[keep].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
    if "nivel_alerta_integrado" not in base.columns and "nivel" in base.columns:
        base["nivel_alerta_integrado"] = base["nivel"]
    if "nivel" not in base.columns and "nivel_alerta_integrado" in base.columns:
        base["nivel"] = base["nivel_alerta_integrado"]
    return base


def _titulo(escopo: str, nivel: str, alvo: str) -> str:
    icon = EMOJI.get(_norm_nivel(nivel), "⚪")
    lab = LEVEL_LABEL.get(_norm_nivel(nivel), nivel)
    prefix = {
        "estadual": "ALERTA ESTADUAL · SES-MT / CIEVS",
        "regional": f"ALERTA REGIONAL · {alvo}",
        "municipal": f"ALERTA MUNICIPAL · {alvo}",
        "cuiaba": "ALERTA VIGIDESASTRE CUIABÁ",
    }.get(escopo, "ALERTA SIS")
    return f"{icon} {prefix} · {lab}"


def _build_payload(
    *,
    escopo: str,
    nivel: str,
    alvo_nome: str,
    alvo_id: str,
    municipios: list[str],
    indicadores: list[dict[str, str]],
    predicao: dict[str, str],
    motivo: str,
    fontes: list[str],
) -> dict[str, Any]:
    niv = _norm_nivel(nivel)
    return {
        "escopo": escopo,
        "alvo_id": alvo_id,
        "alvo_nome": alvo_nome,
        "nivel": niv,
        "icone": EMOJI.get(niv, "⚪"),
        "nivel_rotulo": LEVEL_LABEL.get(niv, niv),
        "titulo": _titulo(escopo, niv, alvo_nome),
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "municipios_abrangidos": municipios,
        "n_municipios": len(municipios),
        "indicadores": indicadores,
        "predicao": predicao,
        "motivo": motivo or "—",
        "fontes": fontes,
        "orientacoes": _orientacoes(niv),
    }


def _predicao_from_rows(df: pd.DataFrame) -> dict[str, str]:
    if df is None or df.empty:
        return {"nivel_predicao_7d": "—", "resumo": "Predição 7d indisponível nesta rodada."}
    niv = _worst_nivel(df["nivel_predicao_7d"]) if "nivel_predicao_7d" in df.columns else "cinza"
    n_up = 0
    if "tendencia_7d" in df.columns:
        n_up = int(df["tendencia_7d"].astype(str).str.lower().isin(["subindo", "alta", "piora"]).sum())
    return {
        "nivel_predicao_7d": niv,
        "icone_predicao": EMOJI.get(niv, "⚪"),
        "municipios_tendencia_alta": str(n_up),
        "resumo": (
            f"Horizonte ~7 dias: nível predito predominante {LEVEL_LABEL.get(niv, niv)}. "
            f"Municípios com tendência de piora: {n_up}."
        ),
    }


def _motivo_agregado(df: pd.DataFrame) -> str:
    for col in ["motivo_integrado", "motivo", "orientacao_leiga"]:
        if col in df.columns:
            s = df[col].dropna().astype(str)
            if not s.empty:
                return str(s.iloc[0])[:500]
    return "Consolidado a partir do nível operacional e componentes climáticos/assistenciais."


def _indicadores_agregados(df: pd.DataFrame) -> list[dict[str, str]]:
    if df.empty:
        return []
    # usa município sentinela (pior score) como referência visual
    sort_cols = [c for c in ["score_alerta_integrado", "score", "risco_cumulativo_3d"] if c in df.columns]
    sent = df.sort_values(sort_cols, ascending=False).iloc[0] if sort_cols else df.iloc[0]
    inds = _pick_indicadores(sent)
    # acrescenta contagens de nível
    if "nivel_alerta_integrado" in df.columns or "nivel" in df.columns:
        col = "nivel_alerta_integrado" if "nivel_alerta_integrado" in df.columns else "nivel"
        vc = df[col].map(_norm_nivel).value_counts()
        dist = ", ".join(f"{k}:{int(v)}" for k, v in vc.items())
        inds.insert(0, {"campo": "distribuicao_niveis", "rotulo": "Distribuição de níveis", "valor": dist})
    inds.insert(0, {"campo": "n_municipios", "rotulo": "Municípios no escopo", "valor": str(len(df))})
    return inds


def build_alertas_multinivel(
    resumo: pd.DataFrame,
    alerta_integrado: pd.DataFrame | None = None,
    predicao_7d: pd.DataFrame | None = None,
    min_level: str = "amarela",
) -> list[dict[str, Any]]:
    """Gera lista de payloads: 1 estadual + N regionais + N municipais (≥min) + Cuiabá."""
    base = _merge_base(resumo, alerta_integrado, predicao_7d)
    if base.empty:
        return []

    min_rank = STAGE_ORDER.get(_norm_nivel(min_level), 1)
    nivel_col = "nivel_alerta_integrado" if "nivel_alerta_integrado" in base.columns else "nivel"
    base["_nivel"] = base[nivel_col].map(_norm_nivel) if nivel_col in base.columns else "cinza"
    base["_rank"] = base["_nivel"].map(STAGE_ORDER).fillna(-1)

    fontes = [
        "Open-Meteo",
        "INMET",
        "Cemaden",
        "ANA",
        "Copernicus/CAMS (quando disponível)",
        "SINAN/SIVEP/SIM/IndicaSUS (DW)",
        "SISREG (regulação/fila)",
        "SIS Clima-Saúde MT",
    ]

    payloads: list[dict[str, Any]] = []

    # 1) Estadual → SES
    niv_est = _worst_nivel(base["_nivel"])
    payloads.append(
        _build_payload(
            escopo="estadual",
            nivel=niv_est,
            alvo_nome="Estado de Mato Grosso · SES/CIEVS",
            alvo_id="MT",
            municipios=sorted(base.get("municipio", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()),
            indicadores=_indicadores_agregados(base),
            predicao=_predicao_from_rows(base),
            motivo=_motivo_agregado(base.sort_values("_rank", ascending=False)),
            fontes=fontes,
        )
    )

    # 2) Regionais
    if "regional_saude" in base.columns:
        for reg, g in base.groupby(base["regional_saude"].fillna("Sem regional").astype(str)):
            niv = _worst_nivel(g["_nivel"])
            payloads.append(
                _build_payload(
                    escopo="regional",
                    nivel=niv,
                    alvo_nome=str(reg),
                    alvo_id=str(reg),
                    municipios=sorted(g.get("municipio", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()),
                    indicadores=_indicadores_agregados(g),
                    predicao=_predicao_from_rows(g),
                    motivo=_motivo_agregado(g.sort_values("_rank", ascending=False)),
                    fontes=fontes,
                )
            )

    # 3) Municipais (a partir do mínimo configurado)
    crit = base[base["_rank"] >= min_rank].copy()
    for _, row in crit.iterrows():
        mun = str(row.get("municipio") or row.get("cod_ibge") or "Município")
        payloads.append(
            _build_payload(
                escopo="municipal",
                nivel=row.get("_nivel"),
                alvo_nome=mun,
                alvo_id=str(row.get("cod_ibge") or mun),
                municipios=[mun],
                indicadores=_pick_indicadores(row),
                predicao={
                    "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                    "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                    "resumo": f"Predição ~7d: {LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}",
                },
                motivo=str(row.get("motivo_integrado") or row.get("motivo") or "—"),
                fontes=fontes,
            )
        )

    # 4) Cuiabá Vigidesastre (sempre gera pacote dedicado se houver linha)
    cui = base[base["cod_ibge"].astype(str) == CUIABA_IBGE] if "cod_ibge" in base.columns else pd.DataFrame()
    if cui.empty and "municipio" in base.columns:
        cui = base[base["municipio"].astype(str).str.lower().str.contains("cuiab", na=False)]
    if not cui.empty:
        row = cui.sort_values("_rank", ascending=False).iloc[0]
        payloads.append(
            _build_payload(
                escopo="cuiaba",
                nivel=row.get("_nivel"),
                alvo_nome="Cuiabá · Vigidesastre",
                alvo_id=CUIABA_IBGE,
                municipios=["Cuiabá"],
                indicadores=_pick_indicadores(row),
                predicao={
                    "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                    "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                    "resumo": f"Predição ~7d Cuiabá: {LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}",
                },
                motivo=str(row.get("motivo_integrado") or row.get("motivo") or "Alerta dedicado Vigidesastre Cuiabá."),
                fontes=fontes + ["Vigidesastre Cuiabá"],
            )
        )

    return payloads


def payloads_to_dataframe(payloads: list[dict[str, Any]]) -> pd.DataFrame:
    """Tabela plana para painel/auditoria (1 linha por escopo/alvo)."""
    rows = []
    for p in payloads:
        o = p.get("orientacoes") or {}
        pred = p.get("predicao") or {}
        rows.append(
            {
                "escopo": p.get("escopo"),
                "alvo_id": p.get("alvo_id"),
                "alvo_nome": p.get("alvo_nome"),
                "nivel": p.get("nivel"),
                "icone": p.get("icone"),
                "titulo": p.get("titulo"),
                "n_municipios": p.get("n_municipios"),
                "motivo": p.get("motivo"),
                "nivel_predicao_7d": pred.get("nivel_predicao_7d"),
                "predicao_resumo": pred.get("resumo"),
                "orientacao_gestor": o.get("gestor"),
                "orientacao_profissional": o.get("profissional"),
                "orientacao_populacao": o.get("populacao"),
                "n_indicadores": len(p.get("indicadores") or []),
                "gerado_em": p.get("gerado_em"),
            }
        )
    return pd.DataFrame(rows)


def render_payload_markdown(p: dict[str, Any]) -> str:
    """Texto/Markdown do boletim (e-mail/Telegram/prévia)."""
    lines = [
        f"# {p.get('titulo')}",
        "",
        f"**Escopo:** {p.get('escopo')} · **Alvo:** {p.get('alvo_nome')} · **Municípios:** {p.get('n_municipios')}",
        f"**Gerado em:** {p.get('gerado_em')}",
        "",
        "## Motivo",
        str(p.get("motivo") or "—"),
        "",
        "## Indicadores",
    ]
    for ind in p.get("indicadores") or []:
        lines.append(f"- **{ind.get('rotulo')}:** {ind.get('valor')}")
    pred = p.get("predicao") or {}
    lines += [
        "",
        "## Predição (~7 dias)",
        f"{pred.get('icone_predicao', '')} {pred.get('resumo', '—')}",
        "",
        "## Orientações",
        f"### Gestor\n{((p.get('orientacoes') or {}).get('gestor') or '—')}",
        "",
        f"### Profissionais de saúde\n{((p.get('orientacoes') or {}).get('profissional') or '—')}",
        "",
        f"### População\n{((p.get('orientacoes') or {}).get('populacao') or '—')}",
        "",
        "## Fontes",
        ", ".join(p.get("fontes") or []),
        "",
        "_SIS Clima-Saúde MT · CIEVS/SES-MT · validar no painel antes do envio externo._",
    ]
    return "\n".join(lines)


def persist_payloads(payloads: list[dict[str, Any]], table: str = "alertas_multinivel_v1") -> int:
    """Persiste resumo tabular na base operacional."""
    from sisclima.core.db import write_df

    df = payloads_to_dataframe(payloads)
    if df.empty:
        return 0
    write_df(df, table, if_exists="replace")
    return len(df)
