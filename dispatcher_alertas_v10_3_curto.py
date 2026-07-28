# -*- coding: utf-8 -*-
"""
SIS Clima-Saúde MT - Alertas V10.3 CURTO/CONSOLIDADO

Objetivo:
- Reduzir alertas longos e repetitivos.
- Enviar um boletim estadual compacto e boletins regionais compactos.
- Agrupar municípios por nível de alerta.
- Incluir orientações gerais para municípios, gestores e profissionais.
- Destacar orientações específicas apenas quando houver gatilhos objetivos.

Uso:
.venv\\Scripts\\python.exe dispatcher_alertas_v10_2_curto.py --dry-run --min-level laranja
.venv\\Scripts\\python.exe dispatcher_alertas_v10_2_curto.py --send --min-level laranja
.venv\\Scripts\\python.exe dispatcher_alertas_v10_2_curto.py --send --min-level vermelha

Saídas:
- data/output/alertas_v10_2_curto_preview.html
- data/output/alertas_v10_2_curto_preview.txt
- alertas_gerados_v10_2
- historico_envios_alertas_v10_2
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import smtplib
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


DB = Path("data/output/sis_integrado.db")
CONTACTS = Path("data/input/contatos_alertas.csv")
OUT_HTML = Path("data/output/alertas_v10_2_curto_preview.html")
OUT_TXT = Path("data/output/alertas_v10_2_curto_preview.txt")

LEVEL_RANK = {
    "cinza": -1, "baixo": 0, "verde": 0,
    "moderado": 1, "amarela": 1, "amarelo": 1,
    "alto": 2, "laranja": 2,
    "vermelha": 3, "vermelho": 3,
    "muito alto": 4, "roxa": 4, "roxo": 4,
}
RANK_LEVEL = {-1: "cinza", 0: "verde", 1: "amarela", 2: "laranja", 3: "vermelha", 4: "roxa"}
LEVEL_LABEL = {"verde": "Verde", "amarela": "Amarela", "laranja": "Laranja", "vermelha": "Vermelha", "roxa": "Roxa", "cinza": "Cinza"}
EMOJI = {"verde": "🟢", "amarela": "🟡", "laranja": "🟠", "vermelha": "🔴", "roxa": "🟣", "cinza": "⚪"}


def env_first(*names, default=None):
    for n in names:
        v = os.getenv(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return default


def env_bool(*names, default=False):
    v = env_first(*names)
    if v is None:
        return default
    return str(v).strip().lower() in ["1", "true", "yes", "sim", "s", "on"]


def split_recipients(value):
    if not value:
        return []
    return [p.strip() for p in re.split(r"[;,]", str(value)) if p and p.strip()]


def normalize_level(x):
    s = str(x or "").strip().lower()
    if s == "amarelo":
        s = "amarela"
    if s == "vermelho":
        s = "vermelha"
    if s == "roxo":
        s = "roxa"
    if s in ["muito_alto", "muito-alto"]:
        s = "muito alto"
    return RANK_LEVEL.get(LEVEL_RANK.get(s, -1), "cinza")


def level_rank(x):
    return LEVEL_RANK.get(str(x or "").strip().lower(), -1)


def max_level(*levels):
    return RANK_LEVEL.get(max([level_rank(x) for x in levels] or [-1]), "cinza")


def fmt(x, nd=1, suffix=""):
    try:
        if pd.isna(x):
            return "s/d"
        return f"{float(x):.{nd}f}{suffix}"
    except Exception:
        return "s/d"


def norm7(s):
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


def read_table(con, name):
    try:
        ok = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", con, params=(name,))
        if ok.empty:
            return pd.DataFrame()
        return pd.read_sql(f"SELECT * FROM {name}", con)
    except Exception:
        return pd.DataFrame()


def ensure_history(con):
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS historico_envios_alertas_v10_2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_envio TEXT,
            data_alerta TEXT,
            escopo TEXT,
            regional_saude TEXT,
            nivel_maximo TEXT,
            canal TEXT,
            destinatario TEXT,
            assunto TEXT,
            chave_alerta TEXT,
            status_envio TEXT,
            detalhe TEXT
        )
        """
    )
    con.commit()


