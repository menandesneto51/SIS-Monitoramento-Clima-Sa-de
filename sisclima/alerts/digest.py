# -*- coding: utf-8 -*-
"""Boletins CIEVS multinível (estadual / regional / municipal) com indicadores, ícones e IA."""
from __future__ import annotations

import hashlib
import html
import json
import re
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
    "orient_gestor": "👔",
    "orient_prof": "🩺",
    "orient_pop": "👥",
    "ia": "🤖",
    "fontes": "📚",
    "rodape": "✅",
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
    "indice_saturacao_solo": "💧",
    "incidencia_arbovirus_100k": "🦟",
    "zscore_arbovirus": "🦟",
    "casos_srag": "🫁",
    "incidencia_srag_100k": "🫁",
    "indice_tensao_climatica": "🌡️",
    "indice_carga_saude": "💊",
    "indice_vigilancia_integrada": "👁️",
    "tendencia_7d": "📉",
    "nivel_predicao_7d": "🔮",
    "componente_dominante": "🧩",
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
    """Orientações curtas via LLM (Gemini/OpenAI-compatible). Não inventa indicadores."""
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
                "Você é assessoria técnica do CIEVS/SES-MT. Em português claro e operacional, "
                "escreva 5 a 7 bullets curtos de orientação para plantão (gestor, assistência e comunicação). "
                "NÃO invente números nem municípios. Use apenas o JSON. Sem markdown pesado."
            ),
            "alerta": {
                "escopo": payload.get("escopo"),
                "alvo": payload.get("alvo_nome"),
                "nivel": payload.get("nivel"),
                "nivel_rotulo": payload.get("nivel_rotulo"),
                "motivo": str(payload.get("motivo") or "")[:600],
                "indicadores": inds[:12],
                "predicao": payload.get("predicao"),
                "orientacoes_base": payload.get("orientacoes"),
            },
        }
        txt = maybe_llm_report(ctx)
        if not txt:
            return None
        # Limpa cercas de código se vierem
        txt = re.sub(r"^```\w*\n?", "", txt.strip())
        txt = re.sub(r"\n?```$", "", txt.strip())
        return txt.strip()[:1800]
    except Exception as exc:  # noqa: BLE001
        log.warning("IA de orientação indisponível: %s", exc)
        return None


