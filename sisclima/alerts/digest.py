# -*- coding: utf-8 -*-
"""Boletins CIEVS em 4 camadas: SES · Regionais · Municipais · Vigidesastre Cuiabá."""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from typing import Any

import pandas as pd

from sisclima.alerts.notifier import send_email, send_telegram
from sisclima.core.config import as_bool, env
from sisclima.core.db import db_conn, execute, fetchone, read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.engines.alertas_multinivel import (
    CUIABA_IBGE,
    EMOJI,
    LEVEL_LABEL,
    ORIENT,
    build_alertas_multinivel,
    ensure_municipio_names,
    persist_payloads,
)
from sisclima.engines.stages import STAGE_ORDER
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

ICON = {
    "titulo": "🌡️",
    "estado": "🏛️",
    "regional": "🗺️",
    "municipal": "📍",
    "cuiaba": "🏙️",
    "indicadores": "📊",
    "predicao": "🔮",
    "motivo": "⚠️",
    "prioridade": "🎯",
    "orient_gestor": "👔",
    "orient_prof": "🩺",
    "orient_pop": "👥",
    "ia": "🤖",
    "rodape": "✅",
    "dist": "📈",
}

# Rótulos em linguagem clara (evitar siglas no texto enviado)
PLAIN_LABELS: dict[str, str] = {
    "nivel": "Classificação operacional",
    "nivel_alerta_integrado": "Classificação integrada (clima + saúde + alertas oficiais)",
    "score": "Pontuação operacional (0 a 4)",
    "score_alerta_integrado": "Pontuação do alerta integrado",
    "tmax": "Temperatura máxima (°C)",
    "utci_proxy": "Sensação térmica estimada (°C)",
    "risco_cumulativo_3d": "Risco de calor acumulado em 3 dias",
    "ocupacao_leitos_pct": "Ocupação de leitos hospitalares (%)",
    "pressao_calor_pct": "Pressão assistencial estimada (%)",
    "indice_pressao_saude": "Índice de pressão em saúde (0 a 100)",
    "semaforo_pressao": "Semáforo de pressão em saúde",
    "pm25_ugm3": "Partículas finas no ar — PM2,5 (µg/m³)",
    "indice_saturacao_solo": "Índice de saturação do solo (0 a 100)",
    "classe_saturacao_solo": "Situação do solo",
    "incidencia_arbovirus_100k": "Incidência de arboviroses por 100 mil habitantes",
    "zscore_arbovirus": "Desvio epidêmico de arboviroses",
    "casos_arbovirus_7d": "Casos de arboviroses nos últimos 7 dias",
    "casos_dengue_7d": "Casos de dengue nos últimos 7 dias",
    "casos_srag": "Casos de síndrome respiratória aguda grave",
    "incidencia_srag_100k": "Incidência de síndrome respiratória grave por 100 mil",
    "letalidade_pct": "Letalidade (%)",
    "indice_tensao_climatica": "Índice de tensão climática (0 a 100)",
    "indice_carga_saude": "Índice de carga em saúde (0 a 100)",
    "indice_vigilancia_integrada": "Índice de vigilância integrada (0 a 100)",
    "indice_prioridade_global": "Prioridade global de atenção (0 a 100)",
    "faixa_prioridade_global": "Faixa de prioridade global",
    "indice_adaptacao_climatica": "Índice de adaptação climática (0 a 100)",
    "tendencia_7d": "Tendência prevista para ~7 dias",
    "nivel_predicao_7d": "Classificação prevista para ~7 dias",
    "componente_dominante": "Fator que mais elevou o alerta",
    "motivo": "Motivo principal",
    "motivo_integrado": "Motivo do alerta integrado",
    "orientacao_leiga": "Orientação em linguagem simples",
    "populacao": "População estimada",
    "regional_saude": "Regional de Saúde",
    "n_municipios": "Municípios no escopo",
    "distribuicao_niveis": "Municípios por classificação",
}

IND_ICON = {
    "n_municipios": "🏘️",
    "distribuicao_niveis": "📈",
    "nivel": "🚦",
    "nivel_alerta_integrado": "🛰️",
    "score": "🔢",
    "score_alerta_integrado": "🔢",
    "tmax": "☀️",
    "utci_proxy": "🥵",
    "risco_cumulativo_3d": "🔥",
    "ocupacao_leitos_pct": "🛏️",
    "pressao_calor_pct": "🏥",
    "indice_pressao_saude": "🏥",
    "pm25_ugm3": "💨",
    "indice_saturacao_solo": "💧",
    "incidencia_arbovirus_100k": "🦟",
    "casos_arbovirus_7d": "🦟",
    "casos_dengue_7d": "🦟",
    "casos_srag": "🫁",
    "incidencia_srag_100k": "🫁",
    "indice_tensao_climatica": "🌡️",
    "indice_carga_saude": "💊",
    "indice_vigilancia_integrada": "👁️",
    "indice_prioridade_global": "🎯",
    "tendencia_7d": "📉",
    "nivel_predicao_7d": "🔮",
    "componente_dominante": "🧩",
    "populacao": "👥",
}

DETAIL_FIELDS = [
    "nivel",
    "nivel_alerta_integrado",
    "score",
    "indice_prioridade_global",
    "faixa_prioridade_global",
    "indice_vigilancia_integrada",
    "indice_tensao_climatica",
    "indice_carga_saude",
    "indice_pressao_saude",
    "semaforo_pressao",
    "tmax",
    "utci_proxy",
    "risco_cumulativo_3d",
    "tendencia_7d",
    "nivel_predicao_7d",
    "ocupacao_leitos_pct",
    "pressao_calor_pct",
    "pm25_ugm3",
    "indice_saturacao_solo",
    "casos_arbovirus_7d",
    "casos_dengue_7d",
    "incidencia_arbovirus_100k",
    "casos_srag",
    "incidencia_srag_100k",
    "componente_dominante",
    "motivo_integrado",
    "motivo",
    "populacao",
    "regional_saude",
]

ORIENT_SES = {
    "verde": (
        "Manter monitoramento estadual de rotina; acompanhar o painel; "
        "atualizar estoques estratégicos e planos regionais."
    ),
    "amarela": (
        "Acionar sala de situação estadual; boletim diário às Regionais de Saúde; "
        "checar autonomia de insumos e comunicação de risco coordenada."
    ),
    "laranja": (
        "Instalar centro de operações parcial na Secretaria de Estado da Saúde; "
        "articular assistência, vigilância e comunicação; "
        "priorizar regionais e municípios críticos e pontos de hidratação e resfriamento."
    ),
    "vermelha": (
        "Centro de operações pleno estadual; reuniões operacionais pelo menos duas vezes ao dia; "
        "priorizar leitos e regulação; apoiar regionais críticas e comunicação pública coordenada."
    ),
    "roxa": (
        "Comando unificado e apoio entre entes federativos; redistribuição emergencial de insumos e leitos; "
        "comunicação de crise e registro contínuo para o pós-evento."
    ),
    "cinza": "Priorizar qualidade de dados antes de comunicação oficial definitiva.",
}

