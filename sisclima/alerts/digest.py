# -*- coding: utf-8 -*-
"""Boletim periódico CIEVS (Telegram + e-mail) a partir do resumo operacional."""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from sisclima.alerts.notifier import dispatch_alert
from sisclima.core.config import as_bool, env
from sisclima.core.db import db_conn, execute, fetchone, read_table, table_exists
from sisclima.core.logging_utils import get_logger
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

LEVEL_RANK = {
    "cinza": -1,
    "verde": 0,
    "amarela": 1,
    "laranja": 2,
    "vermelha": 3,
    "roxa": 4,
}
EMOJI = {
    "verde": "🟢",
    "amarela": "🟡",
    "laranja": "🟠",
    "vermelha": "🔴",
    "roxa": "🟣",
    "cinza": "⚪",
}


def _norm_level(x: Any) -> str:
    s = str(x or "").strip().lower()
    if s in ("amarelo",):
        s = "amarela"
    if s in ("vermelho",):
        s = "vermelha"
    if s in ("roxo",):
        s = "roxa"
    return s if s in LEVEL_RANK else "cinza"


def min_level_ok(nivel: str, min_level: str | None = None) -> bool:
    floor = _norm_level(min_level or env("ALERT_MIN_LEVEL", "laranja"))
    return LEVEL_RANK.get(_norm_level(nivel), -1) >= LEVEL_RANK.get(floor, 2)


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
        age_h = (pd.Timestamp.utcnow().tz_localize(None) - prev.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600.0
        return age_h >= hrs
    except Exception:
        return True


def build_digest_message(resumo: pd.DataFrame | None = None) -> tuple[str, str, str, dict]:
    """Retorna subject, message, fingerprint, meta."""
    resumo = resumo if resumo is not None else read_table("resumo_municipal_atual")
    nivel_df = read_table("nivel_atual") if table_exists("nivel_atual") else pd.DataFrame()

    nivel_estado = "cinza"
    motivo = ""
    score = None
    data_ref = ""
    if not nivel_df.empty:
        row = nivel_df.iloc[0]
        nivel_estado = _norm_level(row.get("nivel"))
        motivo = str(row.get("motivo") or "")
        score = row.get("score")
        data_ref = str(row.get("data_referencia") or "")

    if resumo is not None and not resumo.empty and "nivel" in resumo.columns:
        # Sentinela: pior município no recorte
        ranks = resumo["nivel"].map(lambda x: LEVEL_RANK.get(_norm_level(x), -1))
        if ranks.notna().any() and int(ranks.max()) > LEVEL_RANK.get(nivel_estado, -1):
            worst = resumo.loc[ranks.idxmax()]
            nivel_estado = _norm_level(worst.get("nivel"))
            if not motivo:
                motivo = str(worst.get("motivo") or "")
            if score is None:
                score = worst.get("score")

    n = 0 if resumo is None or resumo.empty else len(resumo)
    dist = {}
    if resumo is not None and not resumo.empty and "nivel" in resumo.columns:
        dist = resumo["nivel"].astype(str).str.lower().value_counts().to_dict()

    top_lines = []
    if resumo is not None and not resumo.empty:
        sort_cols = [c for c in ["score", "indice_prioridade_global", "indice_vigilancia_integrada"] if c in resumo.columns]
        top = resumo.copy()
        if sort_cols:
            for c in sort_cols:
                top[c] = pd.to_numeric(top[c], errors="coerce")
            top = top.sort_values(sort_cols, ascending=[False] * len(sort_cols)).head(8)
        else:
            top = top.head(8)
        for _, r in top.iterrows():
            top_lines.append(
                f"- {r.get('municipio')}: {_norm_level(r.get('nivel')).upper()} "
                f"(score={r.get('score', '—')}"
                + (f", prioridade={r.get('indice_prioridade_global')}" if "indice_prioridade_global" in r.index and pd.notna(r.get("indice_prioridade_global")) else "")
                + ")"
            )

    emoji = EMOJI.get(nivel_estado, "⚪")
    subject = f"[SIS Clima-Saúde] {emoji} Boletim CIEVS — nível {nivel_estado.upper()}"
    dist_txt = ", ".join(f"{k}={v}" for k, v in sorted(dist.items(), key=lambda kv: -LEVEL_RANK.get(kv[0], -1))) or "—"
    motivos = [m.strip() for m in motivo.split(";") if m.strip()][:6]
    message = (
        f"Boletim operacional SIS Clima-Saúde MT\n"
        f"Gerado em: {now_iso()}\n"
        f"Data referência: {data_ref or '—'}\n"
        f"Nível estadual/sentinela: {emoji} {nivel_estado.upper()} (score={score if score is not None else '—'})\n"
        f"Municípios no resumo: {n}\n"
        f"Distribuição: {dist_txt}\n\n"
        f"Motivos principais:\n- "
        + ("\n- ".join(motivos) if motivos else "sem motivo informado")
        + "\n\nTop municípios:\n"
        + ("\n".join(top_lines) if top_lines else "- —")
        + "\n\nValidar no painel antes de comunicação oficial externa.\n"
        + "Lista de contatos provisória — aguardando atualização CIEVS."
    )
    fp_src = f"{nivel_estado}|{dist_txt}|{'|'.join(top_lines[:5])}"
    fingerprint = hashlib.sha1(fp_src.encode("utf-8")).hexdigest()[:16]
    meta = {
        "nivel": nivel_estado,
        "score": score,
        "n_municipios": n,
        "distribuicao": dist,
        "fingerprint": fingerprint,
    }
    return subject, message, fingerprint, meta


def send_digest(
    *,
    force: bool = False,
    skip_cooldown: bool = False,
    resumo: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    Envia boletim Telegram+e-mail se:
    - SEND_ALERT_ON_LEVEL_CHANGE=true (ou force=True), e
    - nível >= ALERT_MIN_LEVEL, e
    - cooldown ok (ou force/skip_cooldown), e
    - fingerprint mudou OU force (evita spam idêntico).
    """
    _ensure_digest_table()
    subject, message, fingerprint, meta = build_digest_message(resumo)
    nivel = meta["nivel"]

    if not force and not as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false"), False):
        out = {"status": "bloqueado_por_config", "nivel": nivel, "fingerprint": fingerprint}
        log.info("Digest bloqueado: SEND_ALERT_ON_LEVEL_CHANGE=false")
        return out

    if not min_level_ok(nivel):
        out = {"status": "abaixo_do_minimo", "nivel": nivel, "min": env("ALERT_MIN_LEVEL", "laranja")}
        log.info("Digest não enviado: nível %s < mínimo", nivel)
        return out

    last = _last_digest()
    if not force and not skip_cooldown and not _cooldown_ok():
        out = {"status": "cooldown", "nivel": nivel, "ultimo": (last or {}).get("enviado_em")}
        log.info("Digest em cooldown")
        return out

    if (
        not force
        and last
        and last.get("fingerprint") == fingerprint
        and as_bool(env("ALERT_DIGEST_SKIP_IDENTICO", "true"), True)
    ):
        out = {"status": "identico", "nivel": nivel, "fingerprint": fingerprint}
        log.info("Digest idêntico ao anterior — skip")
        return out

    results = dispatch_alert(subject, message, meta)
    status = "enviado" if any(results.values()) else "registrado_sem_canal"
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
                subject,
                message[:4000],
                json.dumps({"tipo": "digest", **results}, ensure_ascii=False),
                status,
            ),
        )
    log.info("Digest %s · canais=%s · nivel=%s", status, results, nivel)
    return {"status": status, "canais": results, **meta}
