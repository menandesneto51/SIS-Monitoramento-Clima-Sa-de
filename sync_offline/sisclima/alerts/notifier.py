from __future__ import annotations
import smtplib
from email.message import EmailMessage
import requests
from sisclima.core.config import env, as_bool, env_name_used
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


def send_email(subject: str, body: str) -> bool:
    if not _email_enabled():
        return False
    to = env('ALERT_EMAIL_TO')
    if not to:
        return False
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = env('SMTP_FROM') or env('SMTP_USER') or 'sisclima@local'
    msg['To'] = to
    # Texto puro (compatível) + HTML leve com tipografia monoespaçada preservando ícones.
    msg.set_content(body)
    html_body = (
        "<!DOCTYPE html><html><body style=\"margin:0;padding:0;background:#f4f6f8;\">"
        "<div style=\"max-width:720px;margin:16px auto;padding:20px 22px;"
        "background:#ffffff;border:1px solid #d9dee5;border-radius:10px;"
        "font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1f2933;"
        "line-height:1.45;font-size:14px;\">"
        "<pre style=\"white-space:pre-wrap;word-wrap:break-word;margin:0;"
        "font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px;\">"
        + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        + "</pre></div></body></html>"
    )
    msg.add_alternative(html_body, subtype="html")
    host = env('SMTP_HOST', 'smtp.gmail.com') or 'smtp.gmail.com'
    port = int(env('SMTP_PORT', '587') or 587)
    use_ssl = as_bool(env('SMTP_SSL'), port == 465)
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                if env('SMTP_USER') and env('SMTP_PASSWORD'):
                    s.login(env('SMTP_USER'), env('SMTP_PASSWORD'))
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.starttls()
                if env('SMTP_USER') and env('SMTP_PASSWORD'):
                    s.login(env('SMTP_USER'), env('SMTP_PASSWORD'))
                s.send_message(msg)
        return True
    except Exception as e:
        log.warning('Falha e-mail: %s', e)
        return False


def send_telegram(text: str) -> bool:
    if not _telegram_enabled():
        return False
    token = env('TELEGRAM_BOT_TOKEN')
    chat_id = env('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return False

    chunks = _split_telegram_chunks(text, limit=3500)

    try:
        verify = as_bool(env('ALERT_SSL_VERIFY', 'true'), True)
        ok_any = False
        for i, chunk in enumerate(chunks):
            r = requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': chunk},
                timeout=30,
                verify=verify,
            )
            ok_any = ok_any or r.ok
            if not r.ok:
                log.warning('Telegram parte %s/%s falhou: %s', i + 1, len(chunks), r.text[:200])
            elif i < len(chunks) - 1:
                import time
                time.sleep(0.35)
        return ok_any
    except Exception as e:
        detail = str(e)
        if token:
            detail = detail.replace(token, '***')
        log.warning('Falha Telegram: %s', detail)
        return False


def _split_telegram_chunks(text: str, limit: int = 3500) -> list[str]:
    """Parte o texto em blocos seguros para o Telegram (limite ~4096)."""
    text = str(text or "")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 3:
            cut = window.rfind("\n")
        if cut < limit // 3:
            cut = limit
        piece = remaining[:cut].rstrip()
        remaining = remaining[cut:].lstrip("\n")
        chunks.append(piece)

    total = len(chunks)
    if total <= 1:
        return chunks
    return [f"📨 Parte {i}/{total}\n\n{ch}" for i, ch in enumerate(chunks, start=1)]


def send_webhook(payload: dict) -> bool:
    if not _webhook_enabled():
        return False
    url = env('WEBHOOK_URL')
    if not url:
        return False
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.ok
    except Exception as e:
        log.warning('Falha webhook: %s', e)
        return False


def dispatch_alert(subject: str, message: str, payload: dict | None = None) -> dict:
    """Envia alerta completo no e-mail; Telegram é fatiado se passar de ~3500 chars."""
    payload = payload or {}
    full = f'{subject}\n\n{message}'
    results = {
        'email': send_email(subject, message),  # e-mail SEM truncar
        'telegram': send_telegram(full),        # Telegram em partes
        'webhook': send_webhook({'subject': subject, 'message': message, **payload}),
    }
    log.info(
        'Resultado envio alertas: %s | chars_email=%s | chars_telegram_total=%s',
        results,
        len(message),
        len(full),
    )
    return results
