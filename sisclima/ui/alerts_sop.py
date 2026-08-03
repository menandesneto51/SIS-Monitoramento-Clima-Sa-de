# -*- coding: utf-8 -*-
"""SOP e helpers de alertas para o painel CIEVS."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.alerts.change_detector import (
    alerts_enabled,
    build_level_change_message,
    register_human_validation,
)
from sisclima.alerts.notifier import _email_enabled, _telegram_enabled, _webhook_enabled
from sisclima.core.config import env
from sisclima.core.db import init_db, read_table, table_exists

ALERT_SOP_STEPS = [
    {
        "passo": "1. Confirmar mudança",
        "texto": "Compare o nível estadual persistido (`nivel_atual`) com o nível da rodada (município sentinela / resumo).",
    },
    {
        "passo": "2. Validar na sala de situação",
        "texto": "Abra Visão executiva: mapa + ranking. Confira motivo, vigilância integrada e tendência 7d dos críticos.",
    },
    {
        "passo": "3. Checar canais",
        "texto": "E-mail (SMTP), Telegram e/ou Webhook devem estar configurados no `.env` antes de ligar o envio.",
    },
    {
        "passo": "4. Armar o envio",
        "texto": "Defina `SEND_ALERT_ON_LEVEL_CHANGE=true` somente após validar a mensagem e os destinatários.",
    },
    {
        "passo": "5. Auditoria",
        "texto": "Todo disparo (ou bloqueio) fica em `alertas_enviados` com status `enviado`, `bloqueado_por_config` ou `registrado_sem_canal`. Validação humana em `alertas_validacao_humana`.",
    },
    {
        "passo": "6. Desarmar se necessário",
        "texto": "Volte `SEND_ALERT_ON_LEVEL_CHANGE=false` após o plantão ou em ambiente de teste para evitar spam.",
    },
]

ALERT_CHECKLIST = [
    "Há mudança real de nível (não só reprocessamento idêntico)?",
    "Motivos da sentinela fazem sentido clínico/operacional?",
    "Destinatários CIEVS/regionais estão corretos?",
    "IndicaSUS/ocupação: se offline, a mensagem deixa claro o uso de proxy?",
    "Cemaden/ar/SRAG críticos mencionados quando relevantes?",
]


def alert_channel_status() -> dict[str, Any]:
    return {
        "envio_ligado": alerts_enabled(),
        "email": _email_enabled(),
        "telegram": _telegram_enabled(),
        "webhook": _webhook_enabled(),
        "email_to": env("ALERT_EMAIL_TO") or "—",
        "flag": env("SEND_ALERT_ON_LEVEL_CHANGE", "false"),
    }


def municipal_alert_candidates(resumo: pd.DataFrame) -> pd.DataFrame:
    """Municípios que merecem atenção de plantão (não disparam e-mail automaticamente)."""
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    df = resumo.copy()
    nivel = df.get("nivel", pd.Series(dtype=str)).astype(str).str.lower()
    tend = df.get("tendencia_7d", pd.Series(dtype=str)).astype(str).str.lower()
    vig = pd.to_numeric(df.get("indice_vigilancia_integrada"), errors="coerce")

    mask = nivel.isin(["laranja", "vermelha", "roxa"]) | tend.eq("subindo") | (vig >= 60)
    out = df.loc[mask].copy()
    if out.empty:
        return out

    def _prio(row):
        n = str(row.get("nivel", "")).lower()
        score = {"roxa": 40, "vermelha": 30, "laranja": 20, "amarela": 10}.get(n, 0)
        if str(row.get("tendencia_7d", "")).lower() == "subindo":
            score += 8
        v = row.get("indice_vigilancia_integrada")
        try:
            score += float(v) / 10.0
        except Exception:
            pass
        return score

    out["prioridade_alerta"] = out.apply(_prio, axis=1)
    cols = [
        c
        for c in [
            "cod_ibge",
            "municipio",
            "regional_saude",
            "nivel",
            "score",
            "indice_vigilancia_integrada",
            "indice_vigilancia_bruta",
            "tendencia_7d",
            "orientacao_leiga",
            "motivo",
            "prioridade_alerta",
        ]
        if c in out.columns
    ]
    return out.sort_values("prioridade_alerta", ascending=False)[cols]


def preview_state_alert(data_ref: str, nivel_novo: str, motivos: list[str]) -> dict[str, str]:
    old = None
    try:
        from sisclima.alerts.change_detector import get_previous_level

        old = get_previous_level()
    except Exception:
        old = None
    subj, msg = build_level_change_message(data_ref, old, nivel_novo, motivos)
    status = alert_channel_status()
    if not status["envio_ligado"]:
        acao = "NÃO enviaria agora (SEND_ALERT_ON_LEVEL_CHANGE=false) — só registraria bloqueio."
    elif not (status["email"] or status["telegram"] or status["webhook"]):
        acao = "Flag ligada, mas nenhum canal ativo — ficaria registrado_sem_canal."
    else:
        canais = [k for k in ("email", "telegram", "webhook") if status[k]]
        acao = f"Enviaria pelos canais: {', '.join(canais)}."
    return {
        "nivel_anterior": old or "—",
        "nivel_novo": nivel_novo,
        "subject": subj,
        "message": msg,
        "acao": acao,
    }


def recent_alert_log(limit: int = 20) -> pd.DataFrame:
    try:
        hist = read_table("alertas_enviados")
    except Exception:
        return pd.DataFrame()
    if hist.empty:
        return hist
    if "created_at" in hist.columns:
        hist = hist.sort_values("created_at", ascending=False)
    return hist.head(limit)


def recent_nivel_historico(limit: int = 40) -> pd.DataFrame:
    """Leituras de nível estadual por rodada (`nivel_historico`)."""
    try:
        init_db()
    except Exception:
        pass
    if not table_exists("nivel_historico"):
        return pd.DataFrame()
    try:
        hist = read_table("nivel_historico")
    except Exception:
        return pd.DataFrame()
    if hist.empty:
        return hist
    if "created_at" in hist.columns:
        hist = hist.sort_values("created_at", ascending=False)
    return hist.head(limit)


def recent_validacoes_humanas(limit: int = 20) -> pd.DataFrame:
    try:
        init_db()
    except Exception:
        pass
    if not table_exists("alertas_validacao_humana"):
        return pd.DataFrame()
    try:
        hist = read_table("alertas_validacao_humana")
    except Exception:
        return pd.DataFrame()
    if hist.empty:
        return hist
    if "created_at" in hist.columns:
        hist = hist.sort_values("created_at", ascending=False)
    return hist.head(limit)


def persist_checklist_validation(
    *,
    data_referencia: str,
    nivel: str,
    usuario: str,
    decisao: str,
    checklist_items: dict[str, bool],
    observacao: str = "",
) -> None:
    register_human_validation(
        data_referencia=data_referencia,
        nivel=nivel,
        usuario=usuario,
        decisao=decisao,
        checklist=checklist_items,
        observacao=observacao,
    )


def preview_boletim_executivo_ses(
    resumo: pd.DataFrame | None = None,
    *,
    alerta_integrado: pd.DataFrame | None = None,
    predicao_7d: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Gera prévia do boletim estadual SES legível (não envia)."""
    from sisclima.alerts.digest import format_ses_telegram
    from sisclima.engines.alertas_multinivel import build_alertas_multinivel

    payloads = build_alertas_multinivel(
        resumo if resumo is not None else pd.DataFrame(),
        alerta_integrado=alerta_integrado,
        predicao_7d=predicao_7d,
        min_level="amarela",
    )
    ses = next((p for p in payloads if p.get("escopo") == "estadual"), None)
    if not ses:
        return {
            "ok": False,
            "titulo": "Sem boletim estadual",
            "texto": "Não foi possível montar o pacote estadual com o resumo atual.",
            "payload": None,
        }
    texto = format_ses_telegram(ses)
    return {
        "ok": True,
        "titulo": str(ses.get("titulo") or "Boletim SES"),
        "texto": texto,
        "nivel": ses.get("nivel"),
        "n_municipios": ses.get("n_municipios"),
        "payload": ses,
    }


