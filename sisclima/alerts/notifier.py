from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Iterable

from sisclima.core.config import env, as_bool, env_name_used
from sisclima.core.http_client import http_post
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _email_enabled() -> bool:
    if env_name_used('ALERT_EMAIL_ENABLED'):
        return as_bool(env('ALERT_EMAIL_ENABLED'), False)
    return bool(env('SMTP_HOST') and env('SMTP_USER') and env('SMTP_PASSWORD') and env('ALERT_EMAIL_TO'))


def _telegram_enabled() -> bool:
    if env_name_used('ALERT_TELEGRAM_ENABLED'):
        return as_bool(env('ALERT_TELEGRAM_ENABLED'), False)
    return bool(env('TELEGRAM_BOT_TOKEN') and env('TELEGRAM_CHAT_ID'))


def _webhook_enabled() -> bool:
    if env_name_used('ALERT_WEBHOOK_ENABLED'):
        return as_bool(env('ALERT_WEBHOOK_ENABLED'), False)
    return bool(env('WEBHOOK_URL'))


def _split_recipients(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    out: list[str] = []
    for item in raw:
        out.extend(_split_recipients(str(item)))
    return out


def send_email(
    subject: str,
    body: str,
    html_body: str | None = None,
    *,
    to: str | Iterable[str] | None = None,
) -> bool:
    """Envia e-mail. ``to`` opcional; padrão = ALERT_EMAIL_TO (canal central CIEVS)."""
    if env_name_used("ALERT_EMAIL_ENABLED") and not as_bool(env("ALERT_EMAIL_ENABLED"), False):
        return False
    if to is None and not _email_enabled():
        return False

    recipients = _split_recipients(to if to is not None else env("ALERT_EMAIL_TO"))
    if not recipients:
        return False
    if not env("SMTP_HOST"):
        log.warning("SMTP_HOST ausente — e-mail não enviado")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env("SMTP_FROM") or env("SMTP_USER") or "sisclima@local"
    msg["To"] = ", ".join(recipients)
    msg.set_content(body or "Ver versão HTML.")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    host = env("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com"
    port = int(env("SMTP_PORT", "587") or 587)
    use_ssl = as_bool(env("SMTP_SSL"), port == 465)
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=45) as s:
                if env("SMTP_USER") and env("SMTP_PASSWORD"):
                    s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=45) as s:
                s.starttls()
                if env("SMTP_USER") and env("SMTP_PASSWORD"):
                    s.login(env("SMTP_USER"), env("SMTP_PASSWORD"))
                s.send_message(msg)
        return True
    except Exception as e:
        log.warning("Falha e-mail: %s", e)
        return False


def send_telegram(
    text: str,
    *,
    parse_mode: str | None = None,
    chat_id: str | None = None,
) -> bool:
    """Envia Telegram. ``chat_id`` opcional; padrão = TELEGRAM_CHAT_ID (canal central)."""
    if env_name_used("ALERT_TELEGRAM_ENABLED") and not as_bool(env("ALERT_TELEGRAM_ENABLED"), False):
        return False
    token = env("TELEGRAM_BOT_TOKEN")
    target = (chat_id or env("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not target:
        return False
    if chat_id is None and not _telegram_enabled():
        return False
    payload_text = text if len(text) <= 4000 else text[:3990] + "\n…"
    data = {"chat_id": target, "text": payload_text, "disable_web_page_preview": "true"}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        r = http_post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            timeout=45,
        )
        if not r.ok:
            log.warning("Telegram HTTP %s: %s", r.status_code, getattr(r, "text", "")[:300])
        return r.ok
    except Exception as e:
        log.warning("Falha Telegram: %s", e)
        return False


def send_webhook(payload: dict) -> bool:
    if not _webhook_enabled():
        return False
    url = env('WEBHOOK_URL')
    if not url:
        return False
    try:
        r = http_post(url, json=payload, timeout=30)
        return r.ok
    except Exception as e:
        log.warning('Falha webhook: %s', e)
        return False


def dispatch_alert(subject: str, message: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    results = {
        'email': send_email(subject, message),
        'telegram': send_telegram(f'{subject}\n\n{message}'),
        'webhook': send_webhook({'subject': subject, 'message': message, **payload})
    }
    log.info('Resultado envio alertas: %s', results)
    return results
