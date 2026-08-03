# -*- coding: utf-8 -*-
"""SOP e helpers de alertas para o painel CIEVS."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.alerts.change_detector import (
    alerts_enabled,
    build_level_change_message,
)
from sisclima.alerts.notifier import _email_enabled, _telegram_enabled, _webhook_enabled
from sisclima.core.config import as_bool, env
from sisclima.core.db import init_db, read_table, table_exists

# Contatos/fan-out: import defensivo (não derruba o painel se o módulo falhar no Cloud).
try:
    from sisclima.alerts.contacts import summarize_contacts as _summarize_contacts
except Exception:  # noqa: BLE001

    def _summarize_contacts() -> dict[str, Any]:
        return {
            "path": env("ALERT_CONTACTS_CSV", "data/input/contatos_alertas.csv")
            or "data/input/contatos_alertas.csv",
            "disponivel": False,
            "fanout_enabled": False,
            "n": 0,
            "por_tipo": {},
        }


def summarize_contacts() -> dict[str, Any]:
    return _summarize_contacts()


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
        "texto": "Todo disparo (ou bloqueio) fica em `alertas_enviados`. Validação humana em `alertas_validacao_humana`.",
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
    from sisclima.alerts.change_detector import register_human_validation

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
    texto = format_ses_telegram(enrich_payload_for_preview(ses))
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


def enrich_payload_for_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Aplica orientações do padrão SES legível (sem IA) para prévia no painel."""
    from sisclima.alerts.digest import (
        build_orientacoes_municipal,
        build_orientacoes_regional,
        build_orientacoes_ses_setores,
    )

    p = dict(payload or {})
    escopo = str(p.get("escopo") or "")
    if escopo == "estadual":
        p["orientacoes_setores"] = build_orientacoes_ses_setores(p)
    elif escopo == "regional":
        p["orientacoes_regionais"] = build_orientacoes_regional(p)
    elif escopo in {"municipal", "cuiaba"}:
        o = build_orientacoes_municipal(p)
        p["orientacoes_municipais"] = o
        p["orientacoes"] = {
            "gestor": o.get("gestor"),
            "profissional": o.get("profissional"),
            "populacao": o.get("populacao"),
        }
    return p


def format_boletim_painel(payload: dict[str, Any]) -> str:
    """Texto exatamente no padrão Telegram/e-mail (resumo → KPI → ações → prioritários)."""
    from sisclima.alerts.digest import format_payload_telegram

    return format_payload_telegram(enrich_payload_for_preview(payload), compact=False)


def boletim_destinatario_resumo(escopo: str, status: dict[str, Any] | None = None) -> str:
    status = status or alert_channel_status()
    esc = str(escopo or "").lower()
    if esc == "estadual":
        return (
            f"Canal central CIEVS → {status.get('email_to') or 'ALERT_EMAIL_TO'} "
            f"+ Telegram central (somente estadual)."
        )
    if esc == "regional":
        return "Fan-out regional (planilha de contatos) — não vai para notifica/Telegram central."
    if esc == "cuiaba":
        return "Fan-out Vigidesastre Cuiabá (planilha) — não vai para o canal central CIEVS."
    return "Fan-out municipal (planilha) — não vai para o canal central CIEVS."