def load_contacts():
    if CONTACTS.exists():
        try:
            c = pd.read_csv(CONTACTS, dtype=str).fillna("")
            for col in ["tipo_destinatario", "regional_saude", "cod_ibge", "municipio", "nome", "email", "telegram_chat_id", "ativo"]:
                if col not in c.columns:
                    c[col] = ""
            return c
        except Exception as exc:
            print(f"AVISO: falha lendo {CONTACTS}: {exc}")

    emails = split_recipients(env_first("ALERT_EMAIL_TO", "ALERT_EMAILS", "EMAIL_TO", "EMAIL_DESTINATARIO", "SMTP_TO", "DESTINATARIOS_EMAIL"))
    chats = split_recipients(env_first("ALERT_TELEGRAM_CHAT_IDS", "TELEGRAM_CHAT_IDS", "TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID", "DESTINATARIOS_TELEGRAM"))

    rows = []
    for e in emails:
        rows.append({"tipo_destinatario": "estadual", "regional_saude": "", "cod_ibge": "", "municipio": "", "nome": "estadual", "email": e, "telegram_chat_id": "", "ativo": "1"})
    for t in chats:
        rows.append({"tipo_destinatario": "estadual", "regional_saude": "", "cod_ibge": "", "municipio": "", "nome": "telegram", "email": "", "telegram_chat_id": t, "ativo": "1"})
    return pd.DataFrame(rows)


def active_contacts(contacts):
    if contacts.empty:
        return contacts
    c = contacts.copy().fillna("")
    if "ativo" in c.columns:
        c = c[c["ativo"].astype(str).str.lower().isin(["1", "true", "sim", "s", "yes", "ativo", ""])]
    return c


def recipients(contacts, scope="estadual", regional=None):
    c = active_contacts(contacts)
    if c.empty:
        return [], []

    if scope == "estadual":
        sel = c[c["tipo_destinatario"].astype(str).str.lower().eq("estadual")]
    elif scope == "regional":
        sel = c[
            (c["tipo_destinatario"].astype(str).str.lower().eq("estadual"))
            | (
                c["tipo_destinatario"].astype(str).str.lower().eq("regional")
                & c["regional_saude"].astype(str).eq(str(regional))
            )
        ]
    else:
        sel = c

    emails = sorted(set([x for x in sel.get("email", pd.Series(dtype=str)).astype(str).tolist() if "@" in x]))
    chats = sorted(set([x for x in sel.get("telegram_chat_id", pd.Series(dtype=str)).astype(str).tolist() if x.strip()]))
    return emails, chats


