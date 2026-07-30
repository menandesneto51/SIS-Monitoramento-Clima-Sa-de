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
    "ocupação alerta ≥75% | sensação alerta >32 °C | risco 3d alerta ≥7 · intensificado ≥12 · pleno ≥18"
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
    saf = (
        "Checar estoque estadual/regional de soro de reidratação, soro endovenoso, "
        "antitérmicos e insumos para hipertermia/desidratação"
    )
    if arbo is not None and arbo >= 10:
        saf += "; reforçar insumos para dengue/arboviroses."
    else:
        saf += "."
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
        f"antecipar comunicação aos {n_up} municípios com tendência de piora em ~7 dias."
    )
    return {
        "comando_cievs": cievs,
        "gestao_hospitalar": hospitalar,
        "regulacao": regulacao,
        "assistencia_farmaceutica": saf,
        "saude_trabalhador": trabalhador,
        "atencao_primaria": aps,
        "vigilancia_ambiental": amb,
        "comunicacao_risco": comunicacao,
    }


def _kpi_line(ind: dict[str, Any]) -> str | None:
    campo = str(ind.get("campo") or "")
    if campo in {"n_municipios", "distribuicao_niveis", "cobertura_ocupacao"}:
        return None
    icon = IND_ICON.get(campo, "•")
    rotulo = str(ind.get("rotulo") or campo)
    # rótulos curtos no painel
    short = {
        "score": "Pontuação (pior)",
        "score_alerta_integrado": "Pontuação integrada (pior)",
        "tmax": "Tmáx pico",
        "utci_proxy": "Sensação pico",
        "risco_cumulativo_3d": "Risco 3d pico",
        "pressao_calor_pct": "Pressão calor pico",
        "pm25_ugm3": "PM2,5 pico",
        "ocupacao_leitos_pct": "Ocupação estadual",
        "incidencia_arbovirus_100k": "Arboviroses pico /100 mil",
        "casos_srag": "SRAG (soma)",
    }.get(campo, rotulo)
    valor = ind.get("valor")
    status = _status_for(campo, valor)
    if campo in {"score", "score_alerta_integrado"}:
        num = _parse_num(valor)
        valor_txt = f"{int(num)}/4" if num is not None else str(valor)
    elif campo == "ocupacao_leitos_pct":
        valor_txt = f"{valor}%" if "%" not in str(valor) else str(valor)
    elif campo == "pressao_calor_pct":
        valor_txt = f"{valor} /15"
    else:
        valor_txt = str(valor)
    line = f"{icon} {short}: {valor_txt}"
    if status:
        line += f" — {status}"
    return line


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
    return " | ".join(parts)