def _select_payloads(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filtra: estadual; regionais ≥ min; top municipais; Cuiabá se ≥ min."""
    min_lv = _norm_level(env("ALERT_MIN_LEVEL", "laranja"))
    min_rank = STAGE_ORDER.get(min_lv, 2)
    max_mun = int(env("ALERT_MAX_MUNICIPIOS", "12") or 12)
    max_reg = int(env("ALERT_MAX_REGIONAIS", "20") or 20)

    out: list[dict[str, Any]] = []
    estaduais = [p for p in payloads if p.get("escopo") == "estadual"]
    out.extend(estaduais)

    regionais = [
        p for p in payloads
        if p.get("escopo") == "regional" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
    ]
    regionais = sorted(regionais, key=lambda p: STAGE_ORDER.get(_norm_level(p.get("nivel")), -1), reverse=True)[:max_reg]
    out.extend(regionais)

    municipais = [
        p for p in payloads
        if p.get("escopo") == "municipal" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
    ]
    # prioriza por ícone/nível já no payload; mantém ordem de construção (pior primeiro se build ordenou)
    def _mun_key(p: dict) -> tuple:
        rank = STAGE_ORDER.get(_norm_level(p.get("nivel")), -1)
        score = 0.0
        for ind in p.get("indicadores") or []:
            if ind.get("campo") in {"score", "score_alerta_integrado", "indice_vigilancia_integrada"}:
                try:
                    score = float(str(ind.get("valor")).replace(",", "."))
                except Exception:
                    pass
                break
        return (rank, score)

    municipais = sorted(municipais, key=_mun_key, reverse=True)[:max_mun]
    out.extend(municipais)

    cui = [
        p for p in payloads
        if p.get("escopo") == "cuiaba" and STAGE_ORDER.get(_norm_level(p.get("nivel")), -1) >= min_rank
    ]
    # evita duplicar Cuiabá se já veio como municipal
    if cui:
        already = {str(p.get("alvo_id")) for p in out if p.get("escopo") == "municipal"}
        for p in cui:
            if str(p.get("alvo_id")) not in already:
                out.append(p)

    return out


def _enrich_payloads_with_ai(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """IA: 1× estadual (+ Cuiabá) e até ALERT_AI_MAX_PACKS regionais/municipais."""
    max_extra = int(env("ALERT_AI_MAX_PACKS", "3") or 3)
    used_extra = 0
    for p in payloads:
        escopo = p.get("escopo")
        if escopo == "estadual":
            p["orientacao_ia"] = _ai_orientacao(p)
            continue
        if escopo == "cuiaba":
            p["orientacao_ia"] = _ai_orientacao(p)
            continue
        if escopo in {"regional", "municipal"} and used_extra < max_extra:
            p["orientacao_ia"] = _ai_orientacao(p)
            used_extra += 1  # conta tentativa (sucesso ou falha) para não varrer todos
    return payloads


def format_payload_telegram(p: dict[str, Any], *, compact: bool = False) -> str:
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
    min_lv = env("ALERT_MIN_LEVEL", "laranja") or "laranja"
    payloads = build_alertas_multinivel(resumo, alerta if not alerta.empty else None, pred if not pred.empty else None, min_level=min_lv)
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
        "fingerprint": fingerprint,
        "com_ia": sum(1 for p in selected if p.get("orientacao_ia")),
    }
    return selected, fingerprint, meta


def _send_telegram_batches(payloads: list[dict[str, Any]]) -> bool:
    ok_any = False
    # 1) Estadual completo
    for p in payloads:
        if p.get("escopo") == "estadual":
            if send_telegram(format_payload_telegram(p, compact=False)):
                ok_any = True
            break

    # 2) Regionais — em lotes
    regs = [p for p in payloads if p.get("escopo") == "regional"]
    if regs:
        header = f"{ICON['regional']} ALERTAS REGIONAIS ({len(regs)})\n" + ("─" * 28)
        chunks: list[str] = [header]
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

    # 3) Municipais — em lotes compactos
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
    subject = (
        f"[SIS Clima-Saúde] {EMOJI.get(niv, '⚪')} Boletim multinível CIEVS — "
        f"{niv.upper()} · {meta.get('n_regionais', 0)} regionais · {meta.get('n_municipais', 0)} municípios"
    )
    body_html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:860px;margin:0 auto;background:#f8fafc;padding:18px">
      <h1 style="margin:0 0 6px">{ICON['titulo']} SIS Clima-Saúde MT</h1>
      <p style="margin:0 0 16px;color:#334155">Boletim operacional multinível · gerado em {html.escape(now_iso())}</p>
      <p>🏛️ Estadual · 🗺️ Regionais: <b>{meta.get('n_regionais', 0)}</b>
         · 📍 Municipais: <b>{meta.get('n_municipais', 0)}</b>
         · 🤖 Pacotes com IA: <b>{meta.get('com_ia', 0)}</b></p>
      {''.join(format_payload_html(p) for p in payloads)}
      <p style="color:#64748b;font-size:13px">{ICON['rodape']} Validar no painel antes de comunicação oficial.
      Lista de contatos provisória — aguardando atualização CIEVS.</p>
    </div>
    """
    # texto plano de fallback
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
                f"payloads={len(payloads)}; regionais={meta.get('n_regionais')}; municipais={meta.get('n_municipais')}; ia={meta.get('com_ia')}",
                json.dumps({"tipo": "multinivel", **results}, ensure_ascii=False),
                status,
            ),
        )
    log.info("Digest multinível %s · %s", status, results)
    return {"status": status, "canais": results, **meta}


# Compat: build_digest_message ainda usado em testes antigos
def build_digest_message(resumo: pd.DataFrame | None = None) -> tuple[str, str, str, dict]:
    payloads, fingerprint, meta = build_multilevel_pack(resumo)
    subject = f"[SIS Clima-Saúde] {EMOJI.get(meta['nivel'],'⚪')} Multinível {meta['nivel'].upper()}"
    message = "\n\n".join(format_payload_telegram(p, compact=True) for p in payloads[:5])
    return subject, message, fingerprint, meta