ORIENT_REGIONAL = {
    "verde": "Manter articulação com municípios; acompanhar indicadores e boletins oficiais.",
    "amarela": (
        "Ativar acompanhamento diário da regional; apoiar municípios em atenção; "
        "checar insumos e fluxos de regulação."
    ),
    "laranja": (
        "Sala de situação regional; apoiar municípios em alerta; "
        "abrir ou expandir pontos de hidratação e reforçar comunicação."
    ),
    "vermelha": (
        "Resposta intensificada na regional; priorizar municípios em classificação vermelha ou roxa; "
        "articular leitos, transporte e apoio assistencial."
    ),
    "roxa": (
        "Mobilização plena da regional; comando conjunto com a Secretaria de Estado da Saúde; "
        "redistribuir apoio aos municípios sob maior pressão."
    ),
    "cinza": "Reforçar coleta e validação de dados municipais na regional.",
}

# Escalas/limiares oficiais para exibir ao lado do valor no alerta SES
INDICATOR_META: dict[str, dict[str, str]] = {
    "score": {
        "escala": "0 a 4",
        "limiar": "0 verde · 1 amarela · 2 laranja · 3 vermelha · 4 roxa",
    },
    "score_alerta_integrado": {
        "escala": "0 a 4",
        "limiar": "máximo entre clima, saúde e alertas oficiais",
    },
    "tmax": {
        "escala": "°C",
        "limiar": "atenção ≥37 · alerta ≥39 · intensificado ≥41 · pleno ≥43",
    },
    "utci_proxy": {
        "escala": "°C (proxy operacional)",
        "limiar": "atenção >26 · alerta >32 · intensificado >38 · pleno >46",
    },
    "risco_cumulativo_3d": {
        "escala": "índice contínuo (típico 0–20+)",
        "limiar": "atenção ≥3 · alerta ≥7 · intensificado ≥12 · pleno ≥18",
    },
    "ocupacao_leitos_pct": {
        "escala": "0 a 100 %",
        "limiar": "atenção ≥75 · alerta ≥85 · intensificado ≥95 · pleno ≥100",
    },
    "pressao_calor_pct": {
        "escala": "0 a 15 (proxy) ou % de atendimentos",
        "limiar": "atenção ≥2 · alerta ≥4 · intensificado ≥7 · pleno ≥10",
    },
    "pm25_ugm3": {
        "escala": "µg/m³",
        "limiar": "referência diária OMS ~15 µg/m³",
    },
    "indice_pressao_saude": {
        "escala": "0 a 100",
        "limiar": "baixa ≤39 · moderada ≤69 · alta ≥70",
    },
    "indice_vigilancia_integrada": {
        "escala": "0 a 100",
        "limiar": "baixa ≤30 · moderada ≤60 · alta ≤80 · muito alta >80",
    },
    "indice_prioridade_global": {
        "escala": "0 a 100",
        "limiar": "quanto maior, maior a prioridade de atenção",
    },
    "indice_tensao_climatica": {
        "escala": "0 a 100",
        "limiar": "composto de calor, sensação térmica e seca",
    },
    "indice_carga_saude": {
        "escala": "0 a 100",
        "limiar": "composto de agravos, ar e pressão assistencial",
    },
}


def _fmt_indicator_line(ind: dict[str, Any]) -> str:
    icon = ind.get("icone") or IND_ICON.get(str(ind.get("campo") or ""), "•")
    rotulo = ind.get("rotulo") or _plain_label(str(ind.get("campo") or ""))
    valor = ind.get("valor")
    campo = str(ind.get("campo") or "")
    meta = INDICATOR_META.get(campo, {})
    escala = ind.get("escala") or meta.get("escala")
    limiar = ind.get("limiar") or meta.get("limiar")
    line = f"{icon} {rotulo}: {valor}"
    if escala:
        line += f"  ·  escala {escala}"
    if limiar:
        line += f"  ·  limiares: {limiar}"
    return line