def build_dataset(con):
    resumo = read_table(con, "resumo_municipal_atual")
    if resumo.empty:
        raise RuntimeError("resumo_municipal_atual vazio ou ausente.")

    df = resumo.copy()
    df["cod_ibge"] = norm7(df["cod_ibge"])

    joins = [
        ("alerta_inteligente_municipal_v6", "alerta"),
        ("predicao_calor_7d_municipal_v6", "pred"),
        ("v9_priorizacao_epidemiologica", "v9"),
    ]
    for table, prefix in joins:
        t = read_table(con, table)
        if not t.empty and "cod_ibge" in t.columns:
            t = t.copy()
            t["cod_ibge"] = norm7(t["cod_ibge"])
            t = t.drop_duplicates("cod_ibge")
            ren = {}
            for col in t.columns:
                if col != "cod_ibge" and col in df.columns:
                    ren[col] = f"{prefix}_{col}"
            df = df.merge(t.rename(columns=ren), on="cod_ibge", how="left")

    if "alerta_inteligente_nivel" not in df.columns and "alerta_alerta_inteligente_nivel" in df.columns:
        df["alerta_inteligente_nivel"] = df["alerta_alerta_inteligente_nivel"]
    if "alerta_inteligente_score" not in df.columns and "alerta_alerta_inteligente_score" in df.columns:
        df["alerta_inteligente_score"] = df["alerta_alerta_inteligente_score"]
    if "nivel_predicao_7d" not in df.columns and "pred_nivel_predicao_7d" in df.columns:
        df["nivel_predicao_7d"] = df["pred_nivel_predicao_7d"]
    if "risco_preditivo_score" not in df.columns and "pred_risco_preditivo_score" in df.columns:
        df["risco_preditivo_score"] = df["pred_risco_preditivo_score"]
    if "nivel_priorizacao_v9" not in df.columns and "v9_nivel_priorizacao_v9" in df.columns:
        df["nivel_priorizacao_v9"] = df["v9_nivel_priorizacao_v9"]
    if "score_priorizacao_v9" not in df.columns and "v9_score_priorizacao_v9" in df.columns:
        df["score_priorizacao_v9"] = df["v9_score_priorizacao_v9"]

    for c in [
        "risco_cumulativo_3d", "utci_proxy", "tmax", "ocupacao_leitos_pct",
        "pressao_calor_pct", "pm25_ugm3", "alerta_inteligente_score",
        "risco_preditivo_score", "score_priorizacao_v9", "tmax_max_7d",
        "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d",
    ]:
        if c not in df.columns:
            df[c] = pd.NA
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "nivel" not in df.columns:
        df["nivel"] = "cinza"
    df["nivel"] = df["nivel"].apply(normalize_level)
    df["alerta_inteligente_nivel"] = df.get("alerta_inteligente_nivel", "cinza").apply(normalize_level)
    # HOTFIX V11.6: nivel_predicao_7d seguro
    if "nivel_predicao_7d" not in df.columns:
        df["nivel_predicao_7d"] = "cinza"
    else:
        df["nivel_predicao_7d"] = df["nivel_predicao_7d"].fillna("cinza")
    df["nivel_predicao_7d"] = df["nivel_predicao_7d"].apply(normalize_level)
    df["nivel_priorizacao_norm"] = df.get("nivel_priorizacao_v9", "baixo").apply(normalize_level)

    df["nivel_final"] = df.apply(lambda r: max_level(r["nivel"], r["alerta_inteligente_nivel"], r["nivel_predicao_7d"], r["nivel_priorizacao_norm"]), axis=1)
    df["rank_final"] = df["nivel_final"].apply(level_rank)

    return df


def group_municipios_by_level(df, min_rank=2):
    gdf = df[df["rank_final"] >= min_rank].copy()
    gdf = gdf.sort_values(["rank_final", "risco_cumulativo_3d", "risco_preditivo_score"], ascending=[False, False, False])
    lines = []
    for lvl in ["roxa", "vermelha", "laranja", "amarela"]:
        sub = gdf[gdf["nivel_final"] == lvl]
        if sub.empty:
            continue
        names = []
        for _, r in sub.iterrows():
            detalhe = f"{r['municipio']}"
            # Só mostra detalhes numéricos críticos no agrupamento.
            if lvl in ["roxa", "vermelha"]:
                detalhe += f" (risco3d {fmt(r.get('risco_cumulativo_3d'), 1)}; pred. {LEVEL_LABEL.get(r.get('nivel_predicao_7d'), r.get('nivel_predicao_7d'))})"
            names.append(detalhe)
        lines.append(f"{EMOJI[lvl]} {LEVEL_LABEL[lvl]} ({len(sub)}): " + "; ".join(names))
    return lines


def specific_highlights(df, min_rank=2):
    alerts = df[df["rank_final"] >= min_rank].copy()
    lines = []

    red = alerts[alerts["nivel_final"].isin(["vermelha", "roxa"])]
    if not red.empty:
        lines.append("Municípios em vermelho/roxo: ativar resposta municipal, comunicação diária com Regional/SES e pontos de hidratação/resfriamento.")

    pred_red = alerts[alerts["nivel_predicao_7d"].isin(["vermelha", "roxa"])]
    if not pred_red.empty:
        lines.append("Predição 7 dias em vermelho/roxo: antecipar escala, insumos e comunicação preventiva antes da piora esperada.")

    high_occ = alerts[pd.to_numeric(alerts["ocupacao_leitos_pct"], errors="coerce") >= 75]
    if not high_occ.empty:
        names = ", ".join(high_occ["municipio"].astype(str).head(8))
        lines.append(f"Ocupação ≥75%: {names}. Reforçar regulação, leitos de retaguarda e fluxo de transferência.")

    high_pm = alerts[pd.to_numeric(alerts["pm25_ugm3"], errors="coerce") >= 25]
    if not high_pm.empty:
        names = ", ".join(high_pm["municipio"].astype(str).head(8))
        lines.append(f"PM2.5 elevado: {names}. Reforçar orientação para pneumopatas, idosos, crianças e redução de exposição à fumaça.")

    v9_high = alerts[alerts.get("nivel_priorizacao_v9", "").astype(str).str.lower().isin(["alto", "muito alto"])]
    if not v9_high.empty:
        names = ", ".join(v9_high.sort_values("score_priorizacao_v9", ascending=False)["municipio"].astype(str).head(8))
        lines.append(f"Prioridade epidemiológica V9 alta: {names}. Priorizar vigilância ativa e revisão da rede assistencial.")

    return lines


