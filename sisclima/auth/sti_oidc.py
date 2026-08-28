# -*- coding: utf-8 -*-
"""Login institucional STI (OpenID Connect).

Sem STI_OIDC_ENABLED=true o painel segue com e-mail + senha.
A STI precisa informar issuer, client_id e redirect. Domínio padrão: saude.mt.gov.br.
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DOMINIO_PADRAO = "saude.mt.gov.br"


def sti_ativado() -> bool:
    return as_bool(env("STI_OIDC_ENABLED"), False)


def sti_config() -> dict[str, str]:
    issuer = (env("STI_OIDC_ISSUER") or "").rstrip("/")
    return {
        "issuer": issuer,
        "client_id": env("STI_OIDC_CLIENT_ID") or "",
        "client_secret": env("STI_OIDC_CLIENT_SECRET") or "",
        "redirect_uri": env("STI_OIDC_REDIRECT_URI") or "",
        "authorize_url": env("STI_OIDC_AUTHORIZE_URL") or (f"{issuer}/authorize" if issuer else ""),
        "token_url": env("STI_OIDC_TOKEN_URL") or (f"{issuer}/token" if issuer else ""),
        "userinfo_url": env("STI_OIDC_USERINFO_URL") or (f"{issuer}/userinfo" if issuer else ""),
        "scope": env("STI_OIDC_SCOPE") or "openid email profile",
        "email_domain": (env("STI_EMAIL_DOMAIN") or DOMINIO_PADRAO).lower(),
    }


def sti_pronto() -> bool:
    cfg = sti_config()
    return bool(sti_ativado() and cfg["client_id"] and cfg["authorize_url"] and cfg["redirect_uri"])


def url_autorizacao(*, state: str, nonce: str) -> str:
    cfg = sti_config()
    q = urlencode(
        {
            "response_type": "code",
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "scope": cfg["scope"],
            "state": state,
            "nonce": nonce,
        }
    )
    return f"{cfg['authorize_url']}?{q}"


def novo_state() -> tuple[str, str]:
    return secrets.token_urlsafe(24), secrets.token_urlsafe(24)


def email_institucional(email: str) -> bool:
    cfg = sti_config()
    e = str(email or "").strip().lower()
    return e.endswith("@" + cfg["email_domain"])


def _trocar_code(code: str) -> dict[str, Any]:
    import urllib.request

    cfg = sti_config()
    body = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["redirect_uri"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        }
    ).encode()
    req = urllib.request.Request(
        cfg["token_url"],
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _userinfo(access_token: str) -> dict[str, Any]:
    import urllib.request

    cfg = sti_config()
    if not cfg["userinfo_url"]:
        return {}
    req = urllib.request.Request(
        cfg["userinfo_url"],
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def concluir_login_sti(code: str) -> tuple[dict[str, Any] | None, str]:
    """Troca o code OIDC por usuário ARARAS (nível ses, pendente de perfil do Plano)."""
    if not sti_pronto():
        return None, "Login STI não configurado (STI_OIDC_ENABLED / issuer / client_id)."
    try:
        token = _trocar_code(code)
        access = str(token.get("access_token") or "")
        info = _userinfo(access) if access else {}
        email = str(info.get("email") or info.get("preferred_username") or "").strip().lower()
        nome = str(info.get("name") or info.get("given_name") or email.split("@")[0])
        if not email or not email_institucional(email):
            return None, f"E-mail não pertence ao domínio institucional @{sti_config()['email_domain']}."
        from sisclima.auth.access import get_user_by_email, register_user, set_user_status

        row = get_user_by_email(email)
        if not row:
            import secrets as _s

            ok, msg = register_user(
                email=email,
                nome=nome,
                password=_s.token_urlsafe(24),
                instituicao="SES-MT / STI",
                nivel_solicitado="ses",
            )
            if not ok and "já" not in msg.casefold():
                return None, msg
            set_user_status(email, status="ativo", nivel="ses", aprovado_por="sti_oidc")
            row = get_user_by_email(email)
        if not row:
            return None, "Não foi possível materializar o usuário institucional."
        row = dict(row)
        row["auth_via"] = "sti_oidc"
        row["auth_em"] = int(time.time())
        return row, "ok"
    except Exception as exc:  # noqa: BLE001
        log.warning("OIDC STI falhou: %s", exc)
        return None, "Falha na autenticação institucional. Tente senha local ou contacte a STI."