def build_orientacoes_ses_setores(payload: dict[str, Any], resumo: pd.DataFrame | None = None) -> dict[str, str]:
    """Orientações personalizadas por setor da SES, ancoradas no cenário da rodada."""
    nivel = _norm_level(payload.get("nivel"))
    dist = payload.get("distribuicao") or {}
    n_rox = int(dist.get("roxa", 0) or 0)
    n_verm = int(dist.get("vermelha", 0) or 0)
    n_lar = int(dist.get("laranja", 0) or 0)
    n_crit = n_rox + n_verm
    prior = payload.get("municipios_prioritarios") or []
    top_names = ", ".join(str(p.get("municipio")) for p in prior[:5] if p.get("municipio"))
    pred = payload.get("predicao") or {}
    n_up = pred.get("municipios_tendencia_alta") or "—"

    # leituras rápidas do resumo
    utci_max = risco_max = ocup = pm = arbo = None
    if resumo is not None and not resumo.empty:
        if "utci_proxy" in resumo.columns:
            utci_max = pd.to_numeric(resumo["utci_proxy"], errors="coerce").max()
        if "risco_cumulativo_3d" in resumo.columns:
            risco_max = pd.to_numeric(resumo["risco_cumulativo_3d"], errors="coerce").max()
        if "pm25_ugm3" in resumo.columns:
            pm = pd.to_numeric(resumo["pm25_ugm3"], errors="coerce").max()
        if "incidencia_arbovirus_100k" in resumo.columns:
            arbo = pd.to_numeric(resumo["incidencia_arbovirus_100k"], errors="coerce").max()
    for ind in payload.get("indicadores") or []:
        if ind.get("campo") == "ocupacao_leitos_pct":
            try:
                ocup = float(str(ind.get("valor")).replace(".", "").replace(",", ".")) if "," in str(ind.get("valor")) else float(str(ind.get("valor")).replace(",", "."))
            except Exception:
                ocup = None

    cievs = (
        f"Manter sala de situação ativa (classificação estadual {LEVEL_LABEL.get(nivel, nivel)}). "
        f"Priorizar articulação com {n_crit} município(s) em vermelha/roxa e {n_lar} em laranja. "
        f"Foco imediato: {top_names or 'municípios de maior pontuação'}."
    )
    hospitalar = (
        f"Verificar capacidade de leitos e plano de contingência hospitalar nas regionais dos municípios prioritários"
        f"{' (ocupação estadual atual ~' + f'{ocup:.1f}'.replace('.', ',') + '%)' if ocup is not None else ''}. "
        "Avaliar expansão de leitos clínicos, regulação interestadual se necessário e ativação de leitos de retaguarda."
    )
    if ocup is not None and ocup < 60:
        hospitalar += (
            " Atenção: a ocupação estadual ainda não está no limiar de alerta (≥75%); "
            "monitorar tendência e filas de regulação, não apenas o percentual médio."
        )
    saf = (
        "Checar estoque estadual e regional de soro de reidratação oral, "
        "soro endovenoso, antitérmicos e insumos para atendimento de hipertermia e desidratação"
    )
    if arbo is not None and arbo >= 10:
        saf += "; reforçar também insumos para manejo de dengue e outras arboviroses (teste rápido, hidratação venosa)."
    else:
        saf += "."
    trabalhador = (
        "Orientar troca ou flexibilização de jornadas em exposição solar "
        f"{'(sensação térmica pico ~' + f'{utci_max:.1f}'.replace('.', ',') + ' °C)' if utci_max is not None else ''}; "
        "priorizar trabalhadores rurais, da construção civil, de coleta e de serviços externos; "
        "pausas, hidratação e áreas sombreadas ou climatizadas."
    )
    aps = (
        "Intensificar busca ativa de idosos, gestantes, crianças e pessoas em situação de rua "
        "nos municípios prioritários; orientar hidratação e identificação precoce de sinais de gravidade."
    )
    amb = (
        "Reforçar eliminação de criadouros e comunicação de risco para dengue "
        f"{'diante da incidência elevada observada' if arbo is not None and arbo >= 10 else 'como medida preventiva no calor'}; "
        + (f"acompanhar qualidade do ar (PM2,5 pico ~{pm:.0f} µg/m³)." if pm is not None else "acompanhar qualidade do ar.")
    )
    comunicacao = (
        "Publicar boletim unificado às Regionais de Saúde; "
        f"mensagens à população sobre hidratação, evitar pico de calor e procurar atendimento; "
        f"antecipar comunicação para os {n_up} municípios com tendência de piora em cerca de 7 dias."
    )
    regulacao = (
        "Mapear vagas e fluxos para os municípios prioritários; "
        "garantir retaguarda para hipertermia, desidratação grave e descompensações cardiorrespiratórias."
    )
    return {
        "comando_cievs": cievs,
        "gestao_hospitalar": hospitalar,
        "assistencia_farmaceutica": saf,
        "saude_trabalhador": trabalhador,
        "atencao_primaria": aps,
        "vigilancia_ambiental": amb,
        "comunicacao_risco": comunicacao,
        "regulacao": regulacao,
        "sintese_gestao": ORIENT_SES.get(nivel, ORIENT_SES["cinza"]),
    }