def general_guidance(nivel_max):
    nivel_max = normalize_level(nivel_max)
    base_municipios = [
        "Divulgar orientação à população sobre hidratação, evitar sol nos horários críticos e reconhecer sinais de agravamento.",
        "Mapear grupos vulneráveis: idosos, crianças, gestantes, pessoas com doenças crônicas, trabalhadores expostos ao sol e população em situação de rua.",
        "Verificar disponibilidade de água potável e locais de acolhimento/resfriamento.",
    ]
    base_gestores = [
        "Manter ponto focal municipal/regional disponível e acompanhar painel diariamente.",
        "Checar escala, transporte sanitário, fluxos de regulação, leitos, insumos de hidratação e comunicação com a rede.",
        "Registrar ações adotadas e comunicar intercorrências relevantes à Regional/CIEVS.",
    ]
    base_prof = [
        "Intensificar triagem de grupos vulneráveis e suspeição de desidratação, exaustão pelo calor, síncope, IRA e descompensações cardiopulmonares.",
        "Orientar hidratação, proteção contra calor e atenção a medicamentos que aumentam risco de desidratação/descompensação.",
        "Comunicar aumento incomum de atendimentos, eventos graves e óbitos suspeitos relacionados ao calor.",
    ]

    if level_rank(nivel_max) >= 3:
        base_municipios += [
            "Ativar resposta municipal para calor extremo e ampliar pontos de hidratação/resfriamento.",
            "Avaliar suspensão/reprogramação de atividades ao ar livre nos períodos críticos e acionar Defesa Civil/assistência social quando necessário.",
        ]
        base_gestores += [
            "Garantir escala reforçada em APS/urgência e monitorar leitos bloqueados, higienização, transferências e pressão assistencial.",
            "Emitir alerta formal à rede municipal e intersetorial.",
        ]
        base_prof += [
            "Priorizar atendimento imediato de suspeita de insolação, hipertermia, desidratação grave, alteração de consciência ou sinais de choque.",
        ]
    elif level_rank(nivel_max) >= 2:
        base_municipios += [
            "Ativar rotina diária de acompanhamento e organizar pontos de hidratação/resfriamento em locais estratégicos.",
        ]
        base_gestores += [
            "Preparar reforço de equipe e comunicar rede assistencial sobre manejo rápido de casos relacionados ao calor.",
        ]
        base_prof += [
            "Aplicar manejo rápido de desidratação/exaustão térmica e encaminhar casos graves conforme regulação.",
        ]

    return base_municipios, base_gestores, base_prof


