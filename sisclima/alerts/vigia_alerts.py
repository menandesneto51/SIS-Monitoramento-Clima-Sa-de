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


def _format_recs(nivel: str) -> list[str]:
    lines = []
    for eixo, rec in recommendations_for_stage(str(nivel or "verde").lower()):
        lines.append(f"- [{eixo}] {rec}")
    return lines or ["- Manter monitoramento e validar fontes do ciclo."]


def _ai_orientacoes(nivel: str, motivos: list[str], contexto: dict[str, Any]) -> list[str]:
    """Gera orientações curtas via Gemini/LLM se configurado; senão, texto determinístico."""
    base = [
        f"- Priorizar resposta compatível com nível {_nivel_label(nivel)} nas regionais com maior concentração de municípios em alerta.",
        "- Ativar comunicação de risco para população vulnerável (idosos, gestantes, crianças, pessoas em situação de rua).",
        "- Validar ocupação de leitos, insumos de hidratação/SRO e pontos de resfriamento nas portas de urgência.",
    ]

    use_llm = as_bool(env("USE_LLM_REPORT", "false"), False) or as_bool(env("USE_AI_ALERT_TEXT", "true"), True)
    gemini_key = env("GEMINI_API_KEY")
    if not use_llm:
        return base

    prompt = (
        "Você é assessoria técnica do CIEVS/SES-MT para ondas de calor. "
        "Em no máximo 5 bullets curtos, dê orientações operacionais práticas "
        "sem inventar números. Use apenas o JSON a seguir.\n\n"
        + json.dumps(
            {
                "nivel": nivel,
                "motivos": motivos[:8],
                "municipios_alerta": contexto.get("municipios_alerta"),
                "nivel_estadual": contexto.get("nivel_estadual"),
                "regionais": contexto.get("regionais_resumo"),
                "cuiaba": contexto.get("cuiaba_resumo"),
            },
            ensure_ascii=False,
            default=str,
        )
    )

    # Gemini (chave já presente em vários .env locais)
    if gemini_key and not str(gemini_key).upper().startswith("COLE_AQUI"):
        try:
            import requests

            model = env("GEMINI_MODEL", "gemini-2.0-flash") or "gemini-2.0-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            r = requests.post(
                url,
                params={"key": gemini_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=45,
            )
            r.raise_for_status()
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
                    return bullets[:6]
        except Exception as exc:
            log.warning("Falha orientações Gemini no alerta; usando texto determinístico: %s", exc)

    # Endpoint genérico estilo OpenAI (se configurado)
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
            r = requests.post(api_url, headers=headers, json=payload, timeout=45)
            r.raise_for_status()
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content") or data.get("text")
            if text:
                lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
                return [ln if ln.startswith("-") else f"- {ln}" for ln in lines][:6]
        except Exception as exc:
            log.warning("Falha LLM genérico no alerta; usando texto determinístico: %s", exc)

    return base


def _clip(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n\n[...texto truncado]"


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
) -> list[dict[str, str]]:
    """Monta os 3 alertas VIGIA completos."""
    ctx = _build_contexto(resumo_mun, nivel, motivos)
    ai_lines = _ai_orientacoes(ctx["nivel_estadual"], motivos, ctx)
    motivos_txt = "\n".join(f"- {m}" for m in (motivos or [])[:8]) or "- Sem motivos registrados"
    recs_txt = "\n".join(ctx["recs"])
    ai_txt = "\n".join(ai_lines)
    mudanca = (
        f"Nível anterior: {old_nivel or 'sem registro'} → atual: {_nivel_label(ctx['nivel_estadual'])}"
        if old_nivel != ctx["nivel_estadual"]
        else f"Nível atual: {_nivel_label(ctx['nivel_estadual'])}"
        + (" (envio forçado)" if force else "")
    )

    messages: list[dict[str, str]] = []

    # 1) ESTADO
    body_estado = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[0][1]}\n"
        f"Identificação: alerta estadual consolidado\n"
        f"Data de referência: {data_referencia}\n"
        f"{mudanca}\n"
        f"Municípios em alerta (laranja+): {ctx['municipios_alerta']}\n\n"
        f"GATILHOS / MOTIVOS\n{motivos_txt}\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA\n{ai_txt}\n\n"
        f"Encaminhamento: acionar Sala de Situação/COE conforme o nível e monitorar regionais prioritárias."
    )
    messages.append({
        "tipo": "estado",
        "titulo_tipo": ALERT_TYPES[0][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[0][1]} — {data_referencia}",
        "message": _clip(body_estado),
    })

    # 2) REGIONAIS
    reg_lines = ctx["regionais_resumo"] or ["- Nenhuma regional com município em alerta (score ≥ 2)."]
    body_reg = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[1][1]}\n"
        f"Identificação: alerta por regionais de saúde\n"
        f"Data de referência: {data_referencia}\n"
        f"Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
        f"REGIONAIS COM MUNICÍPIOS EM ALERTA\n"
        + "\n".join(f"- {x}" for x in reg_lines)
        + "\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA\n{ai_txt}\n\n"
        f"Encaminhamento: cada regional priorize busca ativa, pontos de resfriamento e comunicação local."
    )
    messages.append({
        "tipo": "regionais",
        "titulo_tipo": ALERT_TYPES[1][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[1][1]} — {data_referencia}",
        "message": _clip(body_reg),
    })

    # 3) CUIABÁ
    body_cuiaba = (
        f"[VIGIA Clima-Saúde MT] ALERTA {ALERT_TYPES[2][1]}\n"
        f"Identificação: alerta municipal focado em Cuiabá\n"
        f"Data de referência: {data_referencia}\n"
        f"Nível estadual de referência: {_nivel_label(ctx['nivel_estadual'])}\n\n"
        f"SITUAÇÃO DE CUIABÁ\n- {ctx['cuiaba_resumo']}\n\n"
        f"GATILHOS / MOTIVOS (ciclo estadual sentinela)\n{motivos_txt}\n\n"
        f"ORIENTAÇÕES OPERACIONAIS (matriz por nível)\n{recs_txt}\n\n"
        f"ORIENTAÇÕES IA / ASSESSORIA TÉCNICA\n{ai_txt}\n\n"
        f"Encaminhamento: reforçar APS/UPA, comunicação urbana e monitoramento de ocupação hospitalar na capital."
    )
    messages.append({
        "tipo": "cuiaba",
        "titulo_tipo": ALERT_TYPES[2][1],
        "subject": f"[VIGIA][{_nivel_label(ctx['nivel_estadual'])}] {ALERT_TYPES[2][1]} — {data_referencia}",
        "message": _clip(body_cuiaba),
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
    )

    channel_any = {"email": False, "telegram": False, "webhook": False}
    per_type: dict[str, Any] = {}

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
                    json.dumps({"tipo": item["tipo"], **results}, ensure_ascii=False),
                    "enviado" if any(results.values()) else "registrado_sem_canal",
                ),
            )

    log.info("Alertas VIGIA enviados: %s | canais=%s", list(per_type.keys()), channel_any)
    return {"tipos": per_type, "canais": channel_any, "qtd": len(messages)}
