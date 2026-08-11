# -*- coding: utf-8 -*-
"""
V11.10 - Alerta municipal específico de Cuiabá

Envia boletim/alerta com dados específicos do município de Cuiabá para:
vigidesastrescuiaba@gmail.com

Fontes no SQLite:
- resumo_municipal_atual
- predicao_calor_7d_municipal_v6
- alerta_inteligente_municipal_v6
- v9_priorizacao_epidemiologica
- hospital_ocupacao_municipio
- hospital_ocupacao_estado

Uso:
python alerta_municipal_cuiaba_v11_10.py --dry-run
python alerta_municipal_cuiaba_v11_10.py --send
python alerta_municipal_cuiaba_v11_10.py --send --force
"""

from __future__ import annotations

import argparse
import os
import re
import smtplib
import sqlite3
import ssl
import sys
import unicodedata
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.branding import (
    INLINE_BRAND_ASSETS,
    PROJECT_DESCRIPTION,
    SYSTEM_EXPANSION,
    SYSTEM_NAME,
    SYSTEM_TAGLINE,
    branded_subject,
    html_email_shell,
    wrap_plain_message,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DB = Path("data/output/sis_integrado.db")
DEFAULT_TO = "vigidesastrescuiaba@gmail.com"
MUNICIPIO = "Cuiabá"
COD_IBGE_CUIABA = "5103403"
HIST_TABLE = "historico_envios_alerta_cuiaba_v11_10"

NIVEL_ORDEM = {
    "cinza": -1,
    "verde": 0,
    "amarela": 1,
    "amarelo": 1,
    "laranja": 2,
    "vermelha": 3,
    "vermelho": 3,
    "roxa": 4,
    "roxo": 4,
}

EMOJI = {
    "cinza": "⚪",
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
}


def load_env(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def normalize_text(s: Any) -> str:
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()


def normalize_level(x: Any) -> str:
    s = normalize_text(x)
    if s in NIVEL_ORDEM:
        # padronizar feminino
        if s == "amarelo":
            return "amarela"
        if s == "vermelho":
            return "vermelha"
        if s == "roxo":
            return "roxa"
        return s
    return "cinza"


def level_rank(x: Any) -> int:
    return NIVEL_ORDEM.get(normalize_level(x), -1)


def fmt_num(x: Any, dec: int = 1, suffix: str = "") -> str:
    try:
        if pd.isna(x):
            return "indisponível"
        val = float(x)
        return f"{val:.{dec}f}{suffix}"
    except Exception:
        return "indisponível"


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    q = pd.read_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        con,
        params=(name,),
    )
    return not q.empty


def read_table(con: sqlite3.Connection, name: str) -> pd.DataFrame:
    if not table_exists(con, name):
        return pd.DataFrame()
    return pd.read_sql(f"SELECT * FROM {name}", con)


def find_cuiaba(df: pd.DataFrame) -> pd.Series | None:
    if df.empty:
        return None

    # preferir cod_ibge
    for c in ["cod_ibge", "codigo_ibge", "ibge", "cod_municipio"]:
        if c in df.columns:
            m = df[df[c].astype(str).str.replace(r"\.0$", "", regex=True).eq(COD_IBGE_CUIABA)]
            if not m.empty:
                return m.iloc[0]

    # fallback por nome
    for c in ["municipio", "nome_municipio", "localidade"]:
        if c in df.columns:
            m = df[df[c].map(normalize_text).eq(normalize_text(MUNICIPIO))]
            if not m.empty:
                return m.iloc[0]

    return None


def get(row: pd.Series | None, *cols: str, default: Any = None) -> Any:
    if row is None:
        return default
    for c in cols:
        if c in row.index:
            v = row[c]
            if not pd.isna(v):
                return v
    return default


def create_history(con: sqlite3.Connection) -> None:
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {HIST_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_envio TEXT,
            data_alerta TEXT,
            municipio TEXT,
            cod_ibge TEXT,
            canal TEXT,
            destinatario TEXT,
            nivel_operacional TEXT,
            nivel_predicao_7d TEXT,
            nivel_alerta_inteligente TEXT,
            status_envio TEXT,
            detalhe TEXT
        )
    """)
    con.commit()


def already_sent(con: sqlite3.Connection, to: str, force: bool = False) -> bool:
    if force:
        return False
    create_history(con)
    today = datetime.now().strftime("%Y-%m-%d")
    q = pd.read_sql(f"""
        SELECT COUNT(*) n
        FROM {HIST_TABLE}
        WHERE data_alerta = ?
          AND canal = 'email'
          AND destinatario = ?
          AND status_envio = 'enviado'
    """, con, params=(today, to))
    return int(q.iloc[0]["n"]) > 0


def record_history(
    con: sqlite3.Connection,
    to: str,
    nivel: str,
    pred: str,
    inteligente: str,
    status: str,
    detalhe: str,
) -> None:
    create_history(con)
    now = datetime.now()
    con.execute(f"""
        INSERT INTO {HIST_TABLE}
        (data_envio, data_alerta, municipio, cod_ibge, canal, destinatario,
         nivel_operacional, nivel_predicao_7d, nivel_alerta_inteligente,
         status_envio, detalhe)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now.strftime("%Y-%m-%d %H:%M:%S"),
        now.strftime("%Y-%m-%d"),
        MUNICIPIO,
        COD_IBGE_CUIABA,
        "email",
        to,
        nivel,
        pred,
        inteligente,
        status,
        detalhe[:500],
    ))
    con.commit()


