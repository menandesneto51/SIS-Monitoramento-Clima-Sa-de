# -*- coding: utf-8 -*-
"""Boletins CIEVS multinível — SES legível (resumo → KPI → ações → IA → prioritários)."""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from typing import Any

import pandas as pd

from sisclima.alerts.contacts import fanout_enabled, recipients_for, summarize_contacts
from sisclima.alerts.notifier import send_email, send_telegram
from sisclima.core.config import as_bool, env
from sisclima.core.db import db_conn, execute, fetchone, read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.engines.alertas_multinivel import (
    EMOJI,
    LEVEL_LABEL,
    build_alertas_multinivel,
    persist_payloads,
)
from sisclima.engines.stages import STAGE_ORDER
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

# Canal central (Menandes / CIEVS / notifica): somente estadual.
CENTRAL_SCOPES = frozenset({"estadual"})
TERRITORIAL_SCOPES = frozenset({"regional", "municipal", "cuiaba"})

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
    "fontes": "📚",
    "rodape": "✅",
    "legenda": "📎",
    "resumo": "📋",
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
    "pm25_ugm3": "💨",
    "incidencia_arbovirus_100k": "🦟",
    "casos_srag": "🫁",
    "cobertura_ocupacao": "📡",
    "tendencia_7d": "📉",
    "nivel_predicao_7d": "🔮",
}

# Limiares numéricos para status curto no painel SES
STATUS_THRESHOLDS: dict[str, list[tuple[float, str]]] = {
    # (limiar mínimo, rótulo) — ordem ascendente; último que o valor ultrapassa vence
    "score": [(0, "VERDE"), (1, "AMARELA"), (2, "LARANJA"), (3, "VERMELHA"), (4, "ROXA")],
    "score_alerta_integrado": [(0, "VERDE"), (1, "AMARELA"), (2, "LARANJA"), (3, "VERMELHA"), (4, "ROXA")],
    "tmax": [(0, "rotina"), (37, "atenção"), (39, "ALERTA"), (41, "INTENSIFICADO"), (43, "PLENO")],
    "utci_proxy": [(0, "rotina"), (26, "atenção"), (32, "ALERTA"), (38, "INTENSIFICADO"), (46, "PLENO")],
    "risco_cumulativo_3d": [(0, "rotina"), (3, "atenção"), (7, "ALERTA"), (12, "INTENSIFICADO"), (18, "PLENO")],
    "pressao_calor_pct": [(0, "rotina"), (2, "atenção"), (4, "ALERTA"), (7, "INTENSIFICADO"), (10, "PLENO")],
    "ocupacao_leitos_pct": [(0, "abaixo do limiar de alerta"), (75, "atenção"), (85, "ALERTA"), (95, "INTENSIFICADO"), (100, "PLENO")],
    "pm25_ugm3": [(0, "dentro/próximo ref. OMS"), (15, "acima da ref. OMS (~15)")],
}

LEGENDA_RAPIDA = (
    "pontuação 0–4 (0 verde · 1 amarela · 2 laranja · 3 vermelha · 4 roxa) | "
    "Tmáx alerta ≥39 °C | sensação alerta >32 °C | "
    "risco 3d alerta ≥7 · intensificado ≥12 · pleno ≥18 | ocupação alerta ≥75%"
)