def make_compact_message(df, scope_name, min_rank=2, regional=None):
    if regional:
        base = df[df["regional_saude"].astype(str) == str(regional)].copy()
        affected = base[base["rank_final"] >= min_rank].copy()
    else:
        base = df.copy()
        affected = df[df["rank_final"] >= min_rank].copy()

    nivel_max = max_level(*affected["nivel_final"].tolist()) if not affected.empty else "verde"
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    title = f"{EMOJI.get(nivel_max)} Alerta Clima-Saúde — {scope_name} — {LEVEL_LABEL.get(nivel_max)}"
    subject = f"{EMOJI.get(nivel_max)} Alerta Clima-Saúde {scope_name} — {LEVEL_LABEL.get(nivel_max)} — {now}"

    dist = base["nivel_final"].value_counts().reindex(["verde", "amarela", "laranja", "vermelha", "roxa"]).fillna(0).astype(int)
    groups = group_municipios_by_level(base, min_rank=min_rank)
    highlights = specific_highlights(base, min_rank=min_rank)
    mun_guid, gest_guid, prof_guid = general_guidance(nivel_max)

    lines = [
        title,
        f"SIS Clima-Saúde MT é uma ferramenta para monitoramento de ondas de calor e apoio à tomada de decisão em saúde pública.\nGerado em: {now}",
        f"Municípios monitorados: {len(base)}",
        f"Municípios em alerta ≥ {LEVEL_LABEL.get(RANK_LEVEL.get(min_rank, 'laranja'))}: {len(affected)}",
        "",
        "Distribuição geral:",
        f"🟢 Verde: {int(dist.get('verde', 0))} | 🟡 Amarela: {int(dist.get('amarela', 0))} | 🟠 Laranja: {int(dist.get('laranja', 0))} | 🔴 Vermelha: {int(dist.get('vermelha', 0))} | 🟣 Roxa: {int(dist.get('roxa', 0))}",
        "",
        "Municípios por nível:",
    ]

    if groups:
        lines += groups
    else:
        lines.append("Sem municípios acima do limiar definido.")

    if highlights:
        lines += ["", "Destaques específicos:", *[f"- {x}" for x in highlights]]

    lines += [
        "",
        "Orientações gerais aos municípios:",
        *[f"- {x}" for x in mun_guid],
        "",
        "Orientações aos gestores:",
        *[f"- {x}" for x in gest_guid],
        "",
        "Orientações aos profissionais de saúde:",
        *[f"- {x}" for x in prof_guid],
        "",
        "Encaminhamento: manter monitoramento diário, registrar ações adotadas e comunicar agravamento de cenário à Regional/CIEVS.",
    ]

    txt = "\n".join(lines)

    html_body = "<html><body>"
    html_body += f"<h2>{html.escape(title)}</h2>"
    html_body += f"<p><b>SIS Clima-Saúde MT é uma ferramenta para monitoramento de ondas de calor e apoio à tomada de decisão em saúde pública.\nGerado em:</b> {html.escape(now)}<br><b>Monitorados:</b> {len(base)}<br><b>Em alerta:</b> {len(affected)}</p>"
    html_body += "<h3>Distribuição geral</h3>"
    html_body += f"<p>🟢 Verde: {int(dist.get('verde', 0))} | 🟡 Amarela: {int(dist.get('amarela', 0))} | 🟠 Laranja: {int(dist.get('laranja', 0))} | 🔴 Vermelha: {int(dist.get('vermelha', 0))} | 🟣 Roxa: {int(dist.get('roxa', 0))}</p>"
    html_body += "<h3>Municípios por nível</h3><ul>"
    for line in groups or ["Sem municípios acima do limiar definido."]:
        html_body += f"<li>{html.escape(line)}</li>"
    html_body += "</ul>"
    if highlights:
        html_body += "<h3>Destaques específicos</h3><ul>"
        for h in highlights:
            html_body += f"<li>{html.escape(h)}</li>"
        html_body += "</ul>"
    for title2, items in [("Orientações gerais aos municípios", mun_guid), ("Orientações aos gestores", gest_guid), ("Orientações aos profissionais de saúde", prof_guid)]:
        html_body += f"<h3>{html.escape(title2)}</h3><ul>"
        for item in items:
            html_body += f"<li>{html.escape(item)}</li>"
        html_body += "</ul>"
    html_body += "<p><b>Encaminhamento:</b> manter monitoramento diário, registrar ações adotadas e comunicar agravamento de cenário à Regional/CIEVS.</p>"
    html_body += "</body></html>"

    # Telegram ainda mais curto
    tg_lines = lines[:]
    telegram = "\n".join(tg_lines)
    if len(telegram) > 3800:
        # Compacta grupos se necessário
        telegram = "\n".join(lines[:9] + groups[:6] + ["", "Destaques:"] + [f"- {h}" for h in highlights[:4]] + ["", "Orientações: hidratação, comunicação de risco, monitorar vulneráveis, verificar rede/insumos e comunicar agravamentos."])
    return subject, txt, html_body, telegram[:3900], nivel_max, len(affected)


