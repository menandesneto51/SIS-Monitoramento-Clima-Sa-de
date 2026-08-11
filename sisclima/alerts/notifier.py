from __future__ import annotations
import html
import mimetypes
import smtplib
from email.message import EmailMessage
from pathlib import Path

import requests

from sisclima.alerts.whatsapp import send_whatsapp
from sisclima.branding import (
    ALERT_BRAND_CARD_PATH,
    INLINE_BRAND_ASSETS,
    SYSTEM_NAME,
    SYSTEM_TAGLINE,
    branded_subject,
    html_email_shell,
    wrap_plain_message,
)
from sisclima.core.config import env, as_bool, env_name_used
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _email_enabled(to: str | list[str] | tuple[str, ...] | None = None) -> bool:
    if env_name_used('ALERT_EMAIL_ENABLED'):
        return as_bool(env('ALERT_EMAIL_ENABLED'), False)
    return bool(env('SMTP_HOST') and env('SMTP_USER') and env('SMTP_PASSWORD') and (to or env('ALERT_EMAIL_TO')))


def _telegram_enabled(chat_id: str | None = None) -> bool:
    if env_name_used('ALERT_TELEGRAM_ENABLED'):
        return as_bool(env('ALERT_TELEGRAM_ENABLED'), False)
    return bool(env('TELEGRAM_BOT_TOKEN') and (chat_id or env('TELEGRAM_CHAT_ID')))


def _webhook_enabled() -> bool:
    if env_name_used('ALERT_WEBHOOK_ENABLED'):
        return as_bool(env('ALERT_WEBHOOK_ENABLED'), False)
    return bool(env('WEBHOOK_URL'))


def _split_recipients(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw = [str(v) for v in value]
    else:
        raw = str(value).replace(";", ",").split(",")
    return [item.strip() for item in raw if item and item.strip()]


def _attach_inline_brand_assets(message: EmailMessage) -> None:
    payload = message.get_payload()
    if not isinstance(payload, list) or not payload:
        return
    html_part = payload[-1]
    for cid, path in INLINE_BRAND_ASSETS.items():
        asset = Path(path)
        if not asset.exists():
            continue
        mime, _ = mimetypes.guess_type(asset.name)
        maintype, subtype = (mime or "image/png").split("/", 1)
        html_part.add_related(
            asset.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            cid=f"<{cid}>",
            filename=asset.name,
        )


def send_email(
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
    to: str | list[str] | tuple[str, ...] | None = None,
) -> bool:
    if not _email_enabled(to):
        return False
    recipients = _split_recipients(to or env('ALERT_EMAIL_TO'))
    if not recipients:
        return False
    msg = EmailMessage()
    msg['Subject'] = branded_subject(subject)
    msg['From'] = env('SMTP_FROM') or env('SMTP_USER') or 'araras@ses.mt.gov.br'
    msg['To'] = ', '.join(recipients)
    branded_plain = wrap_plain_message(body)
    msg.set_content(branded_plain)
    rendered_body = html_body or (
        '<pre style="white-space:pre-wrap;font:14px/1.55 Segoe UI,Arial,sans-serif">'
        f'{html.escape(str(body or ""))}</pre>'
    )
    msg.add_alternative(html_email_shell(rendered_body), subtype='html')
    _attach_inline_brand_assets(msg)
    try:
        with smtplib.SMTP(env('SMTP_HOST','smtp.gmail.com'), int(env('SMTP_PORT','587') or 587), timeout=30) as s:
            s.starttls()
            if env('SMTP_USER') and env('SMTP_PASSWORD'):
                s.login(env('SMTP_USER'), env('SMTP_PASSWORD'))
            s.send_message(msg)
        return True
    except Exception as e:
        log.warning('Falha e-mail: %s', e)
        return False


def send_telegram_brand_card(*, chat_id: str | None = None) -> bool:
    """Envia a marca como cartão visual antes do texto do boletim."""
    if not _telegram_enabled(chat_id):
        return False
    token = env('TELEGRAM_BOT_TOKEN')
    destination = chat_id or env('TELEGRAM_CHAT_ID')
    if not token or not destination or not ALERT_BRAND_CARD_PATH.exists():
        return False
    try:
        with ALERT_BRAND_CARD_PATH.open('rb') as logo:
            r = requests.post(
                f'https://api.telegram.org/bot{token}/sendPhoto',
                data={
                    'chat_id': destination,
                    'caption': (
                        f'{SYSTEM_NAME} · {SYSTEM_TAGLINE}\n'
                        'SES-MT · CIEVS-MT · Rede CIEVS · Vigidesastres'
                    ),
                },
                files={'photo': (ALERT_BRAND_CARD_PATH.name, logo, 'image/png')},
                timeout=30,
            )
        return r.ok
    except Exception as e:
        log.warning('Falha ao enviar cartão de marca no Telegram: %s', e)
        return False


def send_telegram(text: str, *, chat_id: str | None = None, with_brand: bool = True) -> bool:
    if not _telegram_enabled(chat_id):
        return False
    token = env('TELEGRAM_BOT_TOKEN')
    destination = chat_id or env('TELEGRAM_CHAT_ID')
    if not token or not destination:
        return False
    if with_brand:
        send_telegram_brand_card(chat_id=destination)
    message = str(text or '').strip()
    if not message.startswith(SYSTEM_NAME):
        message = f'{SYSTEM_NAME} · {SYSTEM_TAGLINE}\n\n{message}'
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': destination, 'text': message},
            timeout=30,
        )
        return r.ok
    except Exception as e:
        log.warning('Falha Telegram: %s', e)
        return False


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
    payload = payload or {}
    branded = branded_subject(subject)
    results = {
        'email': send_email(branded, message),
        'telegram': send_telegram(f'{branded}\n\n{message}', with_brand=True),
        'whatsapp': send_whatsapp(
            f'{SYSTEM_NAME} · {SYSTEM_TAGLINE}\n\n{branded}\n\n{message}',
            payload={'subject': branded, **payload},
        ),
        'webhook': send_webhook({'subject': branded, 'message': message, **payload})
    }
    log.info('Resultado envio alertas: %s', results)
    return results