def _norm_level(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in ("amarelo",):
        s = "amarela"
    if s in ("vermelho",):
        s = "vermelha"
    if s in ("roxo",):
        s = "roxa"
    return s if s in EMOJI else "cinza"


def _texto_territorios_escopo(payload: dict[str, Any], *, escopo: str) -> str:
    """Texto de povos/territórios para o boletim (SES, regional ou município)."""
    try:
        from sisclima.engines.vigibarragens_clima import (
            sintese_territorial,
            texto_orientacao_municipal,
        )

        if escopo in {"municipal", "cuiaba"}:
            return texto_orientacao_municipal(payload)
        df = None
        try:
            from sisclima.core.db import read_table as _rt

            df = _rt("prontidao_municipal")
            if df is None or df.empty:
                df = _rt("resumo_municipal_atual")
        except Exception:
            df = None
        if (
            escopo == "regional"
            and isinstance(df, pd.DataFrame)
            and not df.empty
            and "regional_saude" in df.columns
        ):
            nome = str(payload.get("alvo_nome") or payload.get("regional") or "")
            df = df[df["regional_saude"].astype(str) == nome]
        syn = sintese_territorial(df)
        return str(syn.get("texto") or "Sem cruzamento Vigibarragens neste recorte.")
    except Exception:
        return (
            "Conferir aldeias, quilombos, assentamentos e barragens DPA alto no painel "
            "(Prontidão climática). Distância ao eixo ≠ inundação."
        )


def min_level_ok(nivel: str, min_level: str | None = None) -> bool:
    floor = _norm_level(min_level or env("ALERT_MIN_LEVEL", "laranja"))
    return STAGE_ORDER.get(_norm_level(nivel), -1) >= STAGE_ORDER.get(floor, 2)


def _parse_num(v: Any) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    # remove notas entre parênteses
    s = re.sub(r"\s*\(.*\)$", "", s)
    s = s.replace("%", "").strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _status_for(campo: str, valor: Any) -> str | None:
    num = _parse_num(valor)
    if num is None or campo not in STATUS_THRESHOLDS:
        return None
    label = STATUS_THRESHOLDS[campo][0][1]
    for thr, lab in STATUS_THRESHOLDS[campo]:
        if num >= thr:
            label = lab
    return label


def _dist_compact(dist: dict[str, Any] | None, indicadores: list[dict] | None = None) -> str:
    d = dict(dist or {})
    if not d and indicadores:
        for ind in indicadores:
            if ind.get("campo") == "distribuicao_niveis":
                # "laranja:82, amarela:40, ..."
                for part in str(ind.get("valor") or "").split(","):
                    part = part.strip()
                    if ":" in part:
                        k, v = part.split(":", 1)
                        try:
                            d[k.strip()] = int(v.strip())
                        except Exception:
                            pass
    order = ["roxa", "vermelha", "laranja", "amarela", "verde", "cinza"]
    parts = []
    for k in order:
        if k in d and int(d[k] or 0) > 0:
            parts.append(f"{EMOJI.get(k, '⚪')}{int(d[k])}")
    return " ".join(parts) if parts else "—"


def build_orientacoes_ses_setores(payload: dict[str, Any]) -> dict[str, str]:
    """Checklist operacional por setor da SES, ancorado no cenário."""
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

    vals: dict[str, float | None] = {}
    for ind in payload.get("indicadores") or []:
        campo = str(ind.get("campo") or "")
        if campo in {"utci_proxy", "ocupacao_leitos_pct", "pm25_ugm3", "incidencia_arbovirus_100k", "risco_cumulativo_3d"}:
            vals[campo] = _parse_num(ind.get("valor"))

    utci = vals.get("utci_proxy")
    ocup = vals.get("ocupacao_leitos_pct")
    pm = vals.get("pm25_ugm3")
    arbo = vals.get("incidencia_arbovirus_100k")

    from sisclima.engines.atencao_farmaceutica import acao_estadual, flags_from_resumo, orientacao_mascara

    flags_ag = {
        "fumaca": pm is not None and pm >= 25,
        "iqa_atencao": pm is not None and pm >= 15,
        "inundacao": False,
        "calor": utci is not None and utci >= 32,
        "arbovirose": arbo is not None and arbo >= 10,
        "srag": False,
    }
    try:
        from sisclima.core.db import read_table as _rt

        flags_ag = flags_from_resumo(_rt("resumo_municipal_atual"))
    except Exception:
        pass
    saf = acao_estadual({}, agreg=flags_ag)
    mascara_iqa = orientacao_mascara(pm)

    cievs = (
        f"Manter sala de situação ativa ({LEVEL_LABEL.get(nivel, nivel)}). "
        f"Articular {n_crit} município(s) em vermelha/roxa e {n_lar} em laranja. "
        f"Foco: {top_names or 'municípios de maior pontuação'}."
    )
    hospitalar = (
        "Verificar leitos e plano de contingência hospitalar nas regionais prioritárias"
        + (f" (ocupação estadual ~{ocup:.1f}%)".replace(".", ",") if ocup is not None else "")
        + ". Avaliar expansão, regulação e leitos de retaguarda."
    )
    if ocup is not None and ocup < 75:
        hospitalar += " Ocupação ainda abaixo do limiar de alerta (≥75%) — monitorar tendência e filas."
    regulacao = (
        "Mapear vagas e fluxos para prioritários; "
        "retaguarda para hipertermia, desidratação grave e descompensações cardiorrespiratórias."
    )
    trabalhador = (
        "Orientar troca/flexibilização de jornadas sob sol"
        + (f" (sensação pico ~{utci:.1f} °C)".replace(".", ",") if utci is not None else "")
        + "; priorizar rural, construção, coleta e serviços externos; pausas, hidratação e sombra/climatização."
    )
    aps = (
        "Busca ativa de idosos, gestantes, crianças e pessoas em situação de rua nos prioritários; "
        "hidratação e sinais de gravidade."
    )
    amb = (
        "Eliminar criadouros e comunicar risco de dengue; "
        + (f"acompanhar ar (PM2,5 pico ~{pm:.0f} µg/m³)." if pm is not None else "acompanhar qualidade do ar.")
    )
    comunicacao = (
        f"Boletim unificado às Regionais; mensagens de hidratação e evitar pico de calor; "
        f"{mascara_iqa} "
        f"Antecipar comunicação aos {n_up} municípios com tendência de piora em ~7 dias."
    )
    terr = "Articular SESAI/DSEI, APS rural e Defesa Civil nos municípios com aldeias, quilombos, assentamentos ou barragem DPA alto. Distância ao eixo ≠ inundação."
    try:
        from sisclima.engines.vigibarragens_clima import sintese_territorial

        syn = sintese_territorial()
        if syn.get("ok") and syn.get("texto"):
            terr = syn["texto"]
            top = syn.get("top") or []
            if top:
                terr += " Prioridade: " + "; ".join(top[:4]) + "."
    except Exception:
        pass
    return {
        "comando_cievs": cievs,
        "gestao_hospitalar": hospitalar,
        "regulacao": regulacao,
        "assistencia_farmaceutica": saf,
        "saude_trabalhador": trabalhador,
        "atencao_primaria": aps,
        "povos_territorios": terr,
        "vigilancia_ambiental": amb,
        "comunicacao_risco": comunicacao,
    }


def _kpi_line(ind: dict[str, Any], *, escopo: str = "estadual") -> str | None:
    """Valor + status curto; limiares completos ficam só na legenda da seção."""
    campo = str(ind.get("campo") or "")
    if campo in {"n_municipios", "distribuicao_niveis", "cobertura_ocupacao"}:
        return None
    icon = IND_ICON.get(campo, "•")
    rotulo = str(ind.get("rotulo") or campo)
    ocup_short = "Ocupação estadual" if escopo == "estadual" else "Ocupação regional"
    # rótulos curtos no painel
    short = {
        "score": "Pontuação (pior)",
        "score_alerta_integrado": "Pontuação integrada (pior)",
        "tmax": "Tmáx pico",
        "utci_proxy": "Sensação pico",
        "risco_cumulativo_3d": "Risco 3d pico",
        "pressao_calor_pct": "Pressão calor pico",
        "pm25_ugm3": "PM2,5 pico",
        "ocupacao_leitos_pct": ocup_short,
        "incidencia_arbovirus_100k": "Arboviroses pico /100 mil",
        "casos_srag": "SRAG (soma)",
    }.get(campo, rotulo)
    valor = ind.get("valor")
    status = _status_for(campo, valor)
    num = _parse_num(valor)

    def _br(v: float, nd: int = 1) -> str:
        return f"{v:.{nd}f}".replace(".", ",")

    if campo in {"score", "score_alerta_integrado"}:
        valor_txt = f"{int(num)}/4" if num is not None else str(valor)
    elif campo == "ocupacao_leitos_pct":
        valor_txt = f"{_br(num)}%" if num is not None else str(valor)
    elif campo == "pressao_calor_pct":
        valor_txt = f"{_br(num)} /15" if num is not None else f"{valor} /15"
    elif campo in {"tmax", "utci_proxy"}:
        valor_txt = f"{_br(num)} °C" if num is not None else str(valor)
    elif campo == "pm25_ugm3":
        valor_txt = f"{_br(num)} µg/m³" if num is not None else str(valor)
    elif campo == "risco_cumulativo_3d":
        valor_txt = _br(num) if num is not None else str(valor)
    else:
        valor_txt = str(valor)
    line = f"{icon} {short}: {valor_txt}"
    if status:
        line += f" — {status}"
    return line


# Alias do plano (legado): valor + status, sem limiar por linha
_fmt_indicator_line = _kpi_line


def _priority_one_liner(m: dict[str, Any], idx: int) -> str:
    niv = _norm_level(m.get("nivel"))
    score = _parse_num(m.get("score"))
    tmax = _parse_num(m.get("tmax"))
    utci = _parse_num(m.get("utci_proxy"))
    risco = _parse_num(m.get("risco_cumulativo_3d"))
    ocup = _parse_num(m.get("ocupacao_leitos_pct"))
    fonte = str(m.get("fonte_ocupacao") or "")
    if not any(v is not None for v in (score, tmax, utci, risco, ocup)):
        # fallback via indicadores
        for ind in m.get("indicadores") or []:
            c = ind.get("campo")
            if c == "score" and score is None:
                score = _parse_num(ind.get("valor"))
            if c == "tmax" and tmax is None:
                tmax = _parse_num(ind.get("valor"))
            if c == "utci_proxy" and utci is None:
                utci = _parse_num(ind.get("valor"))
            if c == "risco_cumulativo_3d" and risco is None:
                risco = _parse_num(ind.get("valor"))
            if c == "ocupacao_leitos_pct" and ocup is None:
                ocup = _parse_num(ind.get("valor"))
                if "estimado" in str(ind.get("valor")).lower() or "FALLBACK" in fonte.upper():
                    fonte = "FALLBACK"
                elif "local" in str(ind.get("valor")).lower():
                    fonte = "TEMPO_REAL"

    ocup_tag = ""
    if ocup is not None:
        if "TEMPO_REAL" in fonte.upper():
            ocup_tag = " local"
        elif "FALLBACK" in fonte.upper() or "ESTADUAL" in fonte.upper():
            ocup_tag = " estimado estadual"
        else:
            ocup_tag = ""

    def _f(v: float | None, nd: int = 1) -> str:
        if v is None:
            return "—"
        if abs(v - round(v)) < 1e-9 and nd == 0:
            return str(int(round(v)))
        return f"{v:.{nd}f}".replace(".", ",")

    parts = [
        f"{idx}. {EMOJI.get(niv, '⚪')} {m.get('municipio')} ({m.get('regional') or '—'})",
        f"score {_f(score, 0)}/4" if score is not None else "score —",
        f"T {_f(tmax)}",
        f"sens {_f(utci)}",
        f"risco3d {_f(risco)}",
        f"ocup {_f(ocup)}%{ocup_tag}" if ocup is not None else "ocup —",
    ]
    al = m.get("n_aldeias")
    qi = m.get("n_quilombos")
    asst = m.get("n_assentamentos")
    try:
        if int(float(al or 0) + float(qi or 0) + float(asst or 0)) > 0:
            parts.append(f"territórios {int(float(al or 0))} ald/{int(float(qi or 0))} quil/{int(float(asst or 0))} ass")
    except Exception:
        pass
    return " | ".join(parts)


def _ai_is_redundant(ai_txt: str, setores: dict[str, str]) -> bool:
    """Omite IA se for curta, sem bullets ou quase cópia do checklist setorial."""
    if not ai_txt or len(ai_txt.strip()) < 80:
        return True
    blob = " ".join(setores.values()).lower()
    blob_tokens = {t for t in re.findall(r"[a-zà-ú]{4,}", blob)}
    bullets = [b.strip("-• ").lower() for b in ai_txt.splitlines() if b.strip().lstrip("-• ")]
    if not bullets:
        return True
    # poucas linhas e eco óbvio → omitir
    if len(bullets) < 3:
        return True
    overlap = 0
    token_hits = 0
    for b in bullets:
        key = b[:40]
        if key and key in blob:
            overlap += 1
        btoks = {t for t in re.findall(r"[a-zà-ú]{4,}", b)}
        if btoks and len(btoks & blob_tokens) / max(len(btoks), 1) >= 0.55:
            token_hits += 1
    return overlap >= max(3, len(bullets) - 1) or token_hits >= max(3, len(bullets) - 1)


def _ai_orientacao_ses(payload: dict[str, Any]) -> str | None:
    if not (
        as_bool(env("USE_AI_ALERT_TEXT", "false"), False)
        or as_bool(env("USE_LLM_REPORT", "false"), False)
    ):
        return None
    try:
        from sisclima.ai.report_generator import maybe_llm_report

        setores = payload.get("orientacoes_setores") or {}
        ctx = {
            "tarefa": "orientacao_alerta_ses",
            "instrucao": (
                "Escreva EXATAMENTE 5 bullets operacionais para a gestão estadual SES/CIEVS. "
                "NÃO repita as orientações por setor já listadas. Acrescente só ângulos novos "
                "(interfederativo, cronograma, critérios de desescalonamento, gaps de dado). "
                "Formato: cada linha com '- '. Sem títulos, sem markdown. Português claro."
            ),
            "alerta": {
                "nivel": payload.get("nivel"),
                "nivel_rotulo": payload.get("nivel_rotulo"),
                "motivo": str(payload.get("motivo") or "")[:400],
                "distribuicao": payload.get("distribuicao"),
                "predicao": (payload.get("predicao") or {}).get("resumo"),
                "prioritarios": [
                    {"municipio": m.get("municipio"), "regional": m.get("regional"), "nivel": m.get("nivel")}
                    for m in (payload.get("municipios_prioritarios") or [])[:8]
                ],
                "setores_ja_enviados": list(setores.keys()),
            },
        }
        txt = maybe_llm_report(ctx)
        if not txt:
            return None
        txt = re.sub(r"^```\w*\n?", "", txt.strip())
        txt = re.sub(r"\n?```$", "", txt.strip())
        txt = txt.strip()[:3500]
        if _ai_is_redundant(txt, setores):
            return None
        return txt
    except Exception as exc:  # noqa: BLE001
        log.warning("IA SES indisponível: %s", exc)
        return None


def format_ses_telegram(p: dict[str, Any]) -> str:
    """Boletim SES legível: cabeçalho → resumo → KPI → ações → IA → prioritários (1 linha)."""
    niv = _norm_level(p.get("nivel"))
    inds = p.get("indicadores") or []
    n_mun = p.get("n_municipios") or next(
        (i.get("valor") for i in inds if i.get("campo") == "n_municipios"), "—"
    )
    dist_txt = _dist_compact(p.get("distribuicao"), inds)
    pred = p.get("predicao") or {}
    setores = p.get("orientacoes_setores") or build_orientacoes_ses_setores(p)

    lines = [
        f"{ICON['estado']} {EMOJI.get(niv, '⚪')} ALERTA ESTADUAL · SES-MT / CIEVS · {LEVEL_LABEL.get(niv, niv)}",
        f"{EMOJI.get(niv, '⚪')} Classificação: {p.get('nivel_rotulo') or LEVEL_LABEL.get(niv, niv)}",
        f"🎯 Alvo: {p.get('alvo_nome')} · 🏘️ Mun.: {n_mun}",
        f"📅 Dados do sistema: {p.get('data_referencia') or '—'}",
        f"🕒 Boletim montado em: {p.get('gerado_em')}",
        "",
        f"{ICON['resumo']} Resumo executivo",
        f"🏘️ {n_mun} municípios | {dist_txt}",
        f"{ICON['motivo']} {str(p.get('motivo') or '—')[:280]}",
        f"{ICON['predicao']} {pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['indicadores']} Situação estadual",
    ]
    for ind in inds:
        line = _kpi_line(ind, escopo="estadual")
        if line:
            lines.append(line)
    # cobertura
    for ind in inds:
        if ind.get("campo") == "cobertura_ocupacao":
            lines.append(f"📡 cobertura local: {ind.get('valor')}")
    lines += [f"{ICON['legenda']} Legenda: {LEGENDA_RAPIDA}", ""]

    lines.append(f"{ICON['orient_gestor']} Ações por setor (checklist)")
    setor_labels = [
        ("comando_cievs", "CIEVS / sala de situação"),
        ("gestao_hospitalar", "Gestão hospitalar e leitos"),
        ("regulacao", "Regulação e transporte"),
        ("assistencia_farmaceutica", "Assistência Farmacêutica (SAF)"),
        ("saude_trabalhador", "Saúde do Trabalhador"),
        ("atencao_primaria", "Atenção Primária"),
        ("povos_territorios", "Povos e territórios vulneráveis"),
        ("vigilancia_ambiental", "Vigilância ambiental e zoonoses"),
        ("comunicacao_risco", "Comunicação de risco"),
    ]
    for key, label in setor_labels:
        if setores.get(key):
            lines.append(f"• {label} — {setores[key]}")

    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientações da IA (revisar — ângulos adicionais)", str(p["orientacao_ia"])]

    max_prio = int(env("ALERT_SES_TOP_MUNICIPIOS", "8") or 8)
    prior = (p.get("municipios_prioritarios") or [])[:max_prio]
    lines += ["", f"{ICON['prioridade']} Municípios prioritários (top {len(prior)})"]
    for i, m in enumerate(prior, 1):
        lines.append(_priority_one_liner(m, i))

    lines += [
        "",
        f"{ICON['rodape']} Validar no painel antes de comunicação oficial.",
        "Lista de contatos provisória — aguardando atualização CIEVS.",
    ]
    return "\n".join(lines)


def format_ses_html(p: dict[str, Any]) -> str:
    """HTML com seções para leitura no e-mail (sem rodapé duplicado)."""
    return _format_sectioned_html(
        "Alerta 1/4 — Gestão SES-MT / CIEVS",
        format_ses_telegram(p),
        [
            ("Resumo executivo", ICON["resumo"]),
            ("Situação estadual", ICON["indicadores"]),
            ("Ações por setor", ICON["orient_gestor"]),
            ("Orientações da IA", ICON["ia"]),
            ("Municípios prioritários", ICON["prioridade"]),
        ],
    )


def build_orientacoes_regional(payload: dict[str, Any]) -> dict[str, str]:
    """Checklist operacional para gestão da Regional de Saúde."""
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
    vals: dict[str, float | None] = {}
    for ind in payload.get("indicadores") or []:
        campo = str(ind.get("campo") or "")
        if campo in {"utci_proxy", "ocupacao_leitos_pct", "pm25_ugm3", "risco_cumulativo_3d"}:
            vals[campo] = _parse_num(ind.get("valor"))
    utci = vals.get("utci_proxy")
    ocup = vals.get("ocupacao_leitos_pct")
    pm = vals.get("pm25_ugm3")

    return {
        "sala_situacao": (
            f"Ativar/manter sala de situação regional ({LEVEL_LABEL.get(nivel, nivel)}). "
            f"Acompanhar {n_crit} município(s) em vermelha/roxa e {n_lar} em laranja. "
            f"Foco: {top_names or 'municípios de maior pontuação'}."
        ),
        "apoio_municipios": (
            "Apoiar secretarias municipais na abertura de pontos de hidratação/resfriamento, "
            "comunicação de risco e checagem de insumos."
        ),
        "leitos_regulacao": (
            "Articular leitos e regulação na jurisdição"
            + (f" (ocupação ~{ocup:.1f}%)".replace(".", ",") if ocup is not None else "")
            + "; mapear retaguarda e transporte para hipertermia/desidratação grave."
        ),
        "insumos": (
            "Checar estoque regional de SRO, soro EV, broncodilatadores, corticoides e hipoclorito 2,5%; "
            "reportar ruptura à SAF/SES. "
            + (f"Ar: PM2,5 pico ~{pm:.0f} µg/m³." if pm is not None else "")
        ),
        "trabalhador_aps": (
            "Orientar atenção básica e saúde do trabalhador sobre pausas, hidratação e "
            f"flexibilização de jornada sob sol"
            + (f" (sensação pico ~{utci:.1f} °C)".replace(".", ",") if utci is not None else "")
            + "."
        ),
        "ambiental": (
            "Reforçar eliminação de criadouros e vigilância de dengue; "
            + (f"acompanhar ar (PM2,5 pico ~{pm:.0f} µg/m³)." if pm is not None else "acompanhar qualidade do ar.")
        ),
        "comunicacao": (
            f"Boletim diário aos municípios da regional; antecipar comunicação aos "
            f"{n_up} com tendência de piora em ~7 dias; reportar críticos à SES/CIEVS."
        ),
        "povos_territorios": _texto_territorios_escopo(payload, escopo="regional"),
    }


def build_orientacoes_municipal(payload: dict[str, Any]) -> dict[str, str]:
    """Checklist para gestor, profissionais e população no município."""
    nivel = _norm_level(payload.get("nivel"))
    utci = _parse_num(payload.get("utci_proxy"))
    ocup = _parse_num(payload.get("ocupacao_leitos_pct"))
    pm = _parse_num(payload.get("pm25_ugm3"))
    risco = _parse_num(payload.get("risco_cumulativo_3d"))
    for ind in payload.get("indicadores") or []:
        c = str(ind.get("campo") or "")
        if c == "utci_proxy" and utci is None:
            utci = _parse_num(ind.get("valor"))
        if c == "ocupacao_leitos_pct" and ocup is None:
            ocup = _parse_num(ind.get("valor"))
        if c == "pm25_ugm3" and pm is None:
            pm = _parse_num(ind.get("valor"))
        if c == "risco_cumulativo_3d" and risco is None:
            risco = _parse_num(ind.get("valor"))

    gestor = (
        f"Manter sala de situação municipal ({LEVEL_LABEL.get(nivel, nivel)}); "
        "informar a Regional e a SES; checar insumos e pontos de hidratação/resfriamento."
    )
    if STAGE_ORDER.get(nivel, -1) >= STAGE_ORDER.get("laranja", 2):
        gestor += " Avaliar centro de operações parcial e comunicação pública."
    if ocup is not None and ocup >= 75:
        gestor += f" Ocupação de leitos elevada (~{ocup:.0f}%) — acionar contingência hospitalar."
    elif ocup is not None:
        gestor += " Monitorar tendência de leitos e filas de regulação."

    profissional = (
        "Priorizar idosos, gestantes, crianças e pessoas em situação de rua; "
        "identificar precocemente hipertermia e desidratação; reforçar hidratação e resfriamento."
    )
    if risco is not None and risco >= 12:
        profissional += " Risco de calor acumulado alto — ampliar observação em ambiente climatizado."
    if pm is not None and pm >= 15:
        profissional += f" Atenção respiratória: PM2,5 ~{pm:.0f} µg/m³."

    populacao = (
        "Hidrate-se; evite o sol no pico de calor; use roupas leves; "
        "procure atendimento se houver tontura, confusão, febre alta ou falta de ar."
    )
    if utci is not None and utci >= 32:
        populacao = (
            f"Sensação térmica elevada (~{utci:.1f} °C): ".replace(".", ",")
            + populacao
            + " Procure pontos de resfriamento/hidratação da prefeitura."
        )
    if STAGE_ORDER.get(nivel, -1) >= STAGE_ORDER.get("vermelha", 3):
        populacao += " Situação de alto risco — siga apenas canais oficiais."

    from sisclima.engines.atencao_farmaceutica import acao_municipal, orientacao_mascara

    farmacia = acao_municipal(
        {
            "pm25_ugm3": pm,
            "utci_proxy": utci,
            "risco_cumulativo_3d": risco,
            "ocupacao_leitos_pct": ocup,
            "iq_ar_score": payload.get("iq_ar_score"),
            "qualidade_ar_nivel": payload.get("qualidade_ar_nivel"),
            "situacao_hidro": payload.get("situacao_hidro"),
            "nivel_alerta_hidro": payload.get("nivel_alerta_hidro"),
            "casos_srag": payload.get("casos_srag"),
            "casos_arbovirus_7d": payload.get("casos_arbovirus_7d"),
            "incidencia_arbovirus_100k": payload.get("incidencia_arbovirus_100k"),
            "motivo": payload.get("motivo"),
        }
    )
    if pm is not None:
        populacao += " " + orientacao_mascara(pm, str(payload.get("qualidade_ar_nivel") or ""))

    territorios = _texto_territorios_escopo(payload, escopo="municipal")
    return {
        "gestor": gestor,
        "profissional": profissional,
        "populacao": populacao,
        "farmacia": farmacia,
        "territorios": territorios,
    }


def format_regional_telegram(p: dict[str, Any]) -> str:
    """Boletim regional no mesmo padrão do SES."""
    niv = _norm_level(p.get("nivel"))
    inds = p.get("indicadores") or []
    n_mun = p.get("n_municipios") or next(
        (i.get("valor") for i in inds if i.get("campo") == "n_municipios"), "—"
    )
    dist_txt = _dist_compact(p.get("distribuicao"), inds)
    pred = p.get("predicao") or {}
    acoes = p.get("orientacoes_regionais") or build_orientacoes_regional(p)
    reg = p.get("alvo_nome") or "Regional"

    lines = [
        f"{ICON['regional']} {EMOJI.get(niv, '⚪')} ALERTA REGIONAL · {reg} · {LEVEL_LABEL.get(niv, niv)}",
        f"{EMOJI.get(niv, '⚪')} Classificação: {p.get('nivel_rotulo') or LEVEL_LABEL.get(niv, niv)}",
        f"🎯 Alvo: Regional de Saúde {reg} · 🏘️ Mun.: {n_mun}",
        f"📅 Dados do sistema: {p.get('data_referencia') or '—'}",
        f"🕒 Boletim montado em: {p.get('gerado_em')}",
        "",
        f"{ICON['resumo']} Resumo executivo",
        f"🏘️ {n_mun} municípios na jurisdição | {dist_txt}",
        f"{ICON['motivo']} {str(p.get('motivo') or '—')[:280]}",
        f"{ICON['predicao']} {pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['indicadores']} Situação da regional",
    ]
    for ind in inds:
        line = _kpi_line(ind, escopo="regional")
        if line:
            lines.append(line)
    for ind in inds:
        if ind.get("campo") == "cobertura_ocupacao":
            lines.append(f"📡 cobertura local: {ind.get('valor')}")
    lines += [f"{ICON['legenda']} Legenda: {LEGENDA_RAPIDA}", ""]

    lines.append(f"{ICON['orient_gestor']} Ações para a gestão regional (checklist)")
    for key, label in [
        ("sala_situacao", "Sala de situação regional"),
        ("apoio_municipios", "Apoio aos municípios"),
        ("leitos_regulacao", "Leitos e regulação"),
        ("insumos", "Insumos / atenção farmacêutica"),
        ("trabalhador_aps", "Atenção básica / trabalhador"),
        ("povos_territorios", "Povos e territórios vulneráveis"),
        ("ambiental", "Vigilância ambiental"),
        ("comunicacao", "Comunicação e reporte à SES"),
    ]:
        if acoes.get(key):
            lines.append(f"• {label} — {acoes[key]}")

    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientações da IA (revisar)", str(p["orientacao_ia"])]

    max_prio = int(env("ALERT_REGIONAL_TOP_MUNICIPIOS", "8") or 8)
    prior = (p.get("municipios_prioritarios") or [])[:max_prio]
    lines += ["", f"{ICON['prioridade']} Municípios prioritários da regional (top {len(prior)})"]
    for i, m in enumerate(prior, 1):
        lines.append(_priority_one_liner(m, i))

    lines += [
        "",
        f"{ICON['rodape']} Validar com a SES/CIEVS antes de envio externo.",
        "Lista de contatos provisória — aguardando atualização CIEVS.",
    ]
    return "\n".join(lines)


def format_municipal_telegram(p: dict[str, Any], *, cuiaba: bool = False) -> str:
    """Boletim municipal (e Vigidesastre Cuiabá) no padrão legível."""
    niv = _norm_level(p.get("nivel"))
    inds = p.get("indicadores") or []
    pred = p.get("predicao") or {}
    acoes = p.get("orientacoes_municipais") or build_orientacoes_municipal(p)
    mun = p.get("alvo_nome") or "Município"
    reg = p.get("regional") or "—"

    if cuiaba:
        header = (
            f"{ICON['cuiaba']} {EMOJI.get(niv, '⚪')} VIGIDESASTRE CUIABÁ · Relatório municipal · "
            f"{LEVEL_LABEL.get(niv, niv)}"
        )
        alvo = f"📨 Remetente: {p.get('remetente', 'VIGIDESASTRE CUIABÁ')} · 🗺️ Regional: {reg}"
    else:
        header = (
            f"{ICON['municipal']} {EMOJI.get(niv, '⚪')} ALERTA MUNICIPAL · {mun} · "
            f"{LEVEL_LABEL.get(niv, niv)}"
        )
        alvo = f"🎯 Município: {mun} · 🗺️ Regional: {reg}"

    lines = [
        header,
        f"{EMOJI.get(niv, '⚪')} Classificação: {p.get('nivel_rotulo') or LEVEL_LABEL.get(niv, niv)}",
        alvo,
        f"📅 Dados do sistema: {p.get('data_referencia') or '—'}",
        f"🕒 Boletim montado em: {p.get('gerado_em')}",
        "",
        f"{ICON['resumo']} Resumo executivo",
        f"{ICON['motivo']} {str(p.get('motivo') or '—')[:280]}",
        f"{ICON['predicao']} {pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['indicadores']} Indicadores do município",
    ]
    # KPIs principais a partir do payload + indicadores
    kpi_fields = [
        ("score", "Pontuação", True),
        ("tmax", "Tmáx", False),
        ("utci_proxy", "Sensação", False),
        ("risco_cumulativo_3d", "Risco 3d", False),
        ("pressao_calor_pct", "Pressão calor", False),
        ("pm25_ugm3", "PM2,5", False),
        ("ocupacao_leitos_pct", "Ocupação leitos", False),
    ]
    shown = set()
    for campo, short, is_score in kpi_fields:
        val = p.get(campo)
        if val is None:
            for ind in inds:
                if ind.get("campo") == campo:
                    val = ind.get("valor")
                    break
        if val is None:
            continue
        status = _status_for(campo, val)
        num = _parse_num(val)
        if is_score and num is not None:
            valor_txt = f"{int(num)}/4"
        elif campo == "ocupacao_leitos_pct" and num is not None:
            fonte = str(p.get("fonte_ocupacao") or "")
            tag = ""
            if "TEMPO_REAL" in fonte.upper():
                tag = " local"
            elif "FALLBACK" in fonte.upper() or "ESTADUAL" in fonte.upper():
                tag = " estimado estadual"
            # também detecta nota no valor string
            vs = str(val)
            if "local" in vs.lower():
                tag = " local"
            elif "estimado" in vs.lower():
                tag = " estimado estadual"
            valor_txt = f"{num:.1f}%{tag}".replace(".", ",")
        elif campo == "pressao_calor_pct" and num is not None:
            valor_txt = f"{num:.1f} /15".replace(".", ",")
        elif num is not None:
            valor_txt = f"{num:.1f}".replace(".", ",")
        else:
            valor_txt = str(val).split("(")[0].strip()
        icon = IND_ICON.get(campo, "•")
        line = f"{icon} {short}: {valor_txt}"
        if status:
            line += f" — {status}"
        lines.append(line)
        shown.add(campo)

    lines += [f"{ICON['legenda']} Legenda: {LEGENDA_RAPIDA}", ""]
    lines.append(f"{ICON['orient_gestor']} Orientações operacionais")
    lines.append(f"• Gestor municipal — {acoes.get('gestor') or '—'}")
    lines.append(f"• Atenção farmacêutica municipal (CBAF/Visa) — {acoes.get('farmacia') or '—'}")
    lines.append(f"• Povos e territórios (Vigibarragens) — {acoes.get('territorios') or '—'}")
    lines.append(f"• Profissionais de saúde — {acoes.get('profissional') or '—'}")
    lines.append(f"• População — {acoes.get('populacao') or '—'}")

    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientações da IA (revisar)", str(p["orientacao_ia"])]

    footer = (
        "Relatório dedicado Vigidesastre Cuiabá · validar no território."
        if cuiaba
        else "Fonte: SIS Clima-Saúde MT · validar no território."
    )
    lines += ["", f"{ICON['rodape']} {footer}"]
    return "\n".join(lines)


def _format_sectioned_html(title: str, txt: str, sections: list[tuple[str, str]]) -> str:
    blocks: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] = ("Cabeçalho", [])
    for line in txt.splitlines():
        matched = None
        for sec_title, icon in sections:
            if sec_title in line or (icon in line and any(t in line for t, _ in sections)):
                matched = sec_title
                break
        if matched and current[1] and matched != current[0]:
            blocks.append(current)
            current = (matched, [line])
        else:
            if matched and not current[1]:
                current = (matched, [line])
            else:
                current[1].append(line)
    if current[1]:
        blocks.append(current)

    parts = []
    for sec_title, lines in blocks:
        body = html.escape("\n".join(lines))
        parts.append(
            f"<section style='border:1px solid #e2e8f0;border-radius:12px;padding:14px;margin:0 0 12px;background:#fff'>"
            f"<h2 style='margin:0 0 8px;font-size:16px'>{html.escape(sec_title)}</h2>"
            f"<pre style='white-space:pre-wrap;font-family:Segoe UI,Arial,sans-serif;margin:0'>{body}</pre>"
            f"</section>"
        )
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;background:#f8fafc;padding:16px">
      <h1 style="margin:0 0 6px">{ICON['titulo']} {html.escape(title)}</h1>
      <p style="color:#64748b;margin:0 0 14px">Gerado em {html.escape(now_iso())}</p>
      {''.join(parts)}
    </div>
    """


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
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS alertas_enviados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                nivel_anterior TEXT,
                nivel_novo TEXT,
                titulo TEXT,
                mensagem TEXT,
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


def _escopo_icon(escopo: str) -> str:
    return {
        "estadual": ICON["estado"],
        "regional": ICON["regional"],
        "municipal": ICON["municipal"],
        "cuiaba": ICON["cuiaba"],
    }.get(escopo, "📌")


def _ai_orientacao(payload: dict[str, Any]) -> str | None:
    if payload.get("escopo") == "estadual":
        return _ai_orientacao_ses(payload)
    if not (
        as_bool(env("USE_AI_ALERT_TEXT", "false"), False)
        or as_bool(env("USE_LLM_REPORT", "false"), False)
    ):
        return None
    try:
        from sisclima.ai.report_generator import maybe_llm_report

        inds = payload.get("indicadores") or []
        ctx = {
            "tarefa": "orientacao_alerta_cievs",
            "instrucao": (
                "Escreva 5 a 7 bullets curtos de orientação para plantão. "
                "NÃO invente números. Formato '- '. Sem markdown."
            ),
            "alerta": {
                "escopo": payload.get("escopo"),
                "alvo": payload.get("alvo_nome"),
                "nivel": payload.get("nivel"),
                "motivo": str(payload.get("motivo") or "")[:600],
                "indicadores": inds[:12],
                "predicao": payload.get("predicao"),
            },
        }
        txt = maybe_llm_report(ctx)
        if not txt:
            return None
        txt = re.sub(r"^```\w*\n?", "", txt.strip())
        txt = re.sub(r"\n?```$", "", txt.strip())
        return txt.strip()[:1800]
    except Exception as exc:  # noqa: BLE001
        log.warning("IA de orientação indisponível: %s", exc)
        return None


def _active_layers() -> set[str]:
    """Camadas geradas/persistidas. Padrão: todas (envio central continua só SES)."""
    raw = env("ALERT_LAYERS", "ses,regionais,municipais,cuiaba") or "ses,regionais,municipais,cuiaba"
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _select_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Seleciona payloads por camada (para meta/persistência lógica). Envio é separado."""
    layers = _active_layers()
    max_mun = int(env("ALERT_MAX_MUNICIPIOS", "12") or 12)
    max_reg = int(env("ALERT_MAX_REGIONAIS", "20") or 20)

    out: list[dict[str, Any]] = []
    if "ses" in layers or "estadual" in layers:
        out.extend([p for p in payloads if p.get("escopo") == "estadual"])

    if "regionais" in layers or "regional" in layers:
        regionais = [p for p in payloads if p.get("escopo") == "regional"]
        regionais = sorted(
            regionais, key=lambda p: STAGE_ORDER.get(_norm_level(p.get("nivel")), -1), reverse=True
        )[:max_reg]
        out.extend(regionais)

    cuiaba_ids = {str(p.get("alvo_id")) for p in payloads if p.get("escopo") == "cuiaba"}

    if "municipais" in layers or "municipal" in layers:
        min_mun = _norm_level(env("ALERT_MIN_LEVEL_MUNICIPAL", env("ALERT_MIN_LEVEL", "laranja")))
        min_mun_rank = STAGE_ORDER.get(min_mun, 2)
        send_all_mun = as_bool(env("ALERT_SEND_ALL_MUNICIPIOS", "false"), False)
        municipais = [p for p in payloads if p.get("escopo") == "municipal"]
        if "cuiaba" in layers and cuiaba_ids:
            municipais = [p for p in municipais if str(p.get("alvo_id")) not in cuiaba_ids]
        if not send_all_mun:
            municipais = [
                p for p in municipais if STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_mun_rank
            ]

        def _mun_key(p: dict) -> tuple:
            rank = STAGE_ORDER.get(_norm_level(p.get("nivel")), -1)
            score = _parse_num(p.get("score")) or 0.0
            return (rank, score)

        municipais = sorted(municipais, key=_mun_key, reverse=True)[:max_mun]
        out.extend(municipais)

    if "cuiaba" in layers:
        out.extend([p for p in payloads if p.get("escopo") == "cuiaba"])
    return out