def smtp_settings():
    host = env_first("SMTP_HOST", "EMAIL_HOST", "MAIL_SERVER", "MAIL_HOST")
    port = int(env_first("SMTP_PORT", "EMAIL_PORT", "MAIL_PORT", default="587"))
    user = env_first("SMTP_USER", "EMAIL_USER", "MAIL_USERNAME", "MAIL_USER")
    password = env_first("SMTP_PASSWORD", "EMAIL_PASSWORD", "EMAIL_SENHA", "MAIL_PASSWORD", "MAIL_PASS")
    sender = env_first("SMTP_FROM", "EMAIL_FROM", "EMAIL_REMETENTE", "MAIL_FROM", "SMTP_SENDER", default=user)

    raw_tls = env_first("SMTP_TLS", "EMAIL_USE_TLS", "MAIL_USE_TLS")
    raw_ssl = env_first("SMTP_SSL", "EMAIL_USE_SSL", "MAIL_USE_SSL")
    if raw_tls is None and raw_ssl is None:
        use_ssl = port == 465
        use_tls = port != 465
    else:
        use_ssl = env_bool("SMTP_SSL", "EMAIL_USE_SSL", "MAIL_USE_SSL", default=(port == 465))
        use_tls = env_bool("SMTP_TLS", "EMAIL_USE_TLS", "MAIL_USE_TLS", default=(port != 465))
    if use_ssl:
        use_tls = False
    return host, port, user, password, sender, use_ssl, use_tls