def build_payload(con: sqlite3.Connection) -> dict[str, Any]:
    resumo = read_table(con, "resumo_municipal_atual")
    pred = read_table(con, "predicao_calor_7d_municipal_v6")
    ai = read_table(con, "alerta_inteligente_municipal_v6")
    v9 = read_table(con, "v9_priorizacao_epidemiologica")
    ocup_mun = read_table(con, "hospital_ocupacao_municipio")
    ocup_est = read_table(con, "hospital_ocupacao_estado")

    r = find_cuiaba(resumo)
    p = find_cuiaba(pred)
    a = find_cuiaba(ai)
    v = find_cuiaba(v9)
    h = find_cuiaba(ocup_mun)

    nivel = normalize_level(get(r, "nivel", "nivel_operacional", default="cinza"))
    nivel_pred = normalize_level(get(p, "nivel_predicao_7d", default=get(a, "nivel_predicao_7d", default="cinza")))
    nivel_ai = normalize_level(get(a, "alerta_inteligente_nivel", "nivel_alerta_inteligente", default="cinza"))
    nivel_v9 = normalize_level(get(v, "nivel_priorizacao_v9", "prioridade_v9", "nivel_prioridade", default="cinza"))

    max_nivel = max([nivel, nivel_pred, nivel_ai, nivel_v9], key=level_rank)

    # campos operacionais
    data = {
        "municipio": MUNICIPIO,
        "cod_ibge": COD_IBGE_CUIABA,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "dados_atualizados_em": (
            datetime.fromtimestamp(DB.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            if DB.exists() else datetime.now().strftime("%d/%m/%Y %H:%M")
        ),
        "emitido_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "nivel_operacional": nivel,
        "nivel_predicao_7d": nivel_pred,
        "nivel_alerta_inteligente": nivel_ai,
        "nivel_prioridade_v9": nivel_v9,
        "nivel_final": max_nivel,

        "score": get(r, "score", "score_operacional", default=None),
        "risco3d": get(r, "risco_cumulativo_3d", default=get(p, "risco_cumulativo_3d_max_7d", default=None)),
        "risco3d_pred": get(p, "risco_cumulativo_3d_max_7d", default=None),
        "tmax": get(r, "tmax", "tmax_atual", "tmax_max", default=get(p, "tmax_max_7d", default=None)),
        "tmax_pred": get(p, "tmax_max_7d", default=None),
        "utci": get(r, "utci_proxy", "utci", default=get(p, "utci_proxy_max_7d", default=None)),
        "utci_pred": get(p, "utci_proxy_max_7d", default=None),
        "pm25": get(r, "pm25_ugm3", default=None),
        "iqa": get(r, "iq_ar_score", "iqa", default=None),

        "ocupacao_pct": get(r, "ocupacao_leitos_pct", default=get(h, "ocupacao_leitos_pct", "ocupacao_pct", default=None)),
        "pressao_pct": get(r, "pressao_calor_pct", default=None),
        "leitos_total": get(r, "leitos_total", default=get(h, "leitos_total", "leitos_existentes", default=None)),
        "leitos_ocupados": get(r, "leitos_ocupados", default=get(h, "leitos_ocupados", default=None)),

        "risco_preditivo_score": get(p, "risco_preditivo_score", default=get(a, "risco_preditivo_score", default=None)),
        "onda_p95_prevista": get(p, "onda_calor_p95_2d_prevista", default=None),
        "prioridade_v9_score": get(v, "score_priorizacao_v9", "score_prioridade", "score", default=None),
        "motivo": get(r, "motivo", default=""),
    }

    if not ocup_est.empty:
        data["ocupacao_estado_pct"] = get(ocup_est.iloc[0], "ocupacao_leitos_pct", "ocupacao_pct", default=None)
    else:
        data["ocupacao_estado_pct"] = None

    return data


def recommendations(payload: dict[str, Any]) -> list[str]:
    nivel = payload["nivel_final"]
    rec = [
        "Manter monitoramento diário do painel e comunicação com a Vigilância em Saúde/Defesa Civil municipal.",
        "Reforçar orientação à população sobre hidratação, evitar exposição ao sol nos horários críticos e reconhecer sinais de agravamento.",
        "Orientar APS, urgência e rede assistencial para triagem de idosos, crianças, gestantes, pessoas com doenças crônicas, trabalhadores expostos ao sol e população em situação de rua.",
    ]

    if level_rank(nivel) >= 2:
        rec.extend([
            "Ativar comunicação de risco municipal específica para calor extremo.",
            "Verificar pontos de hidratação, locais de acolhimento/resfriamento e disponibilidade de água potável em serviços públicos.",
            "Checar escala, transporte sanitário, fluxos de regulação e insumos de hidratação na rede municipal.",
        ])

    if level_rank(nivel) >= 3:
        rec.extend([
            "Avaliar acionamento formal do plano municipal de resposta a calor extremo.",
            "Avaliar reprogramação de atividades ao ar livre nos horários de maior calor, especialmente para grupos vulneráveis.",
            "Monitorar atendimentos por desidratação, síncope, exaustão pelo calor, agravos cardiorrespiratórios e piora renal.",
        ])

    try:
        pm25 = float(payload.get("pm25"))
        if pm25 >= 25:
            rec.append("PM2.5 elevado: reforçar orientação para pneumopatas, idosos e crianças reduzirem exposição à fumaça e atividades externas.")
    except Exception:
        pass

    return rec



def load_geocalor_cardioresp_cuiaba_block() -> list[str]:
    """Carrega resultados GeoCalor cardiorrespiratórios para Cuiabá."""
    import sqlite3 as _sqlite3_geo
    import pandas as _pd_geo
    from pathlib import Path as _Path_geo

    db = _Path_geo("data/output/sis_integrado.db")
    if not db.exists():
        return [
            "Análise GeoCalor cardiorrespiratória:",
            "- Banco local indisponível para leitura dos resultados de RR."
        ]

    try:
        con_geo = _sqlite3_geo.connect(db)
        exists_geo = _pd_geo.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='geocalor_cuiaba_cardioresp_v11_12'",
            con_geo
        )
        if exists_geo.empty:
            con_geo.close()
            return [
                "Análise GeoCalor cardiorrespiratória:",
                "- Tabela geocalor_cuiaba_cardioresp_v11_12 ainda não foi gerada.",
                "- Rodar calcular_geocalor_cardioresp_v11_12.py para atualizar esta seção."
            ]

        df_geo = _pd_geo.read_sql("SELECT * FROM geocalor_cuiaba_cardioresp_v11_12", con_geo)
        con_geo.close()

        lines_geo = ["Análise GeoCalor cardiorrespiratória:"]
        if df_geo.empty:
            lines_geo.append("- Sem resultado disponível para Cuiabá.")
            return lines_geo

        status_vals = set(df_geo.get("status_modelagem", _pd_geo.Series(dtype=str)).dropna().astype(str).unique())
        if any("insuficiente" in s for s in status_vals):
            detalhe = str(df_geo.get("detalhe", _pd_geo.Series(["Dados insuficientes."])).dropna().astype(str).iloc[0])
            lines_geo.append("- Status: dados diários insuficientes para estimar RR local com defasagens 0–7.")
            lines_geo.append(f"- Observação: {detalhe[:700]}")
            lines_geo.append("- Interpretação: a nota GeoCalor permanece como referência metodológica; não há RR municipal validado para Cuiabá nesta execução.")
            return lines_geo

        for desfecho, g in df_geo.groupby("desfecho_label"):
            g2 = g.sort_values("rr", ascending=False).head(1)
            if g2.empty:
                continue
            r = g2.iloc[0]
            try:
                rr = float(r["rr"])
                li = float(r["rr_ic95_inf"])
                ls = float(r["rr_ic95_sup"])
                lag = int(r["lag"])
                lines_geo.append(f"- {desfecho}: maior RR lag {lag} = {rr:.2f} (IC95% {li:.2f}–{ls:.2f}); método {r.get('metodo','')}.")
            except Exception:
                lines_geo.append(f"- {desfecho}: resultado disponível, mas sem RR numérico válido.")

        lines_geo.append("- Uso: interpretar como componente epidemiológico complementar ao alerta operacional municipal.")
        return lines_geo
    except Exception as e:
        return [
            "Análise GeoCalor cardiorrespiratória:",
            f"- Erro ao carregar resultados: {type(e).__name__}: {e}"
        ]