def _ai_is_redundant(ai_txt: str, setores: dict[str, str]) -> bool:
    if not ai_txt or len(ai_txt.strip()) < 80:
        return True
    # se a IA só ecoa os setores, omitir
    blob = " ".join(setores.values()).lower()
    bullets = [b.strip("-• ").lower() for b in ai_txt.splitlines() if b.strip()]
    if not bullets:
        return True
    overlap = 0
    for b in bullets:
        # similaridade grosseira: primeiras 40 chars aparecem nos setores
        key = b[:40]
        if key and key in blob:
            overlap += 1
    return overlap >= max(3, len(bullets) - 1)


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
        f"🕒 {p.get('gerado_em')}",
        "",
        f"{ICON['resumo']} Resumo executivo",
        f"🏘️ {n_mun} municípios | {dist_txt}",
        f"{ICON['motivo']} {str(p.get('motivo') or '—')[:280]}",
        f"{ICON['predicao']} {pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['indicadores']} Situação estadual",
    ]
    for ind in inds:
        line = _kpi_line(ind)
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
    txt = format_ses_telegram(p)
    # parte em blocos por cabeçalhos conhecidos
    sections = [
        ("Resumo executivo", ICON["resumo"]),
        ("Situação estadual", ICON["indicadores"]),
        ("Ações por setor", ICON["orient_gestor"]),
        ("Orientações da IA", ICON["ia"]),
        ("Municípios prioritários", ICON["prioridade"]),
    ]
    blocks: list[tuple[str, list[str]]] = []
    current = ("Cabeçalho", [])
    for line in txt.splitlines():
        matched = None
        for title, icon in sections:
            if title in line or (icon in line and any(t in line for t, _ in sections)):
                matched = title
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
    for title, lines in blocks:
        body = html.escape("\n".join(lines))
        parts.append(
            f"<section style='border:1px solid #e2e8f0;border-radius:12px;padding:14px;margin:0 0 12px;background:#fff'>"
            f"<h2 style='margin:0 0 8px;font-size:16px'>{html.escape(title)}</h2>"
            f"<pre style='white-space:pre-wrap;font-family:Segoe UI,Arial,sans-serif;margin:0'>{body}</pre>"
            f"</section>"
        )
    return f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;background:#f8fafc;padding:16px">
      <h1 style="margin:0 0 6px">{ICON['titulo']} Alerta 1/4 — Gestão SES-MT / CIEVS</h1>
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
    raw = env("ALERT_LAYERS", "ses,regionais,municipais,cuiaba") or "ses,regionais,municipais,cuiaba"
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _select_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layers = _active_layers()
    min_lv = _norm_level(env("ALERT_MIN_LEVEL", "laranja"))
    min_rank = STAGE_ORDER.get(min_lv, 2)
    max_mun = int(env("ALERT_MAX_MUNICIPIOS", "12") or 12)
    max_reg = int(env("ALERT_MAX_REGIONAIS", "20") or 20)

    out: list[dict[str, Any]] = []
    if "ses" in layers or "estadual" in layers:
        out.extend([p for p in payloads if p.get("escopo") == "estadual"])

    if "regionais" in layers or "regional" in layers:
        regionais = [
            p
            for p in payloads
            if p.get("escopo") == "regional" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
        ]
        regionais = sorted(
            regionais, key=lambda p: STAGE_ORDER.get(_norm_level(p.get("nivel")), -1), reverse=True
        )[:max_reg]
        out.extend(regionais)

    if "municipais" in layers or "municipal" in layers:
        municipais = [
            p
            for p in payloads
            if p.get("escopo") == "municipal" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
        ]

        def _mun_key(p: dict) -> tuple:
            rank = STAGE_ORDER.get(_norm_level(p.get("nivel")), -1)
            score = 0.0
            for ind in p.get("indicadores") or []:
                if ind.get("campo") in {"score", "score_alerta_integrado"}:
                    try:
                        score = float(str(ind.get("valor")).replace(",", ".").split()[0])
                    except Exception:
                        pass
                    break
            return (rank, score)

        municipais = sorted(municipais, key=_mun_key, reverse=True)[:max_mun]
        out.extend(municipais)

    if "cuiaba" in layers:
        cui = [
            p
            for p in payloads
            if p.get("escopo") == "cuiaba" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
        ]
        already = {str(p.get("alvo_id")) for p in out if p.get("escopo") == "municipal"}
        for p in cui:
            if str(p.get("alvo_id")) not in already:
                out.append(p)
    return out