# Critérios técnicos de escalonamento (sinal SIS → avaliação humana).
# Não decretam COE/emergência; documentam quando elevar à sala de situação.
CRITERIOS_ESCALONAMENTO = [
    {
        "gatilho": "Nível estadual laranja+",
        "acao": "Abrir sala de situação CIEVS; validar motivos e frescor das fontes",
        "prazo": "≤2h",
        "decisao_humana": "Comunicar regionais prioritárias / manter monitoramento reforçado",
    },
    {
        "gatilho": "Nível vermelha ou roxa, ou flag_persistencia_roxa",
        "acao": "Elevar à autoridade competente com critérios técnicos documentados",
        "prazo": "Mesmo plantão",
        "decisao_humana": "Avaliar ativação formal (COE/portaria) — fora do SIS",
    },
    {
        "gatilho": "Ocupação ≥85% ou pressão assistencial alta nos prioritários",
        "acao": "Acionar regulação/hospitais; checar CNES e IndicaSUS",
        "prazo": "Mesmo dia",
        "decisao_humana": "Redistribuição de leitos / reforço APS",
    },
    {
        "gatilho": "PM2,5 elevado + SRAG em alta",
        "acao": "Cruzar ar × respiratório; orientar redução de exposição",
        "prazo": "24h",
        "decisao_humana": "Nota técnica conjunta vigilância ambiental/epidemiológica",
    },
    {
        "gatilho": "Alerta oficial Cemaden/INMET/ANA em município prioritário",
        "acao": "Sobrepor sinal oficial ao nível SIS; contatar Defesa Civil / regional",
        "prazo": "Imediato",
        "decisao_humana": "Ações territoriais conforme protocolo setorial",
    },
]


def routing_status_summary() -> dict[str, Any]:
    """Status do canal central + fan-out territorial (sem enviar)."""
    from sisclima.alerts.contacts import summarize_contacts

    status = alert_channel_status()
    contacts = summarize_contacts()
    return {
        **status,
        "contacts_path": contacts.get("path"),
        "contacts_disponivel": bool(contacts.get("disponivel")),
        "contacts_n": int(contacts.get("n") or 0),
        "contacts_por_tipo": contacts.get("por_tipo") or {},
        "fanout_enabled": bool(contacts.get("fanout_enabled")),
        "exemplo_csv": "config/contatos_alertas.exemplo.csv",
    }
