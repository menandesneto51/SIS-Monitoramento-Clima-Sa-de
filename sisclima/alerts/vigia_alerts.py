"""Alertas VIGIA completos — Estado, Regionais e Cuiabá.

Os três tipos previstos pelo painel VIGIA:
1) ESTADO — consolidado estadual
2) REGIONAIS — regionais de saúde com municípios em alerta
3) CUIABÁ — alerta municipal focado na capital
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from sisclima.alerts.notifier import dispatch_alert
from sisclima.core.config import env, as_bool
from sisclima.core.db import sqlite_conn
from sisclima.core.logging_utils import get_logger
from sisclima.engines.recommendations import recommendations_for_stage
from sisclima.public.exporter import _build_status_alertas
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

ALERT_TYPES = (
    ("estado", "TIPO 1/3 — ESTADO"),
    ("regionais", "TIPO 2/3 — REGIONAIS"),
    ("cuiaba", "TIPO 3/3 — CUIABÁ"),
)


def _nivel_label(nivel: str | None) -> str:
    return str(nivel or "indisponível").strip().upper()


def _fmt_num(value: Any, digits: int = 1, suffix: str = "") -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "indisponível"
        if isinstance(value, (int,)) or (isinstance(value, float) and float(value).is_integer()):
            return f"{int(value)}{suffix}"
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        text = str(value).strip()
        return text if text and text.lower() not in {"nan", "none"} else "indisponível"


def _format_recs(nivel: str) -> list[str]:
    lines = []
    for eixo, rec in recommendations_for_stage(str(nivel or "verde").lower()):
        lines.append(f"- [{eixo}] {rec}")
    return lines or ["- Manter monitoramento e validar fontes do ciclo."]


def _epidemiology_block(indicadores: dict[str, Any] | None, resumo_mun: pd.DataFrame, ctx: dict[str, Any]) -> str:
    ind = indicadores or {}
    monitorados = ind.get("municipios_monitorados")
    if monitorados is None and not resumo_mun.empty and "municipio" in resumo_mun.columns:
        monitorados = resumo_mun["municipio"].nunique()
    laranja = ind.get("municipios_laranja_ou_mais", ctx.get("municipios_alerta"))

    top_lines: list[str] = []
    if not resumo_mun.empty and "score" in resumo_mun.columns:
        top = resumo_mun.sort_values("score", ascending=False).head(8)
        for _, row in top.iterrows():
            top_lines.append(
                f"- {row.get('municipio')}: nível {row.get('nivel')} | score {_fmt_num(row.get('score'), 0)} | "
                f"UTCI {_fmt_num(row.get('utci_proxy'))} | Tmax {_fmt_num(row.get('tmax'))}°C | "
                f"ocupação {_fmt_num(row.get('ocupacao_leitos_pct'))}%"
            )
    if not top_lines:
        top_lines = ["- Ranking municipal indisponível neste ciclo."]

    lines = [
        "INDICADORES CLIMA-SAÚDE / EPIDEMIOLÓGICOS",
        f"- Município sentinela: {ind.get('municipio', 'n/d')}",
        f"- Nível/score sentinela: {_nivel_label(ind.get('nivel'))} / {_fmt_num(ind.get('score'), 0)}",
        f"- Data referência: {ind.get('data_referencia', ind.get('data', 'n/d'))}",
        f"- UTCI/proxy: {_fmt_num(ind.get('utci_proxy'))} | Heat index: {_fmt_num(ind.get('heat_index'))}",
        f"- Tmax: {_fmt_num(ind.get('tmax'))}°C | Tmin: {_fmt_num(ind.get('tmin'))}°C | Umidade: {_fmt_num(ind.get('umidade_media'))}%",
        f"- Risco calor diário: {_fmt_num(ind.get('risco_calor_diario'))} | Risco cumulativo 3d: {_fmt_num(ind.get('risco_cumulativo_3d'))}",
        f"- Onda de calor P95 (2d): {_fmt_num(ind.get('onda_calor_p95_2d'), 0)} | Duração: {_fmt_num(ind.get('duracao_onda_calor_dias'), 0)} dia(s)",
        f"- Casos SRAG: {_fmt_num(ind.get('casos_srag'), 0)} | Positividade LACEN: {_fmt_num(ind.get('positividade_lacen_pct'))}%",
        f"- Óbitos totais (SIM): {_fmt_num(ind.get('obitos_total'), 0)} | Suspeitos calor: {_fmt_num(ind.get('obitos_calor_suspeitos'), 0)}",
        f"- Score sentinela: {_fmt_num(ind.get('score_sentinela'), 0)} | IQ ar: {_fmt_num(ind.get('iq_ar_score'))}",
        f"- Ocupação leitos: {_fmt_num(ind.get('ocupacao_leitos_pct'))}% | Leitos totais: {_fmt_num(ind.get('leitos_total'), 0)} | Livres: {_fmt_num(ind.get('leitos_livres'), 0)}",
        f"- Fonte ocupação: {ind.get('fonte_ocupacao', 'n/d')}",
        f"- Índice resiliência: {_fmt_num(ind.get('indice_resiliencia'))}",
        f"- Municípios monitorados: {_fmt_num(monitorados, 0)} | Em alerta (laranja+): {_fmt_num(laranja, 0)}",
        "",
        "MUNICÍPIOS PRIORITÁRIOS (top score)",
        *top_lines,
    ]
    return "\n".join(lines)


def _ai_orientacoes(nivel: str, motivos: list[str], contexto: dict[str, Any], indicadores: dict[str, Any] | None) -> tuple[list[str], str]:
    """Retorna (bullets, fonte). Fonte: gemini | llm | deterministico."""
    base = [
        f"- Priorizar resposta compatível com nível {_nivel_label(nivel)} nas regionais com maior concentração de municípios em alerta.",
        "- Ativar comunicação de risco para população vulnerável (idosos, gestantes, crianças, pessoas em situação de rua).",
        "- Validar ocupação de leitos, insumos de hidratação/SRO e pontos de resfriamento nas portas de urgência.",
        "- Intensificar busca ativa e monitoramento de SRAG/óbitos suspeitos associados ao calor nas regionais críticas.",
        "- Emitir boletim operacional diário enquanto o nível permanecer laranja ou superior.",
    ]

    use_ai = as_bool(env("USE_AI_ALERT_TEXT", "true"), True)
    if not use_ai:
        return base, "deterministico_desligado"

    prompt = (
        "Você é assessoria técnica do CIEVS/SES-MT para ondas de calor. "
        "Em no máximo 6 bullets curtos, dê orientações operacionais práticas "
        "sem inventar números ausentes. Cite ações de vigilância, assistência, "
        "comunicação e epidemiologia. Use apenas o JSON a seguir.\n\n"
        + json.dumps(
            {
                "nivel": nivel,
                "motivos": motivos[:8],
                "municipios_alerta": contexto.get("municipios_alerta"),
                "nivel_estadual": contexto.get("nivel_estadual"),
                "regionais": contexto.get("regionais_resumo"),
                "cuiaba": contexto.get("cuiaba_resumo"),
                "indicadores": {
                    k: indicadores.get(k)
                    for k in [
                        "municipio",
                        "utci_proxy",
                        "tmax",
                        "risco_cumulativo_3d",
                        "casos_srag",
                        "positividade_lacen_pct",
                        "obitos_calor_suspeitos",
                        "ocupacao_leitos_pct",
                        "municipios_laranja_ou_mais",
                        "municipios_monitorados",
                    ]
                    if indicadores
                },
            },
            ensure_ascii=False,
            default=str,
        )
    )

    gemini_key = env("GEMINI_API_KEY")
    if gemini_key and not str(gemini_key).upper().startswith(("COLE_AQUI", "AI***")):
        models = [
            env("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-latest",
        ]
        seen: set[str] = set()
        for model in models:
            if model in seen:
                continue
            seen.add(model)
            try:
                import requests

                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                r = requests.post(
                    url,
                    params={"key": gemini_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=60,
                )
                if r.status_code >= 400:
                    log.warning("Gemini modelo=%s status=%s body=%s", model, r.status_code, r.text[:240])
                    continue
                data = r.json()
                text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text")
                )
                if text:
                    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
                    bullets = []
                    for ln in lines:
                        if not ln.startswith("-"):
                            ln = f"- {ln.lstrip('•* ').strip()}"
                        bullets.append(ln)
                    if bullets:
                        log.info("Orientações IA geradas via Gemini (%s)", model)
                        return bullets[:7], f"gemini:{model}"
            except Exception as exc:
                log.warning("Falha Gemini (%s): %s", model, exc)

    api_url = env("LLM_API_URL")
    api_key = env("LLM_API_KEY")
    if api_url and api_key and not str(api_key).upper().startswith("COLE_AQUI"):
        try:
            import requests

            payload = {
                "model": env("LLM_MODEL", "") or "",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            r = requests.post(api_url, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("text")
            if text:
                lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
                bullets = [ln if ln.startswith("-") else f"- {ln}" for ln in lines][:7]
                log.info("Orientações IA geradas via LLM genérico")
                return bullets, "llm_generico"
        except Exception as exc:
            log.warning("Falha LLM genérico no alerta: %s", exc)

    log.info("Usando orientações determinísticas (Gemini/LLM indisponível ou bloqueado por rede/SSL)")
    return base, "deterministico"


def _clip(text: str, limit: int = 3800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 40].rstrip() + "\n\n[...texto truncado para limite do canal]"


def _build_contexto(resumo_mun: pd.DataFrame, nivel: str, motivos: list[str]) -> dict[str, Any]:
    status, estado, regionais, cuiaba = _build_status_alertas(resumo_mun)
    nivel_estadual = nivel
    municipios_alerta = 0
    if not estado.empty:
        nivel_estadual = str(estado.iloc[0].get("nivel_estadual") or nivel)
        municipios_alerta = int(estado.iloc[0].get("municipios_em_alerta") or 0)

    regionais_resumo = []
    if not regionais.empty:
        for _, row in regionais.sort_values("municipios_em_alerta", ascending=False).head(12).iterrows():
            regionais_resumo.append(
                f"{row.get('regional_saude')}: {int(row.get('municipios_em_alerta') or 0)} município(s)"
            )

    cuiaba_resumo = "Cuiabá sem município em alerta neste ciclo."
    if not cuiaba.empty:
        row = cuiaba.iloc[0]
        cuiaba_resumo = (
            f"Cuiabá em alerta — nível {row.get('nivel', 'n/d')} | "
            f"score {row.get('score', 'n/d')} | "
            f"motivo: {str(row.get('motivo', ''))[:180]}"
        )

    return {
        "status": status,
        "estado": estado,
        "regionais": regionais,
        "cuiaba": cuiaba,
        "nivel_estadual": nivel_estadual,
        "municipios_alerta": municipios_alerta,
        "regionais_resumo": regionais_resumo,
        "cuiaba_resumo": cuiaba_resumo,
        "motivos": motivos,
        "recs": _format_recs(nivel_estadual),
    }


def compose_vigia_messages(
    data_referencia: str,
    nivel: str,
    motivos: list[str],
    resumo_mun: pd.DataFrame,
    old_nivel: str | None = None,
    force: bool = False,
    indicadores: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Monta os 3 alertas VIGIA completos."""
    ctx = _build_contexto(resumo_mun, nivel, motivos)
    ai_lines, ai_fonte = _ai_orientacoes(ctx["nivel_estadual"], motivos, ctx, indicadores)
    epi_txt = _epidemiology_block(indicadores, resumo_mun, ctx)
    motivos_txt = "\n".join(f"- {m}" for m in (motivos or [])[:10]) or "- Sem motivos registrados"
    recs_txt = "\n".join(ctx["recs"])
    ai_txt = "\n".join(ai_lines)
    mudanca = (
        f"Nível anterior: {old_nivel or 'sem registro'} → atual: {_nivel_label(ctx['nivel_estadual'])}"
        if old_nivel != ctx["nivel_estadual"]
        else f"Nível atual: {_nivel_label(ctx['nivel_estadual'])}"
        + (" (envio forçado)" if force else "")
    )

    messages: list[dict[str, str]] = []

    body_estado = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[0][1]}\n"
        f"Identificação: alerta estadual consolidado\n"
        f"Data de referência: {data_referencia}\n"
        f"{mudanca}\n"
        f"Municípios em alerta (laranja+): {ctx['municipios_alerta']}\n\n"
        f"{epi_txt}\n\n"
        f"GATILHOS / MOTIVOS\n{motivos_txt}\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA (fonte: {ai_fonte})\n{ai_txt}\n\n"
        f"Encaminhamento: acionar Sala de Situação/COE conforme o nível e monitorar regionais prioritárias."
    )
    messages.append({
        "tipo": "estado",
        "titulo_tipo": ALERT_TYPES[0][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[0][1]} — {data_referencia}",
        "message": _clip(body_estado),
        "ai_fonte": ai_fonte,
    })

    reg_lines = ctx["regionais_resumo"] or ["Nenhuma regional com município em alerta (score ≥ 2)."]
    body_reg = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[1][1]}\n"
        f"Identificação: alerta por regionais de saúde\n"
        f"Data de referência: {data_referencia}\n"
        f"Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
        f"REGIONAIS COM MUNICÍPIOS EM ALERTA\n"
        + "\n".join(f"- {x}" for x in reg_lines)
        + "\n\n"
        f"{epi_txt}\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA (fonte: {ai_fonte})\n{ai_txt}\n\n"
        f"Encaminhamento: cada regional priorize busca ativa, pontos de resfriamento e comunicação local."
    )
    messages.append({
        "tipo": "regionais",
        "titulo_tipo": ALERT_TYPES[1][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[1][1]} — {data_referencia}",
        "message": _clip(body_reg),
        "ai_fonte": ai_fonte,
    })

    body_cuiaba = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[2][1]}\n"
        f"Identificação: alerta municipal focado em Cuiabá\n"
        f"Data de referência: {data_referencia}\n"
        f"Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
        f"SITUAÇÃO DE CUIABÁ\n- {ctx['cuiaba_resumo']}\n\n"
        f"{epi_txt}\n\n"
        f"GATILHOS / MOTIVOS (ciclo estadual sentinela)\n{motivos_txt}\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA (fonte: {ai_fonte})\n{ai_txt}\n\n"
        f"Encaminhamento: reforçar APS/UPA, comunicação urbana e monitoramento de ocupação hospitalar na capital."
    )
    messages.append({
        "tipo": "cuiaba",
        "titulo_tipo": ALERT_TYPES[2][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[2][1]} — {data_referencia}",
        "message": _clip(body_cuiaba),
        "ai_fonte": ai_fonte,
    })

    return messages


