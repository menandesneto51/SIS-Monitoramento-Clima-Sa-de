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

import re
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

ORIENT = {
    "verde": {
        "gestor": (
            "Manter monitoramento de rotina; revisar estoques e planos locais; "
            "acompanhar boletins oficiais de tempo/desastres e o painel Clima-Saúde."
        ),
        "profissional": (
            "Reforçar hidratação e identificação precoce de desidratação e hipertermia; "
            "manter notificação de agravos sensíveis ao clima "
            "(síndrome respiratória grave, dengue e outras arboviroses, doenças diarreicas)."
        ),
        "populacao": (
            "Hidrate-se, evite exposição prolongada ao sol no pico de calor e "
            "elimine criadouros do mosquito."
        ),
    },
    "amarela": {
        "gestor": (
            "Ativar sala de situação municipal ou regional; emitir boletim diário; "
            "checar autonomia de insumos (soro de reidratação, soro, água) e comunicação de risco."
        ),
        "profissional": (
            "Priorizar idosos, gestantes, crianças e pessoas em situação de rua; "
            "orientar hidratação e resfriamento; intensificar busca ativa na atenção básica."
        ),
        "populacao": (
            "Evite atividades físicas no horário mais quente; use roupas leves; "
            "procure unidade básica ou pronto atendimento se houver tontura, confusão ou febre alta."
        ),
    },
    "laranja": {
        "gestor": (
            "Instalar centro de operações parcial; articular assistência, vigilância e comunicação; "
            "abrir pontos de resfriamento e hidratação; informar a Regional de Saúde e a Secretaria de Estado."
        ),
        "profissional": (
            "Expandir observação em ambiente climatizado; triagem por gravidade; "
            "reforçar investigação de dengue grave e síndrome respiratória aguda; fluxos de regulação."
        ),
        "populacao": (
            "Procure pontos de resfriamento e hidratação; não deixe crianças ou idosos "
            "sozinhos em ambientes quentes; siga orientações oficiais da secretaria municipal e estadual."
        ),
    },
    "vermelha": {
        "gestor": (
            "Centro de operações pleno; reuniões operacionais pelo menos duas vezes ao dia; "
            "priorizar leitos e regulação; comunicar risco à população e acionar contingência de energia e água."
        ),
        "profissional": (
            "Priorizar hipertermia, desidratação grave e descompensações "
            "cardiorrespiratórias; suspender eletivos se necessário; notificar oportunamente."
        ),
        "populacao": (
            "Situação de alto risco: evite exposição ao calor e à fumaça; "
            "procure atendimento imediato em sinais de gravidade; siga canais oficiais."
        ),
    },
    "roxa": {
        "gestor": (
            "Comando unificado e apoio entre entes federativos; redistribuição emergencial "
            "de insumos e leitos; comunicação de crise e registro para o pós-evento."
        ),
        "profissional": (
            "Protocolos de emergência plena; reforço de equipes; "
            "priorização absoluta de risco de vida e notificações imediatas."
        ),
        "populacao": (
            "Emergência sanitária climática: siga orientações oficiais da secretaria estadual e municipal; "
            "procure abrigo ou resfriamento e atendimento urgente se necessário."
        ),
    },
    "cinza": {
        "gestor": "Priorizar coleta e qualidade de dados antes de comunicar alerta definitivo.",
        "profissional": "Registrar lacunas de informação e manter vigilância clínica de rotina.",
        "populacao": "Acompanhe canais oficiais; mantenha cuidados gerais de hidratação e prevenção.",
    },
}