def _enrich_payloads_with_ai(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_extra = int(env("ALERT_AI_MAX_PACKS", "3") or 3)
    used_extra = 0
    for p in payloads:
        escopo = p.get("escopo")
        if escopo == "estadual":
            p["orientacoes_setores"] = build_orientacoes_ses_setores(p)
            p["orientacao_ia"] = _ai_orientacao(p)
            continue
        if escopo == "cuiaba":
            p["orientacao_ia"] = _ai_orientacao(p)
            continue
        if escopo in {"regional", "municipal"} and used_extra < max_extra:
            p["orientacao_ia"] = _ai_orientacao(p)
            used_extra += 1
    return payloads


def format_payload_telegram(p: dict[str, Any], *, compact: bool = False) -> str:
    if p.get("escopo") == "estadual":
        txt = format_ses_telegram(p)
        # Telegram: envia em chunks no caller; aqui só limita se compact
        return txt if not compact or len(txt) <= 3900 else txt[:3890] + "\n…"

    escopo = str(p.get("escopo") or "")
    icon = _escopo_icon(escopo)
    niv = _norm_level(p.get("nivel"))
    lines = [
        f"{icon} {p.get('titulo') or 'Alerta SIS'}",
        f"{EMOJI.get(niv, '⚪')} Nível: {LEVEL_LABEL.get(niv, niv)}",
        f"🎯 Alvo: {p.get('alvo_nome')} · 🏘️ Mun.: {p.get('n_municipios')}",
        f"🕒 {p.get('gerado_em')}",
        "",
        f"{ICON['motivo']} Motivo",
        str(p.get("motivo") or "—")[:500],
        "",
        f"{ICON['indicadores']} Indicadores",
    ]
    inds = p.get("indicadores") or []
    limit = 6 if compact else 12
    for ind in inds[:limit]:
        campo = str(ind.get("campo") or "")
        i = IND_ICON.get(campo, "•")
        lines.append(f"{i} {ind.get('rotulo')}: {ind.get('valor')}")
    pred = p.get("predicao") or {}
    lines += [
        "",
        f"{ICON['predicao']} Predição ~7d",
        f"{pred.get('icone_predicao', '🔮')} {pred.get('resumo', '—')}",
        "",
        f"{ICON['orient_gestor']} Gestor",
        ((p.get("orientacoes") or {}).get("gestor") or "—"),
        "",
        f"{ICON['orient_prof']} Profissionais",
        ((p.get("orientacoes") or {}).get("profissional") or "—"),
    ]
    if not compact:
        lines += [
            "",
            f"{ICON['orient_pop']} População",
            ((p.get("orientacoes") or {}).get("populacao") or "—"),
        ]
    if p.get("orientacao_ia"):
        lines += ["", f"{ICON['ia']} Orientação IA (revisar)", str(p.get("orientacao_ia"))]
    lines += [
        "",
        f"{ICON['rodape']} Validar no painel antes de comunicação oficial.",
        "Lista de contatos provisória — aguardando atualização CIEVS.",
    ]
    txt = "\n".join(lines)
    return txt if len(txt) <= 3900 else txt[:3890] + "\n…"


def format_payload_html(p: dict[str, Any]) -> str:
    if p.get("escopo") == "estadual":
        return format_ses_html(p)
    escopo = str(p.get("escopo") or "")
    icon = _escopo_icon(escopo)
    niv = _norm_level(p.get("nivel"))
    inds_html = "".join(
        f"<li>{html.escape(IND_ICON.get(str(i.get('campo')), '•'))} "
        f"<b>{html.escape(str(i.get('rotulo')))}:</b> {html.escape(str(i.get('valor')))}</li>"
        for i in (p.get("indicadores") or [])[:14]
    )
    o = p.get("orientacoes") or {}
    pred = p.get("predicao") or {}
    ai = p.get("orientacao_ia")
    ai_block = (
        f"<h3>{ICON['ia']} Orientação IA (revisar)</h3><pre style='white-space:pre-wrap;font-family:inherit'>"
        f"{html.escape(str(ai))}</pre>"
        if ai
        else ""
    )
    return f"""
    <section style="border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:0 0 18px;background:#fff">
      <h2 style="margin:0 0 8px">{icon} {html.escape(str(p.get('titulo') or ''))}</h2>
      <p style="margin:0 0 8px">{EMOJI.get(niv,'⚪')} <b>{html.escape(LEVEL_LABEL.get(niv, niv))}</b>
         · 🎯 {html.escape(str(p.get('alvo_nome')))} · 🏘️ {html.escape(str(p.get('n_municipios')))}</p>
      <p style="color:#64748b;margin:0 0 12px">🕒 {html.escape(str(p.get('gerado_em') or ''))}</p>
      <h3>{ICON['motivo']} Motivo</h3>
      <p>{html.escape(str(p.get('motivo') or '—')[:800])}</p>
      <h3>{ICON['indicadores']} Indicadores</h3>
      <ul>{inds_html or '<li>—</li>'}</ul>
      <h3>{ICON['predicao']} Predição ~7 dias</h3>
      <p>{html.escape(str(pred.get('icone_predicao') or '🔮'))} {html.escape(str(pred.get('resumo') or '—'))}</p>
      <h3>{ICON['orient_gestor']} Gestor</h3><p>{html.escape(str(o.get('gestor') or '—'))}</p>
      <h3>{ICON['orient_prof']} Profissionais</h3><p>{html.escape(str(o.get('profissional') or '—'))}</p>
      <h3>{ICON['orient_pop']} População</h3><p>{html.escape(str(o.get('populacao') or '—'))}</p>
      {ai_block}
    </section>
    """


def build_multilevel_pack(resumo: pd.DataFrame | None = None) -> tuple[list[dict[str, Any]], str, dict]:
    resumo = resumo if resumo is not None else read_table("resumo_municipal_atual")
    alerta = read_table("alerta_integrado_sis_titan") if table_exists("alerta_integrado_sis_titan") else pd.DataFrame()
    pred = (
        read_table("predicao_calor_7d_municipal_v6")
        if table_exists("predicao_calor_7d_municipal_v6")
        else pd.DataFrame()
    )
    # Para o pack SES legível, gera a partir de verde e filtra no select
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

    nivel_est = "cinza"
    for p in selected:
        if p.get("escopo") == "estadual":
            nivel_est = _norm_level(p.get("nivel"))
            break
    fp_src = "|".join(
        f"{p.get('escopo')}:{p.get('alvo_id')}:{p.get('nivel')}:{len(p.get('indicadores') or [])}"
        for p in selected[:25]
    )
    fingerprint = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()[:16]
    meta = {
        "nivel": nivel_est,
        "n_payloads": len(selected),
        "n_regionais": sum(1 for p in selected if p.get("escopo") == "regional"),
        "n_municipais": sum(1 for p in selected if p.get("escopo") == "municipal"),
        "n_ses": sum(1 for p in selected if p.get("escopo") == "estadual"),
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


def _send_telegram_batches(payloads: list[dict[str, Any]]) -> bool:
    ok_any = False
    for p in payloads:
        if p.get("escopo") == "estadual":
            for chunk in _split_telegram(format_ses_telegram(p)):
                if send_telegram(chunk):
                    ok_any = True
                time.sleep(0.35)
            break

    regs = [p for p in payloads if p.get("escopo") == "regional"]
    if regs:
        header = f"{ICON['regional']} ALERTAS REGIONAIS ({len(regs)})\n" + ("─" * 28)
        chunks: list[str] = []
        buf = header
        for p in regs:
            block = "\n\n" + format_payload_telegram(p, compact=True)
            if len(buf) + len(block) > 3800:
                chunks.append(buf)
                buf = f"{ICON['regional']} REGIONAIS (cont.)\n" + block
            else:
                buf += block
        chunks.append(buf)
        for c in chunks:
            if send_telegram(c):
                ok_any = True

    muns = [p for p in payloads if p.get("escopo") in {"municipal", "cuiaba"}]
    if muns:
        header = f"{ICON['municipal']} ALERTAS MUNICIPAIS / VIGIDESASTRE ({len(muns)})\n" + ("─" * 28)
        buf = header
        chunks = []
        for p in muns:
            block = "\n\n" + format_payload_telegram(p, compact=True)
            if len(buf) + len(block) > 3800:
                chunks.append(buf)
                buf = f"{ICON['municipal']} MUNICIPAIS (cont.)\n" + block
            else:
                buf += block
        chunks.append(buf)
        for c in chunks:
            if send_telegram(c):
                ok_any = True
    return ok_any


def _send_email_pack(payloads: list[dict[str, Any]], meta: dict) -> bool:
    niv = _norm_level(meta.get("nivel"))
    only_ses = meta.get("n_payloads") == 1 and meta.get("n_ses") == 1
    if only_ses:
        p = next(x for x in payloads if x.get("escopo") == "estadual")
        subject = f"[SIS] {ICON['estado']} Alerta SES-MT / CIEVS — {LEVEL_LABEL.get(niv, niv)}"
        plain = format_ses_telegram(p)
        return send_email(subject, plain, html_body=format_ses_html(p))

    subject = (
        f"[SIS Clima-Saúde] {EMOJI.get(niv, '⚪')} Boletim multinível CIEVS — "
        f"{niv.upper()} · {meta.get('n_regionais', 0)} regionais · {meta.get('n_municipais', 0)} municípios"
    )
    body_html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;background:#f8fafc;padding:18px">
      <h1 style="margin:0 0 6px">{ICON['titulo']} SIS Clima-Saúde MT</h1>
      <p style="margin:0 0 16px;color:#334155">Boletim operacional multinível · gerado em {html.escape(now_iso())}</p>
      {''.join(format_payload_html(p) for p in payloads)}
    </div>
    """
    plain = "\n\n".join(format_payload_telegram(p, compact=False) for p in payloads[:8])
    return send_email(subject, plain, html_body=body_html)


def send_digest(
    *,
    force: bool = False,
    skip_cooldown: bool = False,
    resumo: pd.DataFrame | None = None,
) -> dict[str, Any]:
    _ensure_digest_table()
    payloads, fingerprint, meta = build_multilevel_pack(resumo)
    nivel = meta["nivel"]

    if not force and not as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false"), False):
        out = {"status": "bloqueado_por_config", "nivel": nivel, "fingerprint": fingerprint}
        log.info("Digest bloqueado: SEND_ALERT_ON_LEVEL_CHANGE=false")
        return out

    if not payloads:
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

    tg_ok = _send_telegram_batches(payloads)
    em_ok = _send_email_pack(payloads, meta)
    results = {"email": em_ok, "telegram": tg_ok, "webhook": False, "n_payloads": len(payloads)}
    status = "enviado" if (tg_ok or em_ok) else "registrado_sem_canal"
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
                f"[SIS] Multinível {EMOJI.get(nivel,'⚪')} {nivel.upper()}",
                (
                    f"payloads={len(payloads)}; regionais={meta.get('n_regionais')}; "
                    f"municipais={meta.get('n_municipais')}; ia={meta.get('com_ia')}"
                ),
                json.dumps({"tipo": "multinivel", **results}, ensure_ascii=False),
                status,
            ),
        )
    log.info("Digest multinível %s · %s", status, results)
    return {"status": status, "canais": results, **meta}


def build_digest_message(resumo: pd.DataFrame | None = None) -> tuple[str, str, str, dict]:
    payloads, fingerprint, meta = build_multilevel_pack(resumo)
    subject = f"[SIS Clima-Saúde] {EMOJI.get(meta['nivel'],'⚪')} Multinível {meta['nivel'].upper()}"
    ses = next((p for p in payloads if p.get("escopo") == "estadual"), None)
    message = format_ses_telegram(ses) if ses else "\n\n".join(
        format_payload_telegram(p, compact=True) for p in payloads[:5]
    )
    return subject, message, fingerprint, meta
