# -*- coding: utf-8 -*-
"""SOP e helpers de alertas para o painel CIEVS."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.alerts.change_detector import alerts_enabled, build_level_change_message
from sisclima.alerts.contacts import summarize_contacts
from sisclima.alerts.notifier import _email_enabled, _telegram_enabled, _webhook_enabled
from sisclima.core.config import as_bool, env
from sisclima.core.db import read_table

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
        "passo": "3. Checar canais centrais",
        "texto": "E-mail (`ALERT_EMAIL_TO`, ex. Menandes + notifica@ses.mt.gov.br) e Telegram (`TELEGRAM_CHAT_ID`) "
        "recebem somente o alerta estadual. Regionais/municipais/Cuiabá usam a planilha de contatos.",
    },
    {
        "passo": "4. Armar o envio estadual",
        "texto": "Defina `SEND_ALERT_ON_LEVEL_CHANGE=true` somente após validar a prévia estadual e os destinatários centrais.",
    },
    {
        "passo": "5. Fan-out territorial (quando houver planilha)",
        "texto": "Copie `config/contatos_alertas.exemplo.csv` → `data/input/contatos_alertas.csv`, preencha e ligue "
        "`ALERT_FANOUT_ENABLED=true`. Até lá, os boletins territoriais só são gerados/gravados.",
    },
    {
        "passo": "6. Auditoria",
        "texto": "Todo disparo (ou bloqueio) fica em `alertas_enviados` com status `enviado`, `bloqueado_por_config` ou `registrado_sem_canal`.",
    },
    {
        "passo": "7. Desarmar se necessário",
        "texto": "Volte `SEND_ALERT_ON_LEVEL_CHANGE=false` após o plantão ou em ambiente de teste para evitar spam.",
    },
]

ALERT_CHECKLIST = [
    "Há mudança real de nível estadual (não só reprocessamento idêntico)?",
    "Prévia SES legível (resumo → KPI → ações → prioritários) está correta?",
    "Destinatários centrais (você + notifica CIEVS / Telegram) estão corretos?",
    "Confirmado: canal central NÃO recebe regionais/municipais/Cuiabá?",
    "IndicaSUS/ocupação: se offline, a mensagem deixa claro o uso de estimado estadual?",
    "Planilha de contatos pronta se for liberar fan-out territorial?",
]


def alert_channel_status() -> dict[str, Any]:
    contacts = summarize_contacts()
    return {
        "envio_ligado": alerts_enabled(),
        "email": _email_enabled(),
        "telegram": _telegram_enabled(),
        "webhook": _webhook_enabled(),
        "email_to": env("ALERT_EMAIL_TO") or "—",
        "flag": env("SEND_ALERT_ON_LEVEL_CHANGE", "false"),
        "central_only_ses": as_bool(env("ALERT_CENTRAL_ONLY_SES", "true"), True),
        "fanout_enabled": bool(contacts.get("fanout_enabled")),
        "fanout_flag": as_bool(env("ALERT_FANOUT_ENABLED", "false"), False),
        "contacts_available": bool(contacts.get("disponivel")),
        "contacts_n": int(contacts.get("n") or 0),
        "contacts_path": str(contacts.get("path") or "data/input/contatos_alertas.csv"),
        "layers": env("ALERT_LAYERS", "ses,regionais,municipais,cuiaba") or "ses,regionais,municipais,cuiaba",
        "interval_h": env("ALERT_INTERVAL_HOURS", "24") or "24",
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