def compose_text(payload: dict[str, Any]) -> str:
    emoji = EMOJI.get(payload["nivel_final"], "⚪")
    recs = recommendations(payload)

    lines = []
    lines.append(f"{emoji} Alerta ARARAS MT — Cuiabá — {payload['nivel_final'].capitalize()}")
    lines.append(PROJECT_DESCRIPTION)
    lines.append(f"Dados atualizados em: {payload['dados_atualizados_em']}")
    lines.append(f"Emitido em: {payload['emitido_em']}")
    lines.append("")
    lines.append("Município: Cuiabá")
    lines.append("Código IBGE: 5103403")
    lines.append("")
    lines.append("Síntese operacional:")
    lines.append(f"- Nível operacional atual: {payload['nivel_operacional'].capitalize()}")
    lines.append(f"- Predição 7 dias: {payload['nivel_predicao_7d'].capitalize()}")
    lines.append(f"- Alerta inteligente: {payload['nivel_alerta_inteligente'].capitalize()}")
    lines.append(f"- Prioridade epidemiológica V9: {payload['nivel_prioridade_v9'].capitalize()}")
    lines.append(f"- Nível final para comunicação: {payload['nivel_final'].capitalize()}")
    lines.append("")
    lines.append("Indicadores principais:")
    lines.append(f"- Tmax atual/proxy: {fmt_num(payload['tmax'], 1, ' °C')}")
    lines.append(f"- Tmax máxima 7 dias: {fmt_num(payload['tmax_pred'], 1, ' °C')}")
    lines.append(f"- UTCI/proxy atual: {fmt_num(payload['utci'], 1)}")
    lines.append(f"- UTCI/proxy máximo 7 dias: {fmt_num(payload['utci_pred'], 1)}")
    lines.append(f"- Risco cumulativo 3 dias atual: {fmt_num(payload['risco3d'], 2)}")
    lines.append(f"- Risco cumulativo 3 dias máximo 7 dias: {fmt_num(payload['risco3d_pred'], 2)}")
    lines.append(f"- PM2.5: {fmt_num(payload['pm25'], 1, ' µg/m³')}")
    lines.append(f"- IQA/score: {fmt_num(payload['iqa'], 1)}")
    lines.append(f"- Ocupação de leitos municipal/proxy: {fmt_num(payload['ocupacao_pct'], 1, '%')}")
    lines.append(f"- Pressão assistencial por calor/proxy: {fmt_num(payload['pressao_pct'], 1, '%')}")
    lines.append(f"- Leitos totais: {fmt_num(payload['leitos_total'], 0)}")
    lines.append(f"- Leitos ocupados: {fmt_num(payload['leitos_ocupados'], 0)}")
    lines.append("")
    if payload.get("motivo"):
        lines.append("Motivo técnico resumido:")
        lines.append(str(payload["motivo"])[:1200])
        lines.append("")

    lines.append("")
    for _linha_geo in load_geocalor_cardioresp_cuiaba_block():
        lines.append(_linha_geo)

    lines.append("Recomendações específicas para Cuiabá:")
    for r in recs:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("Encaminhamento:")
    lines.append("- Manter monitoramento diário, registrar ações adotadas e comunicar agravamento de cenário à Regional/CIEVS.")
    return "\n".join(lines)


