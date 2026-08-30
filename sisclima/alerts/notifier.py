from __future__ import annotations
import html
import mimetypes
import smtplib
import socket
import ssl
from email.message import EmailMessage
from pathlib import Path

import requests

from sisclima.alerts.whatsapp import send_whatsapp
from sisclima.branding import (
    ALERT_BRAND_CARD_PATH,
    INLINE_BRAND_ASSETS,
    PROJECT_DESCRIPTION,
    SYSTEM_EXPANSION,
    SYSTEM_NAME,
    SYSTEM_TAGLINE,
    branded_subject,
    html_email_shell,
    plain_header,
    wrap_plain_message,
)
from sisclima.core.config import env, as_bool, env_name_used
from sisclima.core.http_client import http_post
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _telegram_ssl_error(exc: BaseException) -> bool:
    msg = str(exc).upper()
    return "CERTIFICATE" in msg or "SSL" in msg or "CERT_VERIFY" in msg


def _telegram_post(
    path: str,
    *,
    data: dict | None = None,
    files: dict | None = None,
    timeout: int | float = 30,
) -> requests.Response:
    """POST à API Telegram com SSL institucional e fallback em proxy SES."""
    token = env("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/{path.lstrip('/')}"
    try:
        return http_post(
            url,
            data=data,
            files=files,
            timeout=timeout,
            ssl_env_key="TELEGRAM_SSL_VERIFY",
        )
    except Exception as exc:
        if not _telegram_ssl_error(exc):
            raise
        log.warning(
            "Telegram SSL verify falhou (%s) — retry com TELEGRAM_SSL_VERIFY=false (proxy SES).",
            type(exc).__name__,
        )
        return http_post(
            url,
            data=data,
            files=files,
            timeout=timeout,
            verify=False,
        )


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


def _smtp_use_ssl(host: str | None = None, port: int | None = None) -> bool:
    """SSL implícito (465 / Titan), como no Sentinela. STARTTLS só nas demais portas."""
    resolved_host = (host if host is not None else env("SMTP_HOST", "") or "").strip()
    try:
        resolved_port = int(port if port is not None else (env("SMTP_PORT", "587") or 587))
    except (TypeError, ValueError):
        resolved_port = 587
    raw = env("SMTP_SSL")
    if raw is not None and str(raw).strip() != "":
        return as_bool(raw, False)
    return resolved_port == 465 or "titan" in resolved_host.lower()


def _smtp_connect(host: str, port: int, *, use_ssl: bool, timeout: int = 30):
    """Abre SMTP com SSL/STARTTLS forçando IPv4 (IPv6 estoura timeout nesta rede)."""

    class _SMTP_SSL_V4(smtplib.SMTP_SSL):
        def _get_socket(self, h, p, timeout):  # noqa: ANN001
            infos = socket.getaddrinfo(h, p, socket.AF_INET, socket.SOCK_STREAM)
            sock = socket.create_connection(infos[0][4], timeout)
            ctx = self.context or ssl.create_default_context()
            return ctx.wrap_socket(sock, server_hostname=h)

    class _SMTP_V4(smtplib.SMTP):
        def _get_socket(self, h, p, timeout):  # noqa: ANN001
            infos = socket.getaddrinfo(h, p, socket.AF_INET, socket.SOCK_STREAM)
            return socket.create_connection(infos[0][4], timeout)

    if use_ssl or int(port) == 465:
        server = _SMTP_SSL_V4(host, int(port), timeout=timeout)
        server.ehlo()
        return server
    server = _SMTP_V4(host, int(port), timeout=timeout)
    server.ehlo()
    try:
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    except Exception:
        pass
    return server


def _smtp_targets() -> list[tuple[str, int, bool, str | None, str | None]]:
    """Host SMTP principal e fallback opcional (SMTP_FALLBACK_*), como no Sentinela.

    Retorna (host, port, use_ssl, user_override, password_override).
    Overrides None = usar SMTP_USER / SMTP_PASSWORD.
    """
    host = (env("SMTP_HOST", "smtp.gmail.com") or "smtp.gmail.com").strip()
    try:
        port = int(env("SMTP_PORT", "587") or 587)
    except (TypeError, ValueError):
        port = 587
    targets: list[tuple[str, int, bool, str | None, str | None]] = [
        (host, port, _smtp_use_ssl(host, port), None, None)
    ]
    fallback_host = (env("SMTP_FALLBACK_HOST") or "").strip()
    if fallback_host and fallback_host.lower() != host.lower():
        try:
            fallback_port = int(env("SMTP_FALLBACK_PORT", "465") or 465)
        except (TypeError, ValueError):
            fallback_port = 465
        targets.append(
            (
                fallback_host,
                fallback_port,
                _smtp_use_ssl(fallback_host, fallback_port),
                env("SMTP_FALLBACK_USER") or None,
                env("SMTP_FALLBACK_PASSWORD") or None,
            )
        )
    return targets


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
    inline_images: dict[str, Path] | None = None,
    attachments: list[Path] | tuple[Path, ...] | None = None,
) -> bool:
    if not _email_enabled(to):
        return False
    recipients = _split_recipients(to or env('ALERT_EMAIL_TO'))
    if not recipients:
        return False
    msg = EmailMessage()
    msg['Subject'] = branded_subject(subject)
    envelope_from = env('SMTP_FROM') or env('SMTP_USER') or 'araras@ses.mt.gov.br'
    msg['From'] = envelope_from
    # Privacidade: múltiplos destinatários não se veem (Bcc). Um único vai em To.
    if len(recipients) == 1:
        msg['To'] = recipients[0]
    else:
        msg['To'] = env('ALERT_EMAIL_ENVELOPE_TO') or envelope_from
        msg['Bcc'] = ', '.join(recipients)
    branded_plain = wrap_plain_message(body)
    msg.set_content(branded_plain)
    rendered_body = html_body or (
        '<pre style="white-space:pre-wrap;font:14px/1.55 Segoe UI,Arial,sans-serif">'
        f'{html.escape(str(body or ""))}</pre>'
    )
    msg.add_alternative(html_email_shell(rendered_body), subtype='html')
    _attach_inline_brand_assets(msg)
    if inline_images:
        payload = msg.get_payload()
        html_part = payload[-1] if isinstance(payload, list) and payload else None
        if html_part is not None:
            for cid, path in inline_images.items():
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
    for raw in attachments or []:
        asset = Path(raw)
        if not asset.is_file():
            log.warning("Anexo inexistente — ignorado: %s", asset)
            continue
        mime, _ = mimetypes.guess_type(asset.name)
        maintype, subtype = (mime or "application/octet-stream").split("/", 1)
        msg.add_attachment(
            asset.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=asset.name,
        )
    user = env('SMTP_USER')
    password = env('SMTP_PASSWORD')
    passwords: list[str] = []
    for cand in (password, (password or '').replace(' ', ''), (password or '').strip()):
        if cand and cand not in passwords:
            passwords.append(cand)
    last_error: Exception | None = None
    for host, port, use_ssl, user_ov, pass_ov in _smtp_targets():
        login_user = (user_ov or user or "").strip() or None
        secrets = list(passwords)
        if pass_ov:
            secrets = [pass_ov] + [p for p in secrets if p != pass_ov]
        for secret in secrets or [None]:
            try:
                with _smtp_connect(host, port, use_ssl=use_ssl, timeout=30) as s:
                    if login_user and secret:
                        s.login(login_user, secret)
                    s.send_message(msg)
                log.info(
                    "E-mail enviado via %s:%s ssl=%s · user=%s · %d destinatário(s)",
                    host,
                    port,
                    use_ssl,
                    login_user or "(anon)",
                    len(recipients),
                )
                return True
            except Exception as e:
                last_error = e
                log.warning('Falha e-mail %s:%s ssl=%s: %s', host, port, use_ssl, e)
    if last_error is not None:
        log.warning('Falha e-mail: %s', last_error)
    return False