def _norm_level(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in ("amarelo",):
        s = "amarela"
    if s in ("vermelho",):
        s = "vermelha"
    if s in ("roxo",):
        s = "roxa"
    return s if s in EMOJI else "cinza"


def min_level_ok(nivel: str, min_level: str | None = None) -> bool:
    floor = _norm_level(min_level or env("ALERT_MIN_LEVEL", "laranja"))
    return STAGE_ORDER.get(_norm_level(nivel), -1) >= STAGE_ORDER.get(floor, 2)


def _plain_label(campo: str) -> str:
    return PLAIN_LABELS.get(campo, campo.replace("_", " ").capitalize())


def _fmt_val(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
        return "sem dado nesta rodada"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            fv = float(v)
            if abs(fv - round(fv)) < 1e-9:
                return f"{int(round(fv)):,}".replace(",", ".")
            return f"{fv:.1f}".replace(".", ",")
        except Exception:
            pass
    s = str(v).strip()
    # traduz tendências comuns
    low = s.lower()
    mapping = {
        "subindo": "tendência de piora",
        "alta": "tendência de piora",
        "piora": "tendência de piora",
        "estavel": "tendência estável",
        "estável": "tendência estável",
        "descendo": "tendência de melhora",
        "queda": "tendência de melhora",
        "verde": "Verde",
        "amarela": "Amarela",
        "laranja": "Laranja",
        "vermelha": "Vermelha",
        "roxa": "Roxa",
    }
    return mapping.get(low, s)


def _ensure_digest_table() -> None:
    with db_conn() as conn:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS alertas_digest_controle (
                id INTEGER PRIMARY KEY,
                fingerprint TEXT,
                nivel TEXT,
                enviado_em TEXT,
                canais TEXT,
                status TEXT
            )
            """,
        )


def _last_digest() -> dict | None:
    if not table_exists("alertas_digest_controle"):
        return None
    with db_conn() as conn:
        row = fetchone(
            conn,
            "SELECT fingerprint, nivel, enviado_em, status FROM alertas_digest_controle WHERE id=1",
        )
        return dict(row) if row else None


def _cooldown_ok(hours: float | None = None) -> bool:
    last = _last_digest()
    if not last or not last.get("enviado_em"):
        return True
    try:
        prev = pd.to_datetime(last["enviado_em"], errors="coerce")
        if pd.isna(prev):
            return True
        hrs = float(hours if hours is not None else env("ALERT_DIGEST_COOLDOWN_HOURS", "6") or 6)
        age_h = (pd.Timestamp.now(tz=None) - prev.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600.0
        return age_h >= hrs
    except Exception:
        return True


def _ai_orientacao(payload: dict[str, Any], publico: str) -> str | None:
    if not (
        as_bool(env("USE_AI_ALERT_TEXT", "false"), False)
        or as_bool(env("USE_LLM_REPORT", "false"), False)
    ):
        return None
    try:
        from sisclima.ai.report_generator import maybe_llm_report

        publico_txt = {
            "ses": (
                "gestão estadual da Secretaria de Estado da Saúde / CIEVS — "
                "direcionar bullets por setor: CIEVS, gestão hospitalar, assistência farmacêutica, "
                "saúde do trabalhador, atenção primária, vigilância ambiental e comunicação de risco"
            ),
            "regional": "gestão da Regional de Saúde (apoio aos municípios da jurisdição)",
            "municipal": "gestão municipal, profissionais de saúde e população",
            "cuiaba": "Vigidesastre Cuiabá e sala de situação municipal",
        }.get(publico, publico)
        ctx = {
            "tarefa": f"orientacao_alerta_{publico}",
            "instrucao": (
                f"Escreva EXATAMENTE 8 bullets operacionais para {publico_txt}. "
                "Português claro, sem siglas desnecessárias, sem inventar números. "
                "Formato: cada linha começa com '- '. Sem títulos, sem markdown, sem introdução. "
                "Complete todos os 8 bullets."
            ),
            "alerta": {
                "escopo": payload.get("escopo"),
                "alvo": payload.get("alvo_nome"),
                "nivel": payload.get("nivel"),
                "nivel_rotulo": payload.get("nivel_rotulo"),
                "motivo": str(payload.get("motivo") or "")[:400],
                "indicadores_resumo": [
                    {"rotulo": i.get("rotulo"), "valor": i.get("valor"), "escala": i.get("escala")}
                    for i in (payload.get("indicadores") or [])[:10]
                ],
                "predicao": (payload.get("predicao") or {}).get("resumo"),
                "municipios_prioritarios": [
                    {"municipio": m.get("municipio"), "regional": m.get("regional"), "nivel": m.get("nivel")}
                    for m in (payload.get("municipios_prioritarios") or [])[:8]
                ],
                "distribuicao": payload.get("distribuicao"),
                "orientacoes_setores": payload.get("orientacoes_setores"),
            },
        }
        txt = maybe_llm_report(ctx)
        if not txt:
            return None
        txt = re.sub(r"^```\w*\n?", "", txt.strip())
        txt = re.sub(r"\n?```$", "", txt.strip())
        return txt.strip()[:4000]
    except Exception as exc:  # noqa: BLE001
        log.warning("IA indisponível (%s): %s", publico, exc)
        return None


def _row_indicators(row: pd.Series | dict, fields: list[str] | None = None) -> list[dict[str, str]]:
    data = row if isinstance(row, pd.Series) else pd.Series(row)
    out = []
    for campo in fields or DETAIL_FIELDS:
        if campo not in data.index:
            continue
        val = data.get(campo)
        if val is None or (isinstance(val, float) and pd.isna(val)) or pd.isna(val):
            continue
        if str(val).strip() in {"", "nan", "None", "—"}:
            continue
        out.append(
            {
                "campo": campo,
                "rotulo": _plain_label(campo),
                "valor": _fmt_val(val),
                "icone": IND_ICON.get(campo, "•"),
            }
        )
    return out


def _dist_niveis(df: pd.DataFrame) -> dict[str, int]:
    if df is None or df.empty or "nivel" not in df.columns:
        return {}
    return df["nivel"].map(_norm_level).value_counts().to_dict()


def _dist_text(dist: dict[str, int]) -> str:
    order = ["roxa", "vermelha", "laranja", "amarela", "verde", "cinza"]
    parts = []
    for k in order:
        if k in dist:
            parts.append(f"{EMOJI.get(k, '⚪')} {LEVEL_LABEL.get(k, k)}: {int(dist[k])} município(s)")
    for k, v in dist.items():
        if k not in order:
            parts.append(f"{k}: {int(v)}")
    return "\n".join(parts) if parts else "Sem distribuição nesta rodada."


def _top_municipios(df: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    top = df.copy()
    sort_cols = [c for c in ["indice_prioridade_global", "score", "indice_vigilancia_integrada", "risco_cumulativo_3d"] if c in top.columns]
    for c in sort_cols:
        top[c] = pd.to_numeric(top[c], errors="coerce")
    if sort_cols:
        top = top.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    elif "nivel" in top.columns:
        top["_rk"] = top["nivel"].map(lambda x: STAGE_ORDER.get(_norm_level(x), -1))
        top = top.sort_values("_rk", ascending=False)
    return top.head(n)


def build_four_layer_pack(resumo: pd.DataFrame | None = None) -> tuple[dict[str, list[dict[str, Any]]], str, dict]:
    """Monta os 4 tipos de alerta."""
    resumo = resumo if resumo is not None else read_table("resumo_municipal_atual")
    resumo = ensure_municipio_names(resumo)
    alerta = read_table("alerta_integrado_sis_titan") if table_exists("alerta_integrado_sis_titan") else pd.DataFrame()
    pred = (
        read_table("predicao_calor_7d_municipal_v6")
        if table_exists("predicao_calor_7d_municipal_v6")
        else pd.DataFrame()
    )
    # payloads base (orientações padrão + estrutura)
    base_payloads = build_alertas_multinivel(
        resumo,
        alerta if not alerta.empty else None,
        pred if not pred.empty else None,
        min_level="verde",  # gera todos; filtramos no envio se necessário
    )
    try:
        persist_payloads(base_payloads)
    except Exception as exc:  # noqa: BLE001
        log.warning("persist alertas_multinivel: %s", exc)

    dist = _dist_niveis(resumo)
    nivel_estado = "cinza"
    est_base = next((p for p in base_payloads if p.get("escopo") == "estadual"), {})
    if est_base:
        nivel_estado = _norm_level(est_base.get("nivel"))

    # ---- 1) SES ----
    top = _top_municipios(resumo, n=int(env("ALERT_SES_TOP_MUNICIPIOS", "15") or 15))
    priorizados = est_base.get("municipios_prioritarios") or []
    if not priorizados:
        for _, row in top.iterrows():
            priorizados.append(
                {
                    "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                    "regional": str(row.get("regional_saude") or "—"),
                    "nivel": _norm_level(row.get("nivel")),
                    "indicadores": _row_indicators(row),
                }
            )
    else:
        # reforça indicadores com rótulos claros
        for m in priorizados:
            if not m.get("indicadores") and resumo is not None and not resumo.empty:
                hit = resumo[resumo["cod_ibge"].astype(str) == str(m.get("cod_ibge"))] if "cod_ibge" in resumo.columns else pd.DataFrame()
                if hit.empty and "municipio" in resumo.columns:
                    hit = resumo[resumo["municipio"].astype(str) == str(m.get("municipio"))]
                if not hit.empty:
                    m["indicadores"] = _row_indicators(hit.iloc[0])

    ses = {
        "escopo": "estadual",
        "tipo": "ses",
        "alvo_nome": "Estado de Mato Grosso · Secretaria de Estado da Saúde / CIEVS",
        "alvo_id": "MT-SES",
        "nivel": nivel_estado,
        "nivel_rotulo": LEVEL_LABEL.get(nivel_estado, nivel_estado),
        "icone": EMOJI.get(nivel_estado, "⚪"),
        "titulo": (
            f"{ICON['estado']} {EMOJI.get(nivel_estado, '⚪')} ALERTA ESTADUAL · SES-MT / CIEVS · "
            f"{LEVEL_LABEL.get(nivel_estado, nivel_estado)}"
        ),
        "gerado_em": now_iso(),
        "distribuicao": dist,
        "distribuicao_texto": _dist_text(dist),
        "n_municipios": int(len(resumo)) if resumo is not None else int(est_base.get("n_municipios") or 0),
        "municipios_prioritarios": priorizados,
        "motivo": est_base.get("motivo") or "—",
        "predicao": est_base.get("predicao") or {},
        "indicadores": est_base.get("indicadores") or [],
        "orientacao_gestao_ses": ORIENT_SES.get(nivel_estado, ORIENT_SES["cinza"]),
    }
    ses["orientacoes_setores"] = build_orientacoes_ses_setores(ses, resumo)
    # IA só nas camadas que serão enviadas (custo/tempo)
    layers_ai = {
        x.strip().lower()
        for x in (env("ALERT_LAYERS", "ses,regionais,municipais,cuiaba") or "ses").split(",")
        if x.strip()
    }
    if "ses" in layers_ai:
        ses["orientacao_ia"] = _ai_orientacao(ses, "ses")
    else:
        ses["orientacao_ia"] = None

    # ---- 2) Regionais (todas) ----
    regionais: list[dict[str, Any]] = []
    if resumo is not None and not resumo.empty and "regional_saude" in resumo.columns:
        for reg, g in resumo.groupby(resumo["regional_saude"].fillna("Sem regional").astype(str)):
            niv = "cinza"
            if "nivel" in g.columns:
                ranks = g["nivel"].map(lambda x: STAGE_ORDER.get(_norm_level(x), -1))
                if ranks.notna().any():
                    niv = _norm_level(g.loc[ranks.idxmax(), "nivel"])
            mun_lines = []
            gg = _top_municipios(g, n=30)
            for _, row in gg.iterrows():
                mun_lines.append(
                    {
                        "municipio": str(row.get("municipio") or "—"),
                        "nivel": _norm_level(row.get("nivel")),
                        "indicadores": _row_indicators(
                            row,
                            [
                                "nivel",
                                "indice_prioridade_global",
                                "tmax",
                                "utci_proxy",
                                "risco_cumulativo_3d",
                                "ocupacao_leitos_pct",
                                "indice_pressao_saude",
                                "tendencia_7d",
                                "casos_arbovirus_7d",
                            ],
                        ),
                    }
                )
            rp = {
                "escopo": "regional",
                "tipo": "regional",
                "alvo_nome": str(reg),
                "alvo_id": str(reg),
                "nivel": niv,
                "nivel_rotulo": LEVEL_LABEL.get(niv, niv),
                "icone": EMOJI.get(niv, "⚪"),
                "titulo": f"{ICON['regional']} ALERTA REGIONAL · {reg} · {LEVEL_LABEL.get(niv, niv)}",
                "gerado_em": now_iso(),
                "n_municipios": len(g),
                "distribuicao": _dist_niveis(g),
                "distribuicao_texto": _dist_text(_dist_niveis(g)),
                "municipios_jurisdicao": mun_lines,
                "motivo": _fmt_val(g.sort_values("score", ascending=False).iloc[0].get("motivo")) if "score" in g.columns and not g.empty else "—",
                "orientacao_gestao_regional": ORIENT_REGIONAL.get(niv, ORIENT_REGIONAL["cinza"]),
                "indicadores": _row_indicators(_top_municipios(g, 1).iloc[0]) if not g.empty else [],
            }
            # IA só para regionais em alerta alto e se a camada estiver ativa
            if (
                ("regionais" in layers_ai or "regional" in layers_ai)
                and STAGE_ORDER.get(niv, -1) >= STAGE_ORDER.get("laranja", 2)
            ):
                rp["orientacao_ia"] = _ai_orientacao(rp, "regional")
            regionais.append(rp)
        regionais = sorted(regionais, key=lambda p: STAGE_ORDER.get(p.get("nivel", "cinza"), -1), reverse=True)

    # ---- 3) Municipais (todos) ----
    municipais: list[dict[str, Any]] = []
    if resumo is not None and not resumo.empty:
        for _, row in resumo.iterrows():
            niv = _norm_level(row.get("nivel"))
            o = ORIENT.get(niv, ORIENT["cinza"])
            municipais.append(
                {
                    "escopo": "municipal",
                    "tipo": "municipal",
                    "alvo_nome": str(row.get("municipio") or row.get("cod_ibge") or "Município"),
                    "alvo_id": str(row.get("cod_ibge") or ""),
                    "regional": str(row.get("regional_saude") or "—"),
                    "nivel": niv,
                    "nivel_rotulo": LEVEL_LABEL.get(niv, niv),
                    "icone": EMOJI.get(niv, "⚪"),
                    "titulo": (
                        f"{ICON['municipal']} ALERTA MUNICIPAL · {row.get('municipio')} · "
                        f"{LEVEL_LABEL.get(niv, niv)}"
                    ),
                    "gerado_em": now_iso(),
                    "indicadores": _row_indicators(row),
                    "motivo": _fmt_val(row.get("motivo_integrado") or row.get("motivo")),
                    "orientacoes": {
                        "gestor": o.get("gestor"),
                        "profissional": o.get("profissional"),
                        "populacao": o.get("populacao"),
                    },
                    "predicao": {
                        "nivel_predicao_7d": _norm_level(row.get("nivel_predicao_7d")),
                        "resumo": (
                            f"Classificação prevista em cerca de 7 dias: "
                            f"{LEVEL_LABEL.get(_norm_level(row.get('nivel_predicao_7d')), 'sem previsão')}"
                        ),
                        "icone_predicao": EMOJI.get(_norm_level(row.get("nivel_predicao_7d")), "⚪"),
                    },
                }
            )
        municipais = sorted(municipais, key=lambda p: STAGE_ORDER.get(p.get("nivel", "cinza"), -1), reverse=True)

    # ---- 4) Vigidesastre Cuiabá ----
    cuiaba = None
    if resumo is not None and not resumo.empty:
        cui = pd.DataFrame()
        if "cod_ibge" in resumo.columns:
            cui = resumo[resumo["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False) == CUIABA_IBGE]
        if cui.empty and "municipio" in resumo.columns:
            cui = resumo[resumo["municipio"].astype(str).str.lower().str.contains("cuiab", na=False)]
        if not cui.empty:
            row = cui.iloc[0]
            niv = _norm_level(row.get("nivel"))
            o = ORIENT.get(niv, ORIENT["cinza"])
            cuiaba = {
                "escopo": "cuiaba",
                "tipo": "vigidesastre_cuiaba",
                "remetente": "VIGIDESASTRE CUIABÁ",
                "alvo_nome": "Cuiabá",
                "alvo_id": CUIABA_IBGE,
                "nivel": niv,
                "nivel_rotulo": LEVEL_LABEL.get(niv, niv),
                "icone": EMOJI.get(niv, "⚪"),
                "titulo": (
                    f"{ICON['cuiaba']} VIGIDESASTRE CUIABÁ · Relatório municipal · "
                    f"{LEVEL_LABEL.get(niv, niv)}"
                ),
                "gerado_em": now_iso(),
                "indicadores": _row_indicators(row),
                "motivo": _fmt_val(row.get("motivo_integrado") or row.get("motivo")),
                "orientacoes": {
                    "gestor": o.get("gestor"),
                    "profissional": o.get("profissional"),
                    "populacao": o.get("populacao"),
                },
                "predicao": {
                    "nivel_predicao_7d": _norm_level(row.get("nivel_predicao_7d")),
                    "resumo": (
                        f"Classificação prevista em cerca de 7 dias: "
                        f"{LEVEL_LABEL.get(_norm_level(row.get('nivel_predicao_7d')), 'sem previsão')}"
                    ),
                    "icone_predicao": EMOJI.get(_norm_level(row.get("nivel_predicao_7d")), "⚪"),
                },
            }
            if "cuiaba" in layers_ai:
                cuiaba["orientacao_ia"] = _ai_orientacao(cuiaba, "cuiaba")

    pack = {
        "ses": [ses],
        "regionais": regionais,
        "municipais": municipais,
        "cuiaba": [cuiaba] if cuiaba else [],
    }
    fp_src = (
        f"{nivel_estado}|{len(regionais)}|{len(municipais)}|"
        + "|".join(f"{k}:{v}" for k, v in sorted(dist.items()))
        + "|"
        + "|".join(p["municipio"] for p in priorizados[:5])
    )
    fingerprint = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()[:16]
    meta = {
        "nivel": nivel_estado,
        "n_regionais": len(regionais),
        "n_municipais": len(municipais),
        "n_ses": 1,
        "n_cuiaba": 1 if cuiaba else 0,
        "fingerprint": fingerprint,
        "distribuicao": dist,
        "com_ia": sum(
            1
            for lst in pack.values()
            for p in lst
            if p and p.get("orientacao_ia")
        ),
    }
    return pack, fingerprint, meta


def _split_telegram(text: str, header: str | None = None) -> list[str]:
    if len(text) <= 3900:
        return [text]
    chunks = []
    cur = header or ""
    for para in text.split("\n"):
        line = para + "\n"
        if len(cur) + len(line) > 3800:
            chunks.append(cur.rstrip() + "\n…")
            cur = (header or "") + "\n(cont.)\n" + line
        else:
            cur += line
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


def format_ses_telegram(p: dict[str, Any]) -> str:
    """Layout estadual: cabeçalho · indicadores · predição · setores/IA · prioritários."""
    niv = _norm_level(p.get("nivel"))
    lines = [
        p.get("titulo")
        or (
            f"{ICON['estado']} {EMOJI.get(niv, '⚪')} ALERTA ESTADUAL · SES-MT / CIEVS · "
            f"{LEVEL_LABEL.get(niv, niv)}"
        ),
        f"{EMOJI.get(niv, '⚪')} Classificação: {p.get('nivel_rotulo') or LEVEL_LABEL.get(niv, niv)}",
        f"🎯 Alvo: {p.get('alvo_nome')} · 🏘️ Mun.: {p.get('n_municipios')}",
        f"🕒 {p.get('gerado_em')}",
        "",
        f"{ICON['motivo']} Motivo",
        str(p.get("motivo") or "—")[:700],
        "",
        f"{ICON['indicadores']} Indicadores estaduais (valor · escala · limiares)",
    ]
    for ind in p.get("indicadores") or []:
        lines.append(_fmt_indicator_line(ind))

    pred = p.get("predicao") or {}
    lines += [
        "",
        f"{ICON['predicao']} Predição ~7d",
        f"{pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['orient_gestor']} Orientações por setor da Secretaria de Estado da Saúde",
    ]
    setores = p.get("orientacoes_setores") or {}
    setor_labels = [
        ("comando_cievs", "CIEVS / sala de situação"),
        ("gestao_hospitalar", "Gestão hospitalar e leitos"),
        ("regulacao", "Regulação e transporte"),
        ("assistencia_farmaceutica", "Assistência Farmacêutica (SAF)"),
        ("saude_trabalhador", "Saúde do Trabalhador"),
        ("atencao_primaria", "Atenção Primária"),
        ("vigilancia_ambiental", "Vigilância ambiental e zoonoses"),
        ("comunicacao_risco", "Comunicação de risco"),
    ]
    if setores:
        for key, label in setor_labels:
            if setores.get(key):
                lines += [f"• {label}:", str(setores[key]), ""]
        if setores.get("sintese_gestao"):
            lines += ["• Síntese para a gestão estadual:", str(setores["sintese_gestao"]), ""]
    else:
        lines.append(str(p.get("orientacao_gestao_ses") or "—"))

    if p.get("orientacao_ia"):
        lines += [
            f"{ICON['ia']} Orientações da IA para a gestão estadual (revisar)",
            str(p["orientacao_ia"]),
            "",
        ]

    max_prio = int(env("ALERT_SES_TOP_MUNICIPIOS", "10") or 10)
    lines += [f"{ICON['prioridade']} Municípios prioritários para ação (top {max_prio})"]
    priority_fields = {
        "nivel",
        "score",
        "tmax",
        "utci_proxy",
        "risco_cumulativo_3d",
        "ocupacao_leitos_pct",
        "pressao_calor_pct",
        "tendencia_7d",
    }
    for i, m in enumerate((p.get("municipios_prioritarios") or [])[:max_prio], 1):
        mn = _norm_level(m.get("nivel"))
        lines.append(
            f"\n{i}. {EMOJI.get(mn, '⚪')} {m.get('municipio')} "
            f"(Regional: {m.get('regional')}) — {LEVEL_LABEL.get(mn, mn)}"
        )
        shown = 0
        for ind in m.get("indicadores") or []:
            campo = str(ind.get("campo") or "")
            if campo not in priority_fields:
                continue
            meta = INDICATOR_META.get(campo, {})
            icon = ind.get("icone") or IND_ICON.get(campo, "•")
            extra = f" · escala {meta['escala']}" if meta.get("escala") else ""
            lines.append(f"   {icon} {ind.get('rotulo')}: {ind.get('valor')}{extra}")
            shown += 1
            if shown >= 6:
                break

    lines += [
        "",
        f"{ICON['rodape']} Validar no painel antes de comunicação oficial.",
        "Lista de contatos provisória — aguardando atualização CIEVS.",
    ]
    return "\n".join(lines)


def format_regional_telegram(p: dict[str, Any]) -> str:
    lines = [
        p.get("titulo") or f"{ICON['regional']} ALERTA REGIONAL",
        f"🕒 {p.get('gerado_em')}",
        f"🏘️ Municípios na jurisdição: {p.get('n_municipios')}",
        "",
        f"{ICON['dist']} Cenário por classificação",
        p.get("distribuicao_texto") or "—",
        "",
        f"{ICON['motivo']} Motivo de referência",
        str(p.get("motivo") or "—")[:500],
        "",
        f"{ICON['indicadores']} Municípios da regional (indicadores)",
    ]
    for m in (p.get("municipios_jurisdicao") or [])[:20]:
        niv = _norm_level(m.get("nivel"))
        lines.append(f"\n{EMOJI.get(niv, '⚪')} {m.get('municipio')} — {LEVEL_LABEL.get(niv, niv)}")
        for ind in (m.get("indicadores") or [])[:6]:
            lines.append(f"   {ind.get('icone', '•')} {ind.get('rotulo')}: {ind.get('valor')}")
    lines += [
        "",
        f"{ICON['orient_gestor']} Ações sugeridas para a gestão regional",
        str(p.get("orientacao_gestao_regional") or "—"),
    ]
    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientações da IA para a regional (revisar)", str(p["orientacao_ia"])]
    lines += ["", f"{ICON['rodape']} Validar com a SES/CIEVS antes de envio externo."]
    return "\n".join(lines)


def format_municipal_telegram(p: dict[str, Any]) -> str:
    o = p.get("orientacoes") or {}
    pred = p.get("predicao") or {}
    lines = [
        p.get("titulo") or f"{ICON['municipal']} ALERTA MUNICIPAL",
        f"🗺️ Regional de Saúde: {p.get('regional', '—')}",
        f"🕒 {p.get('gerado_em')}",
        "",
        f"{ICON['motivo']} Situação",
        str(p.get("motivo") or "—")[:500],
        "",
        f"{ICON['indicadores']} Indicadores do município (validados nesta rodada)",
    ]
    for ind in p.get("indicadores") or []:
        lines.append(f"{ind.get('icone', '•')} {ind.get('rotulo')}: {ind.get('valor')}")
    lines += [
        "",
        f"{ICON['predicao']} Perspectiva de cerca de 7 dias",
        f"{pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['orient_gestor']} Para o gestor municipal",
        str(o.get("gestor") or "—"),
        "",
        f"{ICON['orient_prof']} Para profissionais de saúde",
        str(o.get("profissional") or "—"),
        "",
        f"{ICON['orient_pop']} Para a população",
        str(o.get("populacao") or "—"),
        "",
        f"{ICON['rodape']} Fonte: SIS Clima-Saúde MT · validar no território.",
    ]
    return "\n".join(lines)


def format_cuiaba_telegram(p: dict[str, Any]) -> str:
    o = p.get("orientacoes") or {}
    pred = p.get("predicao") or {}
    lines = [
        p.get("titulo") or f"{ICON['cuiaba']} VIGIDESASTRE CUIABÁ",
        f"📨 Remetente: {p.get('remetente', 'VIGIDESASTRE CUIABÁ')}",
        f"🕒 {p.get('gerado_em')}",
        f"{p.get('icone', '⚪')} Classificação: {p.get('nivel_rotulo')}",
        "",
        f"{ICON['motivo']} Status e motivo",
        str(p.get("motivo") or "—")[:600],
        "",
        f"{ICON['indicadores']} Índices, indicadores e KPIs de Cuiabá",
    ]
    for ind in p.get("indicadores") or []:
        lines.append(f"{ind.get('icone', '•')} {ind.get('rotulo')}: {ind.get('valor')}")
    lines += [
        "",
        f"{ICON['predicao']} Perspectiva de cerca de 7 dias",
        f"{pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['orient_gestor']} Orientações ao gestor municipal",
        str(o.get("gestor") or "—"),
        "",
        f"{ICON['orient_prof']} Orientações aos profissionais de saúde",
        str(o.get("profissional") or "—"),
        "",
        f"{ICON['orient_pop']} Orientações à população",
        str(o.get("populacao") or "—"),
    ]
    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientações da IA — Vigidesastre Cuiabá (revisar)", str(p["orientacao_ia"])]
    lines += ["", f"{ICON['rodape']} Relatório dedicado Vigidesastre Cuiabá · SIS Clima-Saúde MT."]
    return "\n".join(lines)


def _html_escape_pre(txt: str) -> str:
    return f"<pre style='white-space:pre-wrap;font-family:Segoe UI,Arial,sans-serif'>{html.escape(txt)}</pre>"


def format_pack_html(title: str, bodies: list[str]) -> str:
    sections = "".join(
        f"<section style='border:1px solid #e2e8f0;border-radius:12px;padding:14px;margin:0 0 14px;background:#fff'>{_html_escape_pre(b)}</section>"
        for b in bodies
    )
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:0 auto;background:#f8fafc;padding:16px">
      <h1 style="margin:0 0 8px">{ICON['titulo']} {html.escape(title)}</h1>
      <p style="color:#64748b">Gerado em {html.escape(now_iso())}</p>
      {sections}
    </div>
    """


def _tg_send_text(text: str, pause: float = 0.35) -> bool:
    ok = False
    for chunk in _split_telegram(text):
        if send_telegram(chunk):
            ok = True
        time.sleep(pause)
    return ok


def _send_four_layers(pack: dict[str, list[dict[str, Any]]], meta: dict) -> dict[str, Any]:
    tg_ok = False
    em_ok = False
    counts = {"ses": 0, "regionais": 0, "municipais": 0, "cuiaba": 0}
    layers = {
        x.strip().lower()
        for x in (env("ALERT_LAYERS", "ses,regionais,municipais,cuiaba") or "ses").split(",")
        if x.strip()
    }

    # 1) SES
    if "ses" in layers:
        for p in pack.get("ses") or []:
            txt = format_ses_telegram(p)
            if _tg_send_text(txt, pause=0.4):
                tg_ok = True
                counts["ses"] += 1
            if send_email(
                f"[SIS] {ICON['estado']} Alerta SES-MT / CIEVS — {p.get('nivel_rotulo')}",
                txt,
                html_body=format_pack_html("Alerta 1/4 — Gestão SES-MT / CIEVS", [txt]),
            ):
                em_ok = True

    # 2) Regionais — Telegram 1 msg cada; e-mail consolidado
    if "regionais" in layers or "regional" in layers:
        reg_texts = []
        for p in pack.get("regionais") or []:
            txt = format_regional_telegram(p)
            reg_texts.append(txt)
            if _tg_send_text(txt, pause=0.35):
                tg_ok = True
                counts["regionais"] += 1
        if reg_texts:
            if send_email(
                f"[SIS] {ICON['regional']} Alertas Regionais ({len(reg_texts)}) — CIEVS/SES-MT",
                "\n\n".join(reg_texts[:5]) + ("\n\n…" if len(reg_texts) > 5 else ""),
                html_body=format_pack_html(f"Alerta 2/4 — Regionais de Saúde ({len(reg_texts)})", reg_texts),
            ):
                em_ok = True

    # 3) Municipais
    if "municipais" in layers or "municipal" in layers:
        send_all_mun = as_bool(env("ALERT_SEND_ALL_MUNICIPIOS", "true"), True)
        min_mun = _norm_level(env("ALERT_MIN_LEVEL_MUNICIPAL", env("ALERT_MIN_LEVEL", "amarela")))
        mun_list = pack.get("municipais") or []
        if not send_all_mun:
            mun_list = [p for p in mun_list if STAGE_ORDER.get(p.get("nivel", "cinza"), -1) >= STAGE_ORDER.get(min_mun, 1)]
        mun_texts = []
        for p in mun_list:
            txt = format_municipal_telegram(p)
            mun_texts.append(txt)
            if _tg_send_text(txt, pause=0.35):
                tg_ok = True
                counts["municipais"] += 1
        # e-mail municipal: divide em blocos de 25 para não estourar SMTP
        if mun_texts:
            block = int(env("ALERT_EMAIL_MUNICIPAL_BLOCK", "25") or 25)
            for i in range(0, len(mun_texts), block):
                part = mun_texts[i : i + block]
                if send_email(
                    f"[SIS] {ICON['municipal']} Alertas Municipais {i+1}–{i+len(part)} de {len(mun_texts)}",
                    "\n\n".join(part[:3]) + "\n\n…",
                    html_body=format_pack_html(
                        f"Alerta 3/4 — Municipais ({i+1}–{i+len(part)} de {len(mun_texts)})",
                        part,
                    ),
                ):
                    em_ok = True
                time.sleep(0.5)

    # 4) Cuiabá Vigidesastre
    if "cuiaba" in layers:
        for p in pack.get("cuiaba") or []:
            txt = format_cuiaba_telegram(p)
            if _tg_send_text(txt, pause=0.4):
                tg_ok = True
                counts["cuiaba"] += 1
            if send_email(
                f"[SIS] {ICON['cuiaba']} VIGIDESASTRE CUIABÁ — {p.get('nivel_rotulo')}",
                txt,
                html_body=format_pack_html("Alerta 4/4 — Vigidesastre Cuiabá", [txt]),
            ):
                em_ok = True

    return {"telegram": tg_ok, "email": em_ok, "webhook": False, "enviados": counts, "layers": sorted(layers), **meta}


def send_digest(
    *,
    force: bool = False,
    skip_cooldown: bool = False,
    resumo: pd.DataFrame | None = None,
) -> dict[str, Any]:
    _ensure_digest_table()
    pack, fingerprint, meta = build_four_layer_pack(resumo)
    nivel = meta["nivel"]

    if not force and not as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false"), False):
        return {"status": "bloqueado_por_config", "nivel": nivel, "fingerprint": fingerprint}

    if not min_level_ok(nivel) and not force:
        return {"status": "abaixo_do_minimo", "nivel": nivel, "min": env("ALERT_MIN_LEVEL", "laranja")}

    last = _last_digest()
    if not force and not skip_cooldown and not _cooldown_ok():
        return {"status": "cooldown", "nivel": nivel, "ultimo": (last or {}).get("enviado_em")}

    if (
        not force
        and last
        and last.get("fingerprint") == fingerprint
        and as_bool(env("ALERT_DIGEST_SKIP_IDENTICO", "true"), True)
    ):
        return {"status": "identico", "nivel": nivel, "fingerprint": fingerprint}

    results = _send_four_layers(pack, meta)
    status = "enviado" if results.get("telegram") or results.get("email") else "registrado_sem_canal"
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO alertas_digest_controle (id, fingerprint, nivel, enviado_em, canais, status)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                fingerprint=excluded.fingerprint,
                nivel=excluded.nivel,
                enviado_em=excluded.enviado_em,
                canais=excluded.canais,
                status=excluded.status
            """,
            (fingerprint, nivel, now_iso(), json.dumps(results, ensure_ascii=False), status),
        )
        execute(
            conn,
            """
            INSERT INTO alertas_enviados
                (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                (last or {}).get("nivel"),
                nivel,
                f"[SIS] 4 camadas {EMOJI.get(nivel,'⚪')} {nivel.upper()}",
                (
                    f"SES=1; regionais={meta.get('n_regionais')}; "
                    f"municipais={meta.get('n_municipais')}; cuiaba={meta.get('n_cuiaba')}; ia={meta.get('com_ia')}"
                ),
                json.dumps({"tipo": "quatro_camadas", **results}, ensure_ascii=False),
                status,
            ),
        )
    log.info("Digest 4 camadas %s · %s", status, results.get("enviados"))
    return {"status": status, "canais": results, **meta}


# Compatibilidade
def build_multilevel_pack(resumo: pd.DataFrame | None = None):
    pack, fingerprint, meta = build_four_layer_pack(resumo)
    flat = []
    for k in ("ses", "regionais", "municipais", "cuiaba"):
        flat.extend([p for p in pack.get(k) or [] if p])
    return flat, fingerprint, meta


def build_digest_message(resumo: pd.DataFrame | None = None) -> tuple[str, str, str, dict]:
    pack, fingerprint, meta = build_four_layer_pack(resumo)
    ses = (pack.get("ses") or [{}])[0]
    subject = ses.get("titulo") or f"[SIS] Multinível {meta.get('nivel')}"
    message = format_ses_telegram(ses) if ses else "—"
    return subject, message, fingerprint, meta