def _central_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Somente estadual → Menandes / CIEVS (ALERT_EMAIL_TO + TELEGRAM_CHAT_ID)."""
    if as_bool(env("ALERT_CENTRAL_ONLY_SES", "true"), True):
        return [p for p in payloads if p.get("escopo") in CENTRAL_SCOPES]
    return list(payloads)


def _territorial_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in payloads if p.get("escopo") in TERRITORIAL_SCOPES]


def _enrich_payloads_with_ai(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_extra = int(env("ALERT_AI_MAX_PACKS", "0") or 0)
    used_extra = 0
    for p in payloads:
        escopo = p.get("escopo")
        if escopo == "estadual":
            p["orientacoes_setores"] = build_orientacoes_ses_setores(p)
            ai_on = as_bool(env("USE_AI_ALERT_TEXT", "false"), False) or as_bool(
                env("USE_LLM_REPORT", "false"), False
            )
            p["orientacao_ia"] = _ai_orientacao(p) if max_extra >= 0 and ai_on else None
            continue
        if escopo == "regional":
            p["orientacoes_regionais"] = build_orientacoes_regional(p)
            if used_extra < max_extra:
                p["orientacao_ia"] = _ai_orientacao(p)
                used_extra += 1
            continue
        if escopo in {"municipal", "cuiaba"}:
            p["orientacoes_municipais"] = build_orientacoes_municipal(p)
            # espelha no dict clássico para compatibilidade
            o = p["orientacoes_municipais"]
            p["orientacoes"] = {
                "gestor": o.get("gestor"),
                "profissional": o.get("profissional"),
                "populacao": o.get("populacao"),
            }
            if escopo == "cuiaba" and used_extra < max_extra:
                p["orientacao_ia"] = _ai_orientacao(p)
                used_extra += 1
            elif escopo == "municipal" and used_extra < max_extra:
                p["orientacao_ia"] = _ai_orientacao(p)
                used_extra += 1
            continue
    return payloads


def format_payload_telegram(p: dict[str, Any], *, compact: bool = False) -> str:
    escopo = p.get("escopo")
    if escopo == "estadual":
        txt = format_ses_telegram(p)
    elif escopo == "regional":
        txt = format_regional_telegram(p)
    elif escopo == "cuiaba":
        txt = format_municipal_telegram(p, cuiaba=True)
    elif escopo == "municipal":
        txt = format_municipal_telegram(p, cuiaba=False)
    else:
        txt = format_municipal_telegram(p, cuiaba=False)
    if compact and len(txt) > 3900:
        return txt[:3890] + "\n…"
    return txt


def format_payload_html(p: dict[str, Any]) -> str:
    escopo = p.get("escopo")
    if escopo == "estadual":
        return format_ses_html(p)
    if escopo == "regional":
        return _format_sectioned_html(
            f"Alerta regional — {p.get('alvo_nome')}",
            format_regional_telegram(p),
            [
                ("Resumo executivo", ICON["resumo"]),
                ("Situação da regional", ICON["indicadores"]),
                ("Ações para a gestão regional", ICON["orient_gestor"]),
                ("Municípios prioritários", ICON["prioridade"]),
            ],
        )
    title = (
        "Alerta 4/4 — Vigidesastre Cuiabá"
        if escopo == "cuiaba"
        else f"Alerta municipal — {p.get('alvo_nome')}"
    )
    return _format_sectioned_html(
        title,
        format_municipal_telegram(p, cuiaba=(escopo == "cuiaba")),
        [
            ("Resumo executivo", ICON["resumo"]),
            ("Indicadores do município", ICON["indicadores"]),
            ("Orientações operacionais", ICON["orient_gestor"]),
        ],
    )


def build_multilevel_pack(resumo: pd.DataFrame | None = None) -> tuple[list[dict[str, Any]], str, dict]:
    resumo = resumo if resumo is not None else read_table("resumo_municipal_atual")
    alerta = read_table("alerta_integrado_sis_titan") if table_exists("alerta_integrado_sis_titan") else pd.DataFrame()
    pred = (
        read_table("predicao_calor_7d_municipal_v6")
        if table_exists("predicao_calor_7d_municipal_v6")
        else pd.DataFrame()
    )
    # Gera todas as camadas; persiste todas; envio central filtra só SES.
    payloads = build_alertas_multinivel(
        resumo,
        alerta if not alerta.empty else None,
        pred if not pred.empty else None,
        min_level="verde",
    )
    selected = _select_payloads(payloads)
    selected = _enrich_payloads_with_ai(selected)
    try:
        persist_payloads(payloads)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao persistir alertas_multinivel_v1: %s", exc)

    central = _central_payloads(selected)
    territorial = _territorial_payloads(selected)

    nivel_est = "cinza"
    for p in payloads:
        if p.get("escopo") == "estadual":
            nivel_est = _norm_level(p.get("nivel"))
            break
    # Fingerprint SES: nível + motivo + data dos dados (KPIs novos com mesmo texto não ficam travados)
    fp_src = "|".join(
        f"{p.get('escopo')}:{p.get('alvo_id')}:{p.get('nivel')}:"
        f"{p.get('data_referencia')}:{str(p.get('motivo') or '')[:80]}"
        for p in central
    ) or f"sem_ses|{nivel_est}"
    fingerprint = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()[:16]
    contacts_meta = summarize_contacts()
    meta = {
        "nivel": nivel_est,
        "n_payloads": len(selected),
        "n_gerados": len(payloads),
        "n_regionais": sum(1 for p in selected if p.get("escopo") == "regional"),
        "n_municipais": sum(1 for p in selected if p.get("escopo") == "municipal"),
        "n_cuiaba": sum(1 for p in selected if p.get("escopo") == "cuiaba"),
        "n_ses": sum(1 for p in selected if p.get("escopo") == "estadual"),
        "n_central_envio": len(central),
        "n_territorial_pendente": len(territorial),
        "fanout": contacts_meta,
        "fingerprint": fingerprint,
        "com_ia": sum(1 for p in selected if p.get("orientacao_ia")),
        "layers": sorted(_active_layers()),
    }
    return selected, fingerprint, meta


def _split_telegram(text: str) -> list[str]:
    if len(text) <= 3900:
        return [text]
    chunks = []
    cur = ""
    for para in text.split("\n"):
        line = para + "\n"
        if len(cur) + len(line) > 3800:
            chunks.append(cur.rstrip() + "\n…")
            cur = "(cont.)\n" + line
        else:
            cur += line
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


def _send_telegram_batches(payloads: list[dict[str, Any]], *, chat_id: str | None = None) -> bool:
    """Envia boletins ao chat indicado (padrão: canal central TELEGRAM_CHAT_ID)."""
    ok_any = False
    order = {"estadual": 0, "regional": 1, "municipal": 2, "cuiaba": 3}
    ordered = sorted(payloads, key=lambda p: (order.get(str(p.get("escopo")), 9), str(p.get("alvo_nome") or "")))
    for p in ordered:
        txt = format_payload_telegram(p, compact=False)
        for chunk in _split_telegram(txt):
            if send_telegram(chunk, chat_id=chat_id):
                ok_any = True
            time.sleep(0.35)
    return ok_any


def _send_email_pack(payloads: list[dict[str, Any]], meta: dict, *, to: str | list[str] | None = None) -> bool:
    if not payloads:
        return False
    niv = _norm_level(meta.get("nivel") or (payloads[0].get("nivel") if payloads else "cinza"))
    only_ses = len(payloads) == 1 and payloads[0].get("escopo") == "estadual"
    if only_ses:
        p = payloads[0]
        subject = f"[SIS] {ICON['estado']} Alerta SES-MT / CIEVS — {LEVEL_LABEL.get(niv, niv)}"
        plain = format_ses_telegram(p)
        return send_email(subject, plain, html_body=format_ses_html(p), to=to)

    subject = (
        f"[SIS Clima-Saúde] {EMOJI.get(niv, '⚪')} Boletim · "
        f"{niv.upper()} · {len(payloads)} alerta(s)"
    )
    body_html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;background:#f8fafc;padding:18px">
      <h1 style="margin:0 0 6px">{ICON['titulo']} SIS Clima-Saúde MT</h1>
      <p style="margin:0 0 16px;color:#334155">Boletim operacional · gerado em {html.escape(now_iso())}</p>
      {''.join(format_payload_html(p) for p in payloads)}
    </div>
    """
    plain = "\n\n".join(format_payload_telegram(p, compact=False) for p in payloads[:8])
    return send_email(subject, plain, html_body=body_html, to=to)