def dispatch_vigia_alerts(
    data_referencia: str,
    old: str | None,
    new: str,
    motivos: list[str],
    indicadores: dict,
    resumo_mun: pd.DataFrame | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Envia os 3 alertas VIGIA e registra auditoria."""
    df = resumo_mun if resumo_mun is not None else pd.DataFrame()
    messages = compose_vigia_messages(
        data_referencia=str(data_referencia),
        nivel=str(new),
        motivos=list(motivos or []),
        resumo_mun=df,
        old_nivel=old,
        force=force,
        indicadores=indicadores,
    )

    channel_any = {"email": False, "telegram": False, "webhook": False}
    per_type: dict[str, Any] = {}

    log.info(
        "Preparando pacote VIGIA com %s alertas | ai_fonte=%s | resumo_mun_linhas=%s",
        len(messages),
        messages[0].get("ai_fonte") if messages else "n/d",
        len(df),
    )

    for item in messages:
        results = dispatch_alert(
            item["subject"],
            item["message"],
            {
                "data_referencia": data_referencia,
                "nivel_anterior": old,
                "nivel_novo": new,
                "tipo_alerta_vigia": item["tipo"],
                "titulo_tipo": item["titulo_tipo"],
                "indicadores": indicadores,
                "force": force,
                "ai_fonte": item.get("ai_fonte"),
            },
        )
        per_type[item["tipo"]] = results
        for k in channel_any:
            channel_any[k] = channel_any[k] or bool(results.get(k))

        with sqlite_conn() as conn:
            conn.execute(
                """INSERT INTO alertas_enviados
                   (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    now_iso(),
                    old,
                    new,
                    item["subject"],
                    item["message"],
                    json.dumps({"tipo": item["tipo"], "ai_fonte": item.get("ai_fonte"), **results}, ensure_ascii=False),
                    "enviado" if any(results.values()) else "registrado_sem_canal",
                ),
            )

    log.info("Alertas VIGIA enviados: %s | canais=%s", list(per_type.keys()), channel_any)
    return {"tipos": per_type, "canais": channel_any, "qtd": len(messages), "ai_fonte": messages[0].get("ai_fonte") if messages else None}