def send_telegram_brand_card(*, chat_id: str | None = None) -> bool:
    """Envia a marca como cartão visual antes do texto do boletim."""
    if not _telegram_enabled(chat_id):
        return False
    destination = chat_id or env('TELEGRAM_CHAT_ID')
    if not destination or not ALERT_BRAND_CARD_PATH.exists():
        return False
    try:
        # Ler bytes de uma vez — retry SSL não pode reusar file pointer no EOF.
        photo_bytes = ALERT_BRAND_CARD_PATH.read_bytes()
        if not photo_bytes:
            log.warning("Cartão de marca Telegram vazio: %s", ALERT_BRAND_CARD_PATH)
            return False
        r = _telegram_post(
            "sendPhoto",
            data={
                'chat_id': destination,
                'caption': (
                    f'{SYSTEM_NAME} — {SYSTEM_EXPANSION}\n'
                    f'{SYSTEM_TAGLINE}\n{PROJECT_DESCRIPTION}\n'
                    'SES-MT · CIEVS-MT · Rede CIEVS · Vigidesastres'
                ),
            },
            files={'photo': (ALERT_BRAND_CARD_PATH.name, photo_bytes, 'image/png')},
            timeout=45,
        )
        if not r.ok:
            log.warning('Telegram sendPhoto (marca) HTTP %s: %s', r.status_code, (r.text or '')[:240])
        return r.ok
    except Exception as e:
        log.warning('Falha ao enviar cartão de marca no Telegram: %s', type(e).__name__)
        return False