def _fanout_territorial(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Encaminha regionais/municipais/Cuiabá aos destinatários da planilha (nunca ao canal central)."""
    territorial = _territorial_payloads(payloads)
    if not territorial:
        return {"status": "sem_territoriais", "enviados": 0, "sem_destinatario": 0}

    if not fanout_enabled():
        log.info(
            "Territoriais gerados=%d · fan-out adiado (planilha ausente ou ALERT_FANOUT_ENABLED=false). "
            "Canal central CIEVS recebe somente o estadual.",
            len(territorial),
        )
        return {
            "status": "adiado_sem_contatos",
            "gerados": len(territorial),
            "enviados": 0,
            "contatos": summarize_contacts(),
        }

    enviados = 0
    sem_dest = 0
    for p in territorial:
        emails, chats = recipients_for(
            str(p.get("escopo")),
            regional=str(p.get("alvo_nome") if p.get("escopo") == "regional" else p.get("regional") or ""),
            cod_ibge=str(p.get("alvo_id") or ""),
            municipio=str(p.get("alvo_nome") or ""),
        )
        if not emails and not chats:
            sem_dest += 1
            continue
        txt = format_payload_telegram(p, compact=False)
        html_body = format_payload_html(p)
        subject = f"[SIS] {p.get('titulo') or p.get('alvo_nome')}"
        if emails:
            if send_email(subject, txt, html_body=html_body, to=emails):
                enviados += 1
            time.sleep(0.2)
        for chat in chats:
            for chunk in _split_telegram(txt):
                if send_telegram(chunk, chat_id=chat):
                    enviados += 1
                time.sleep(0.35)

    status = "enviado" if enviados else "sem_envio"
    log.info("Fan-out territorial %s · enviados=%s sem_dest=%s", status, enviados, sem_dest)
    return {"status": status, "enviados": enviados, "sem_destinatario": sem_dest, "gerados": len(territorial)}


def send_digest(
    *,
    force: bool = False,
    skip_cooldown: bool = False,
    resumo: pd.DataFrame | None = None,
) -> dict[str, Any]:
    _ensure_digest_table()
    payloads, fingerprint, meta = build_multilevel_pack(resumo)
    nivel = meta["nivel"]
    central = _central_payloads(payloads)

    if not force and not as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false"), False):
        out = {"status": "bloqueado_por_config", "nivel": nivel, "fingerprint": fingerprint}
        log.info("Digest bloqueado: SEND_ALERT_ON_LEVEL_CHANGE=false")
        return out

    if not central and not payloads:
        return {"status": "sem_payloads", "nivel": nivel}

    if not min_level_ok(nivel) and not force:
        out = {"status": "abaixo_do_minimo", "nivel": nivel, "min": env("ALERT_MIN_LEVEL", "laranja")}
        log.info("Digest não enviado: nível %s < mínimo", nivel)
        return out

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

    # 1) Canal central CIEVS: somente estadual
    tg_ok = _send_telegram_batches(central) if central else False
    em_ok = _send_email_pack(central, meta) if central else False

    # 2) Territoriais: gerados sempre; envio só com planilha + ALERT_FANOUT_ENABLED
    fanout = _fanout_territorial(payloads)

    results = {
        "email": em_ok,
        "telegram": tg_ok,
        "webhook": False,
        "n_payloads_central": len(central),
        "n_payloads_gerados": meta.get("n_gerados", len(payloads)),
        "fanout": fanout,
    }
    status = "enviado" if (tg_ok or em_ok or fanout.get("enviados")) else "registrado_sem_canal"
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
                f"[SIS] SES/CIEVS {EMOJI.get(nivel,'⚪')} {nivel.upper()}",
                (
                    f"central_ses={len(central)}; gerados={meta.get('n_gerados')}; "
                    f"regionais={meta.get('n_regionais')}; municipais={meta.get('n_municipais')}; "
                    f"fanout={fanout.get('status')}"
                ),
                json.dumps({"tipo": "multinivel", **results}, ensure_ascii=False),
                status,
            ),
        )
    log.info("Digest multinível %s · %s", status, results)
    return {"status": status, "canais": results, **meta}


def build_digest_message(resumo: pd.DataFrame | None = None) -> tuple[str, str, str, dict]:
    payloads, fingerprint, meta = build_multilevel_pack(resumo)
    subject = f"[SIS Clima-Saúde] {EMOJI.get(meta['nivel'],'⚪')} SES/CIEVS {meta['nivel'].upper()}"
    ses = next((p for p in payloads if p.get("escopo") == "estadual"), None)
    message = format_ses_telegram(ses) if ses else "Sem alerta estadual gerado."
    return subject, message, fingerprint, meta
