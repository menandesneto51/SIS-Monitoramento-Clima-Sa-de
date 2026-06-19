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
    msg['From'] = env('SMTP_USER') or 'sisclima@local'
    msg['To'] = to
    msg.set_content(body)
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


def send_telegram(text: str) -> bool:
    if not _telegram_enabled():
        return False
    token = env('TELEGRAM_BOT_TOKEN')
    chat_id = env('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return False
    try:
        r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage', data={'chat_id': chat_id, 'text': text}, timeout=30)
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
    results = {
        'email': send_email(subject, message),
        'telegram': send_telegram(f'{subject}\n\n{message}'),
        'webhook': send_webhook({'subject': subject, 'message': message, **payload})
    }
    log.info('Resultado envio alertas: %s', results)
    return results