INDICADOR_COLS = [
    ("nivel", "Classificação operacional"),
    ("nivel_alerta_integrado", "Classificação integrada (clima + saúde + alertas oficiais)"),
    ("score", "Pontuação operacional (0 a 4)"),
    ("score_alerta_integrado", "Pontuação do alerta integrado"),
    ("tmax", "Temperatura máxima (°C)"),
    ("utci_proxy", "Sensação térmica estimada (°C)"),
    ("risco_cumulativo_3d", "Risco de calor acumulado em 3 dias"),
    ("ocupacao_leitos_pct", "Ocupação de leitos hospitalares (%)"),
    ("pressao_calor_pct", "Pressão assistencial estimada (%)"),
    ("pm25_ugm3", "Partículas finas no ar — PM2,5 (µg/m³)"),
    ("indice_saturacao_solo", "Índice de saturação do solo (0 a 100)"),
    ("classe_saturacao_solo", "Situação do solo"),
    ("incidencia_arbovirus_100k", "Incidência de arboviroses por 100 mil habitantes"),
    ("zscore_arbovirus", "Desvio epidêmico de arboviroses"),
    ("casos_srag", "Casos de síndrome respiratória aguda grave"),
    ("incidencia_srag_100k", "Incidência de síndrome respiratória grave por 100 mil"),
    ("letalidade_pct", "Letalidade (%)"),
    ("indice_tensao_climatica", "Índice de tensão climática (0 a 100)"),
    ("indice_carga_saude", "Índice de carga em saúde (0 a 100)"),
    ("indice_vigilancia_integrada", "Índice de vigilância integrada (0 a 100)"),
    ("tendencia_7d", "Tendência prevista para ~7 dias"),
    ("nivel_predicao_7d", "Classificação prevista para ~7 dias"),
    ("componente_dominante", "Fator que mais elevou o alerta"),
    ("motivo", "Motivo principal"),
    ("motivo_integrado", "Motivo do alerta integrado"),
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
        return f"{f:.{nd}f}".replace(".", ",")
    except Exception:
        s = str(v).strip()
        return s if s else "—"


def _motivo_em_linguagem_clara(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return "—"
    repl = [
        (r"(?i)\bSIS\s*est[aá]gio\s*", "Classificação operacional "),
        (r"(?i)\bUTCI/proxy\b", "sensação térmica estimada"),
        (r"(?i)\bUTCI\b", "sensação térmica estimada"),
        (r"(?i)\bRisco\s+cumulativo\s*3d\b", "risco de calor acumulado em 3 dias"),
        (r"(?i)\bINMET\b", "alerta oficial de tempo"),
        (r"(?i)\bCemaden\b", "alerta oficial de desastres"),
        (r"(?i)\bTITAN\b", "alertas oficiais integrados"),
        (r"(?i)\bSRAG\b", "síndrome respiratória grave"),
    ]
    out = s
    for pat, to in repl:
        out = re.sub(pat, to, out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ;")
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def _pick_indicadores(row: pd.Series | dict) -> list[dict[str, str]]:
    data = row if isinstance(row, pd.Series) else pd.Series(row)
    out = []
    for col, label in INDICADOR_COLS:
        if col in data.index and pd.notna(data.get(col)):
            valor = _fmt(data.get(col))
            nota = ""
            if col == "ocupacao_leitos_pct" and "fonte_ocupacao" in data.index:
                fonte = str(data.get("fonte_ocupacao") or "")
                if "FALLBACK" in fonte.upper() or "ESTADUAL" in fonte.upper():
                    nota = " (estimado estadual — sem dado local)"
                elif "TEMPO_REAL" in fonte.upper():
                    nota = " (dado local em tempo real)"
            out.append({"campo": col, "rotulo": label, "valor": f"{valor}{nota}"})
    return out


def _orientacoes(nivel: str) -> dict[str, str]:
    return dict(ORIENT.get(_norm_nivel(nivel), ORIENT["cinza"]))


def ensure_municipio_names(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche municipio/regional ausentes a partir do catálogo IBGE/geo local."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    need_name = "municipio" not in out.columns or out["municipio"].isna().all() or (
        out["municipio"].astype(str).str.strip().isin(["", "nan", "None"]).mean() > 0.5
    )
    need_reg = "regional_saude" not in out.columns or out["regional_saude"].isna().all()
    if not need_name and not need_reg:
        return out
    try:
        from sisclima.ingestion.ibge_municipios import load_or_refresh_municipios

        cat = load_or_refresh_municipios()
        if cat is None or cat.empty:
            return out
        cat = cat.copy()
        cat["cod_ibge"] = cat["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        cols = ["cod_ibge"]
        if need_name and "municipio" in cat.columns:
            cols.append("municipio")
        if need_reg and "regional_saude" in cat.columns:
            cols.append("regional_saude")
        if "populacao" in cat.columns and "populacao" not in out.columns:
            cols.append("populacao")
        cat = cat[cols].drop_duplicates("cod_ibge")
        out = out.drop(columns=[c for c in cols if c != "cod_ibge" and c in out.columns], errors="ignore")
        out = out.merge(cat, on="cod_ibge", how="left")
    except Exception:
        pass
    return out


def _coalesce_pred_cols(base: pd.DataFrame) -> pd.DataFrame:
    if base is None or base.empty:
        return base
    out = base.copy()
    candidates = [c for c in ["nivel_predicao_7d", "nivel_predicao_7d_x", "nivel_predicao_7d_y"] if c in out.columns]
    if not candidates:
        return out
    merged = out[candidates[0]]
    for c in candidates[1:]:
        better = out[c].where(~out[c].isna() & ~out[c].astype(str).str.lower().isin(["", "nan", "cinza", "none"]))
        merged = better.combine_first(merged)
    out["nivel_predicao_7d"] = merged
    drop = [c for c in candidates if c != "nivel_predicao_7d"]
    return out.drop(columns=drop, errors="ignore")


def _merge_base(
    resumo: pd.DataFrame,
    alerta_int: pd.DataFrame | None = None,
    pred: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base = resumo.copy() if resumo is not None else pd.DataFrame()
    if base.empty:
        return base
    base = ensure_municipio_names(base)
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
        want = [c for c in ["nivel_predicao_7d", "score_predicao", "horizonte_dias"] if c in pr.columns]
        if want:
            pr2 = pr[["cod_ibge"] + want].drop_duplicates("cod_ibge")
            overlapping = [c for c in want if c in base.columns]
            if overlapping:
                base = base.drop(columns=overlapping, errors="ignore")
            base = base.merge(pr2, on="cod_ibge", how="left")
    base = _coalesce_pred_cols(base)
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
        return {"nivel_predicao_7d": "—", "resumo": "Predição de cerca de 7 dias indisponível nesta rodada."}
    work = _coalesce_pred_cols(df)
    if "nivel_predicao_7d" in work.columns:
        niv = _worst_nivel(work["nivel_predicao_7d"])
        vc = work["nivel_predicao_7d"].map(_norm_nivel).value_counts()
        moda = str(vc.index[0]) if not vc.empty else niv
    else:
        niv, moda = "cinza", "cinza"
    n_up = 0
    if "tendencia_7d" in work.columns:
        n_up = int(work["tendencia_7d"].astype(str).str.lower().isin(["subindo", "alta", "piora"]).sum())
    if niv == "cinza" and n_up > 0 and "nivel" in work.columns:
        niv = _worst_nivel(work["nivel"])
    return {
        "nivel_predicao_7d": niv,
        "icone_predicao": EMOJI.get(niv, "⚪"),
        "municipios_tendencia_alta": str(n_up),
        "resumo": (
            f"Mais grave prevista: {LEVEL_LABEL.get(niv, niv)}; "
            f"mais frequente: {LEVEL_LABEL.get(moda, moda)}. "
            f"Municípios com tendência de piora: {n_up}."
        ),
    }


def _ocupacao_agregada(df: pd.DataFrame, *, escopo: str = "estadual") -> tuple[float | None, str]:
    """Ocupação no escopo: ponderada por leitos; estadual pode cair no IndicaSUS estadual."""
    lo = pd.to_numeric(df.get("leitos_ocupados"), errors="coerce") if "leitos_ocupados" in df.columns else None
    lt = pd.to_numeric(df.get("leitos_total"), errors="coerce") if "leitos_total" in df.columns else None
    if lo is not None and lt is not None and float(lt.fillna(0).sum()) > 0:
        pct = 100.0 * float(lo.fillna(0).sum()) / float(lt.fillna(0).sum())
        return pct, "ponderada por leitos"
    if escopo == "estadual":
        try:
            from sisclima.core.db import read_table, table_exists

            if table_exists("hospital_ocupacao_estado"):
                est = read_table("hospital_ocupacao_estado")
                if est is not None and not est.empty and "ocupacao_pct" in est.columns:
                    return float(pd.to_numeric(est["ocupacao_pct"], errors="coerce").iloc[-1]), "IndicaSUS estadual"
        except Exception:
            pass
    if "ocupacao_leitos_pct" in df.columns:
        return float(pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce").mean()), "média municipal"
    return None, "sem dado"


def _ocupacao_estadual(df: pd.DataFrame) -> tuple[float | None, str]:
    """Compat: ocupa o agregador estadual."""
    return _ocupacao_agregada(df, escopo="estadual")


def _indicadores_agregados(df: pd.DataFrame, *, escopo: str = "estadual") -> list[dict[str, str]]:
    """Indicadores agregados com valor + escala (não usa município sentinela cru)."""
    if df.empty:
        return []
    pico = "estadual" if escopo == "estadual" else "da regional"
    limiar_dist = (
        "pior classificação define o alerta estadual"
        if escopo == "estadual"
        else "pior classificação define o alerta da regional"
    )
    ocup_rotulo = "Ocupação estadual de leitos" if escopo == "estadual" else "Ocupação de leitos na regional"
    inds: list[dict[str, str]] = []
    inds.append(
        {
            "campo": "n_municipios",
            "rotulo": "Municípios no escopo",
            "valor": str(len(df)),
            "escala": "contagem",
            "limiar": "",
        }
    )
    if "nivel_alerta_integrado" in df.columns or "nivel" in df.columns:
        col = "nivel_alerta_integrado" if "nivel_alerta_integrado" in df.columns else "nivel"
        vc = df[col].map(_norm_nivel).value_counts()
        dist = ", ".join(f"{k}:{int(v)}" for k, v in vc.items())
        inds.append(
            {
                "campo": "distribuicao_niveis",
                "rotulo": "Municípios por classificação",
                "valor": dist,
                "escala": "contagem por cor",
                "limiar": limiar_dist,
            }
        )

    if "score" in df.columns:
        score_max = pd.to_numeric(df["score"], errors="coerce").max()
        if pd.notna(score_max):
            inds.append(
                {
                    "campo": "score",
                    "rotulo": "Pontuação operacional (pior município)",
                    "valor": str(int(score_max)),
                    "escala": "0 a 4",
                    "limiar": "0 verde · 1 amarela · 2 laranja · 3 vermelha · 4 roxa",
                }
            )
    if "score_alerta_integrado" in df.columns:
        s2 = pd.to_numeric(df["score_alerta_integrado"], errors="coerce").max()
        if pd.notna(s2):
            inds.append(
                {
                    "campo": "score_alerta_integrado",
                    "rotulo": "Pontuação do alerta integrado (pior município)",
                    "valor": str(int(s2)),
                    "escala": "0 a 4",
                    "limiar": "máximo entre clima, saúde e alertas oficiais",
                }
            )

    for col, rotulo, escala, limiar, agg in [
        ("tmax", f"Temperatura máxima (pico {pico})", "°C", "atenção ≥37 · alerta ≥39 · intensificado ≥41 · pleno ≥43", "max"),
        (
            "utci_proxy",
            f"Sensação térmica estimada (pico {pico})",
            "°C (proxy)",
            "atenção >26 · alerta >32 · intensificado >38 · pleno >46",
            "max",
        ),
        (
            "risco_cumulativo_3d",
            "Risco de calor acumulado em 3 dias (pico)",
            "índice (típico 0–20+)",
            "atenção ≥3 · alerta ≥7 · intensificado ≥12 · pleno ≥18",
            "max",
        ),
        (
            "pressao_calor_pct",
            "Pressão assistencial por calor (pico)",
            "0 a 15 (proxy)",
            "atenção ≥2 · alerta ≥4 · intensificado ≥7 · pleno ≥10",
            "max",
        ),
        (
            "pm25_ugm3",
            "Partículas finas no ar — PM2,5 (pico)",
            "µg/m³",
            "referência OMS diária ~15 µg/m³",
            "max",
        ),
        (
            "incidencia_arbovirus_100k",
            "Incidência de arboviroses (pico) /100 mil",
            "casos / 100 mil",
            "interpretar com tendência",
            "max",
        ),
        (
            "casos_srag",
            "Casos de síndrome respiratória aguda grave (soma)",
            "casos",
            "acompanhar com incidência e ocupação",
            "sum",
        ),
    ]:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() == 0:
            continue
        val = float(s.max()) if agg == "max" else float(s.fillna(0).sum())
        inds.append({"campo": col, "rotulo": rotulo, "valor": _fmt(val), "escala": escala, "limiar": limiar})

    ocup, ocup_fonte = _ocupacao_agregada(df, escopo=escopo)
    if ocup is not None:
        inds.append(
            {
                "campo": "ocupacao_leitos_pct",
                "rotulo": ocup_rotulo,
                "valor": _fmt(ocup),
                "escala": "0 a 100 %",
                "limiar": f"atenção ≥75 · alerta ≥85 · intensificado ≥95 · pleno ≥100 · fonte: {ocup_fonte}",
            }
        )
    if "fonte_ocupacao" in df.columns:
        n_rt = int(df["fonte_ocupacao"].astype(str).str.contains("TEMPO_REAL", case=False, na=False).sum())
        inds.append(
            {
                "campo": "cobertura_ocupacao",
                "rotulo": "Cobertura de ocupação em tempo real",
                "valor": f"{n_rt} de {len(df)} municípios",
                "escala": "municípios com dado local",
                "limiar": "baixa cobertura exige cautela na interpretação hospitalar",
            }
        )
    return inds


def _motivo_agregado(df: pd.DataFrame) -> str:
    for col in ["motivo_integrado", "motivo", "orientacao_leiga"]:
        if col in df.columns:
            s = df[col].dropna().astype(str)
            s = s[~s.str.lower().isin(["", "nan", "none", "—"])]
            if not s.empty:
                return _motivo_em_linguagem_clara(str(s.iloc[0])[:500])
    return "Consolidado a partir da classificação operacional e dos componentes climáticos e assistenciais."


def _top_prioritarios(base: pd.DataFrame, n: int = 8) -> list[dict[str, Any]]:
    sort_cols = ["_rank"] + ([c for c in ["score", "risco_cumulativo_3d"] if c in base.columns])
    top = base.sort_values(sort_cols, ascending=False).head(n)
    out = []
    for _, row in top.iterrows():
        out.append(
            {
                "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                "cod_ibge": str(row.get("cod_ibge") or ""),
                "regional": str(row.get("regional_saude") or "—"),
                "nivel": _norm_nivel(row.get("_nivel") or row.get("nivel")),
                "score": row.get("score"),
                "tmax": row.get("tmax"),
                "utci_proxy": row.get("utci_proxy"),
                "risco_cumulativo_3d": row.get("risco_cumulativo_3d"),
                "ocupacao_leitos_pct": row.get("ocupacao_leitos_pct"),
                "fonte_ocupacao": row.get("fonte_ocupacao"),
                "indicadores": _pick_indicadores(row),
            }
        )
    return out


def build_alertas_multinivel(
    resumo: pd.DataFrame,
    alerta_integrado: pd.DataFrame | None = None,
    predicao_7d: pd.DataFrame | None = None,
    min_level: str = "amarela",
) -> list[dict[str, Any]]:
    """Gera lista de payloads: 1 estadual + N regionais + N municipais (≥min) + Cuiabá."""
    from sisclima.core.config import env

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
    mun_names = base.get("municipio", pd.Series(dtype=str)).dropna().astype(str)
    mun_names = mun_names[~mun_names.str.lower().isin(["", "nan", "none"])]
    top_n = int(env("ALERT_SES_TOP_MUNICIPIOS", "8") or 8)
    est = _build_payload(
        escopo="estadual",
        nivel=niv_est,
        alvo_nome="Estado de Mato Grosso · Secretaria de Estado da Saúde / CIEVS",
        alvo_id="MT",
        municipios=sorted(mun_names.unique().tolist()),
        indicadores=_indicadores_agregados(base, escopo="estadual"),
        predicao=_predicao_from_rows(base),
        motivo=_motivo_agregado(base.sort_values("_rank", ascending=False)),
        fontes=fontes,
    )
    est["municipios_prioritarios"] = _top_prioritarios(base, n=top_n)
    if "nivel" in base.columns:
        est["distribuicao"] = base["nivel"].map(_norm_nivel).value_counts().to_dict()
    else:
        est["distribuicao"] = base["_nivel"].value_counts().to_dict()
    payloads.append(est)

    # 2) Regionais
    if "regional_saude" in base.columns:
        top_reg = int(env("ALERT_REGIONAL_TOP_MUNICIPIOS", "8") or 8)
        for reg, g in base.groupby(base["regional_saude"].fillna("Sem regional").astype(str)):
            niv = _worst_nivel(g["_nivel"])
            g_names = g.get("municipio", pd.Series(dtype=str)).dropna().astype(str)
            g_names = g_names[~g_names.str.lower().isin(["", "nan", "none"])]
            rp = _build_payload(
                escopo="regional",
                nivel=niv,
                alvo_nome=str(reg),
                alvo_id=str(reg),
                municipios=sorted(g_names.unique().tolist()),
                indicadores=_indicadores_agregados(g, escopo="regional"),
                predicao=_predicao_from_rows(g),
                motivo=_motivo_agregado(g.sort_values("_rank", ascending=False)),
                fontes=fontes,
            )
            rp["municipios_prioritarios"] = _top_prioritarios(g, n=top_reg)
            rp["distribuicao"] = g["_nivel"].value_counts().to_dict()
            payloads.append(rp)

    # 3) Municipais
    crit = base[base["_rank"] >= min_rank].copy()
    for _, row in crit.iterrows():
        mun = str(row.get("municipio") or row.get("cod_ibge") or "Município")
        mp = _build_payload(
            escopo="municipal",
            nivel=row.get("_nivel"),
            alvo_nome=mun,
            alvo_id=str(row.get("cod_ibge") or mun),
            municipios=[mun],
            indicadores=_pick_indicadores(row),
            predicao={
                "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                "resumo": (
                    f"Predição em cerca de 7 dias: "
                    f"{LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}"
                ),
            },
            motivo=_motivo_em_linguagem_clara(str(row.get("motivo_integrado") or row.get("motivo") or "—")),
            fontes=fontes,
        )
        mp["regional"] = str(row.get("regional_saude") or "—")
        mp["score"] = row.get("score")
        mp["tmax"] = row.get("tmax")
        mp["utci_proxy"] = row.get("utci_proxy")
        mp["risco_cumulativo_3d"] = row.get("risco_cumulativo_3d")
        mp["ocupacao_leitos_pct"] = row.get("ocupacao_leitos_pct")
        mp["fonte_ocupacao"] = row.get("fonte_ocupacao")
        mp["pressao_calor_pct"] = row.get("pressao_calor_pct")
        mp["pm25_ugm3"] = row.get("pm25_ugm3")
        payloads.append(mp)

    # 4) Cuiabá
    cui = base[base["cod_ibge"].astype(str) == CUIABA_IBGE] if "cod_ibge" in base.columns else pd.DataFrame()
    if cui.empty and "municipio" in base.columns:
        cui = base[base["municipio"].astype(str).str.lower().str.contains("cuiab", na=False)]
    if not cui.empty:
        row = cui.sort_values("_rank", ascending=False).iloc[0]
        cp = _build_payload(
            escopo="cuiaba",
            nivel=row.get("_nivel"),
            alvo_nome="Cuiabá",
            alvo_id=CUIABA_IBGE,
            municipios=["Cuiabá"],
            indicadores=_pick_indicadores(row),
            predicao={
                "nivel_predicao_7d": _norm_nivel(row.get("nivel_predicao_7d")),
                "icone_predicao": EMOJI.get(_norm_nivel(row.get("nivel_predicao_7d")), "⚪"),
                "resumo": (
                    f"Predição em cerca de 7 dias: "
                    f"{LEVEL_LABEL.get(_norm_nivel(row.get('nivel_predicao_7d')), '—')}"
                ),
            },
            motivo=_motivo_em_linguagem_clara(
                str(row.get("motivo_integrado") or row.get("motivo") or "Alerta dedicado Vigidesastre Cuiabá.")
            ),
            fontes=fontes + ["Vigidesastre Cuiabá"],
        )
        cp["remetente"] = "VIGIDESASTRE CUIABÁ"
        cp["regional"] = str(row.get("regional_saude") or "Cuiabá")
        cp["score"] = row.get("score")
        cp["tmax"] = row.get("tmax")
        cp["utci_proxy"] = row.get("utci_proxy")
        cp["risco_cumulativo_3d"] = row.get("risco_cumulativo_3d")
        cp["ocupacao_leitos_pct"] = row.get("ocupacao_leitos_pct")
        cp["fonte_ocupacao"] = row.get("fonte_ocupacao")
        cp["pressao_calor_pct"] = row.get("pressao_calor_pct")
        cp["pm25_ugm3"] = row.get("pm25_ugm3")
        payloads.append(cp)

    return payloads


def payloads_to_dataframe(payloads: list[dict[str, Any]]) -> pd.DataFrame:
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
                "n_prioritarios": len(p.get("municipios_prioritarios") or []),
                "gerado_em": p.get("gerado_em"),
            }
        )
    return pd.DataFrame(rows)


def render_payload_markdown(p: dict[str, Any]) -> str:
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
    from sisclima.core.db import write_df

    df = payloads_to_dataframe(payloads)
    if df.empty:
        return 0
    write_df(df, table, if_exists="replace")
    return len(df)