def compose_html(text: str) -> str:
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.45;">
        <div style="max-width: 900px;">
          {safe}
        </div>
      </body>
    </html>
    """


def send_email(to: str, subject: str, text: str, html: str) -> tuple[bool, str]:
    load_env()

    host = env_first("SMTP_HOST", "EMAIL_SMTP_HOST", default="smtp.gmail.com")
    port = int(env_first("SMTP_PORT", "EMAIL_SMTP_PORT", default="465"))
    user = env_first("SMTP_USER", "EMAIL_USER", "EMAIL_REMETENTE", default="")
    password = env_first("SMTP_PASSWORD", "EMAIL_PASSWORD", "EMAIL_SENHA", default="")
    sender = env_first("EMAIL_FROM", "SMTP_FROM", "EMAIL_REMETENTE", default=user)
    ssl_flag = env_first("SMTP_SSL", "EMAIL_SMTP_SSL", default="").lower()
    tls_flag = env_first("SMTP_TLS", "EMAIL_SMTP_TLS", default="").lower()

    use_ssl = ssl_flag in {"1", "true", "sim", "yes"} or (port == 465 and tls_flag not in {"1", "true", "sim", "yes"})
    use_tls = tls_flag in {"1", "true", "sim", "yes"} and not use_ssl

    if not host or not port or not user or not password or not sender:
        return False, "Configuração SMTP incompleta no .env."

    msg = MIMEMultipart("related")
    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)
    msg["Subject"] = branded_subject(subject)
    msg["From"] = sender
    msg["To"] = to
    alternative.attach(MIMEText(wrap_plain_message(text), "plain", "utf-8"))
    alternative.attach(MIMEText(html_email_shell(html), "html", "utf-8"))
    for cid, asset in INLINE_BRAND_ASSETS.items():
        if not asset.exists():
            continue
        image = MIMEImage(asset.read_bytes())
        image.add_header("Content-ID", f"<{cid}>")
        image.add_header("Content-Disposition", "inline", filename=asset.name)
        msg.attach(image)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as server:
                server.login(user, password)
                server.sendmail(sender, [x.strip() for x in to.split(",") if x.strip()], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=60) as server:
                if use_tls:
                    server.starttls(context=ssl.create_default_context())
                server.login(user, password)
                server.sendmail(sender, [x.strip() for x in to.split(",") if x.strip()], msg.as_string())
        return True, "enviado"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Envia e-mail real.")
    parser.add_argument("--dry-run", action="store_true", help="Apenas gera prévia.")
    parser.add_argument("--force", action="store_true", help="Ignora deduplicação diária.")
    parser.add_argument("--to", default=DEFAULT_TO, help="Destinatário.")
    parser.add_argument("--min-level", default="verde", help="Nível mínimo para envio: verde, amarela, laranja, vermelha, roxa.")
    args = parser.parse_args()

    if not DB.exists():
        raise SystemExit(f"ERRO: banco não encontrado: {DB}")

    con = sqlite3.connect(DB)
    payload = build_payload(con)
    text = compose_text(payload)
    html = compose_html(text)

    out_dir = Path("data/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_txt = out_dir / "alerta_cuiaba_v11_10_preview.txt"
    preview_html = out_dir / "alerta_cuiaba_v11_10_preview.html"
    preview_txt.write_text(text, encoding="utf-8")
    preview_html.write_text(html, encoding="utf-8")

    subject = f"{EMOJI.get(payload['nivel_final'], '⚪')} Alerta ARARAS MT Cuiabá — {payload['nivel_final'].capitalize()} — {datetime.now():%d/%m/%Y}"

    print("============================================================")
    print("ALERTA MUNICIPAL CUIABÁ V11.10")
    print("============================================================")
    print(f"Destinatário: {args.to}")
    print(f"Nível final: {payload['nivel_final']}")
    print(f"Nível mínimo para envio: {normalize_level(args.min_level)}")
    print(f"Prévia TXT: {preview_txt}")
    print(f"Prévia HTML: {preview_html}")
    print()
    print(text)

    should_send = level_rank(payload["nivel_final"]) >= level_rank(args.min_level)

    if not args.send:
        print()
        print("Modo simulação. Nenhum envio real foi feito. Para enviar: --send")
        con.close()
        return

    if not should_send:
        detalhe = f"Nível {payload['nivel_final']} abaixo do mínimo {args.min_level}; envio não realizado."
        print(detalhe)
        record_history(con, args.to, payload["nivel_operacional"], payload["nivel_predicao_7d"], payload["nivel_alerta_inteligente"], "ignorado", detalhe)
        con.close()
        return

    if already_sent(con, args.to, force=args.force):
        detalhe = "Já existe envio para Cuiabá hoje. Use --force para reenviar."
        print(detalhe)
        record_history(con, args.to, payload["nivel_operacional"], payload["nivel_predicao_7d"], payload["nivel_alerta_inteligente"], "ignorado", detalhe)
        con.close()
        return

    ok, detalhe = send_email(args.to, subject, text, html)
    status = "enviado" if ok else "erro"
    record_history(con, args.to, payload["nivel_operacional"], payload["nivel_predicao_7d"], payload["nivel_alerta_inteligente"], status, detalhe)

    con.close()

    if ok:
        print(f"OK: e-mail enviado para {args.to}")
    else:
        print(f"ERRO: envio falhou: {detalhe}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