def send_email(to_list, subject, html_body, txt_body):
    if not to_list:
        return False, "sem destinatários"
    host, port, user, password, sender, use_ssl, use_tls = smtp_settings()
    if not host or not sender or not user or not password:
        return False, "SMTP incompleto"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(txt_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as server:
                server.login(user, password)
                server.sendmail(sender, to_list, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(user, password)
                server.sendmail(sender, to_list, msg.as_string())
        return True, f"enviado para {len(to_list)}"
    except Exception as exc:
        return False, str(exc)


def send_telegram(chat_ids, text):
    token = env_first("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN")
    if not chat_ids:
        return False, "sem chat_id"
    if not token:
        return False, "token ausente"

    ok = 0
    errors = []
    for chat_id in chat_ids:
        try:
            payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": "true"}).encode("utf-8")
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    ok += 1
                else:
                    errors.append(f"{chat_id}: HTTP {resp.status}")
        except Exception as exc:
            errors.append(f"{chat_id}: {exc}")
        time.sleep(0.2)
    return (ok > 0 and not errors), f"enviados {ok}; erros: {' | '.join(errors[:3])}" if errors else f"enviados {ok}"


def alert_key(data_alerta, scope, regional, nivel):
    """
    Chave estável V10.3.
    Não usa assunto nem horário, para impedir reenvio do mesmo boletim no mesmo dia.
    """
    raw = f"{data_alerta}|{scope}|{regional}|{nivel}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def already_sent(con, data_alerta, scope, regional, nivel, canal, destinatario):
    """
    Deduplicação rígida por dia, escopo, regional, nível máximo, canal e destinatário.
    Funciona mesmo para envios V10.2 anteriores, pois consulta os campos estruturados.
    """
    q = pd.read_sql(
        """
        SELECT COUNT(*) n
        FROM historico_envios_alertas_v10_2
        WHERE data_alerta=?
          AND escopo=?
          AND regional_saude=?
          AND nivel_maximo=?
          AND canal=?
          AND destinatario=?
          AND status_envio='enviado'
        """,
        con,
        params=(data_alerta, scope, regional or "", nivel, canal, destinatario),
    )
    return int(q.iloc[0]["n"]) > 0


def log_send(con, data_alerta, scope, regional, nivel, canal, destinatario, subject, key, status, detail):
    con.execute(
        """
        INSERT INTO historico_envios_alertas_v10_2 (
            data_envio, data_alerta, escopo, regional_saude, nivel_maximo,
            canal, destinatario, assunto, chave_alerta, status_envio, detalhe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data_alerta, scope, regional or "", nivel,
            canal, destinatario, subject, key, status, detail,
        ),
    )
    con.commit()


def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--min-level", default="laranja")
    parser.add_argument("--scope", default="all", choices=["all", "estadual", "regional"])
    args = parser.parse_args()

    do_send = bool(args.send)
    min_rank = level_rank(args.min_level)
    data_alerta = date.today().isoformat()

    with sqlite3.connect(DB) as con:
        ensure_history(con)
        contacts = load_contacts()
        df = build_dataset(con)

        generated = []
        html_parts = ["<html><body><h1>Prévia compacta de alertas V10.3</h1>"]
        txt_parts = []

        if args.scope in ["all", "estadual"]:
            subject, txt, html_body, telegram, nivel, n_aff = make_compact_message(df, "MT", min_rank=min_rank)
            emails, chats = recipients(contacts, "estadual")
            key = alert_key(data_alerta, "estadual", "MT", nivel)
            generated.append({"data_alerta": data_alerta, "escopo": "estadual", "regional_saude": "MT", "nivel_maximo": nivel, "municipios_em_alerta": n_aff, "assunto": subject, "texto": txt, "emails": ";".join(emails), "telegram_chat_ids": ";".join(chats)})
            html_parts.append(html_body)
            txt_parts.append(txt)

            if do_send:
                for e in emails:
                    if args.force or not already_sent(con, data_alerta, "estadual", "MT", nivel, "email", e):
                        ok, detail = send_email([e], subject, html_body, txt)
                        log_send(con, data_alerta, "estadual", "MT", nivel, "email", e, subject, key, "enviado" if ok else "erro", detail)
                for c in chats:
                    if args.force or not already_sent(con, data_alerta, "estadual", "MT", nivel, "telegram", c):
                        ok, detail = send_telegram([c], telegram)
                        log_send(con, data_alerta, "estadual", "MT", nivel, "telegram", c, subject, key, "enviado" if ok else "erro", detail)

        if args.scope in ["all", "regional"]:
            affected = df[df["rank_final"] >= min_rank].copy()
            for regional in sorted(affected["regional_saude"].dropna().astype(str).unique()):
                subject, txt, html_body, telegram, nivel, n_aff = make_compact_message(df, regional, min_rank=min_rank, regional=regional)
                emails, chats = recipients(contacts, "regional", regional=regional)
                key = alert_key(data_alerta, "regional", regional, nivel)
                generated.append({"data_alerta": data_alerta, "escopo": "regional", "regional_saude": regional, "nivel_maximo": nivel, "municipios_em_alerta": n_aff, "assunto": subject, "texto": txt, "emails": ";".join(emails), "telegram_chat_ids": ";".join(chats)})
                html_parts.append(html_body)
                txt_parts.append(txt)

                if do_send:
                    for e in emails:
                        if args.force or not already_sent(con, data_alerta, "regional", regional, nivel, "email", e):
                            ok, detail = send_email([e], subject, html_body, txt)
                            log_send(con, data_alerta, "regional", regional, nivel, "email", e, subject, key, "enviado" if ok else "erro", detail)
                    for c in chats:
                        if args.force or not already_sent(con, data_alerta, "regional", regional, nivel, "telegram", c):
                            ok, detail = send_telegram([c], telegram)
                            log_send(con, data_alerta, "regional", regional, nivel, "telegram", c, subject, key, "enviado" if ok else "erro", detail)

        html_parts.append("</body></html>")
        OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
        OUT_HTML.write_text("\n<hr>\n".join(html_parts), encoding="utf-8")
        OUT_TXT.write_text(("\n\n" + "="*80 + "\n\n").join(txt_parts), encoding="utf-8")

        gen_df = pd.DataFrame(generated)
        if gen_df.empty:
            gen_df = pd.DataFrame(columns=["data_alerta", "escopo", "regional_saude", "nivel_maximo", "municipios_em_alerta", "assunto", "texto", "emails", "telegram_chat_ids"])
        gen_df.to_sql("alertas_gerados_v10_2", con, if_exists="replace", index=False)

    print("OK: alertas curtos V10.3 concluídos.")
    print("Modo:", "ENVIO REAL" if do_send else "SIMULAÇÃO")
    print("Alertas consolidados gerados:", len(generated))
    print("Prévia HTML:", OUT_HTML)
    print("Prévia TXT:", OUT_TXT)
    if not do_send:
        print("Nenhum envio real foi feito. Para enviar: --send")


if __name__ == "__main__":
    main()