def send_telegram_photo(path: Path, caption: str = "", *, chat_id: str | None = None) -> bool:
    """Envia uma imagem (mapa de risco) ao chat do Telegram."""
    if not _telegram_enabled(chat_id):
        return False
    destination = chat_id or env('TELEGRAM_CHAT_ID')
    asset = Path(path)
    if not destination or not asset.is_file():
        return False
    try:
        photo_bytes = asset.read_bytes()
        if not photo_bytes:
            log.warning("Foto Telegram vazia: %s", asset)
            return False
        r = _telegram_post(
            "sendPhoto",
            data={'chat_id': destination, 'caption': (caption or '')[:1024]},
            files={'photo': (asset.name, photo_bytes, 'image/png')},
            timeout=45,
        )
        if not r.ok:
            log.warning('Telegram sendPhoto HTTP %s: %s', r.status_code, (r.text or '')[:240])
        return r.ok
    except Exception as e:
        log.warning('Falha ao enviar foto no Telegram: %s', type(e).__name__)
        return False


def send_telegram(text: str, *, chat_id: str | None = None, with_brand: bool = True) -> bool:
    if not _telegram_enabled(chat_id):
        return False
    destination = chat_id or env('TELEGRAM_CHAT_ID')
    if not destination:
        return False
    if with_brand:
        send_telegram_brand_card(chat_id=destination)
    message = str(text or '').strip()
    if PROJECT_DESCRIPTION not in message:
        message = f'{plain_header()}\n\n{message}'
    # Limite da API Telegram
    if len(message) > 4096:
        message = message[:4080] + "\n…"
    try:
        r = _telegram_post(
            "sendMessage",
            data={'chat_id': destination, 'text': message},
            timeout=30,
        )
        if not r.ok:
            log.warning('Telegram sendMessage HTTP %s: %s', r.status_code, (r.text or '')[:240])
        return r.ok
    except Exception as e:
        log.warning('Falha Telegram: %s', type(e).__name__)
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
            f'{plain_header()}\n\n{branded}\n\n{message}',
            payload={'subject': branded, **payload},
        ),
        'webhook': send_webhook({
            'system_name': SYSTEM_NAME,
            'system_expansion': SYSTEM_EXPANSION,
            'project_description': PROJECT_DESCRIPTION,
            'subject': branded,
            'message': message,
            **payload,
        })
    }
    log.info('Resultado envio alertas: %s', results)
    return results
