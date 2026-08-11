# -*- coding: utf-8 -*-
"""Cliente HTTP auditável para a rede SES.

Política: sem ofuscação, sem scrapers stealth, User-Agent institucional
identificável. Preferir APIs oficiais e SSL verificado por padrão.
"""
from __future__ import annotations

from typing import Any

import requests
import urllib3

from sisclima.core.config import as_bool, env

# Identidade explícita — TI/SES consegue auditar o tráfego.
USER_AGENT = "ARARAS-Clima-Saude-MT/1.0 (+CIEVS-MT; codigo-legivel; sem-stealth)"
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
}


def ssl_verify(source_key: str | None = None, default: bool = True) -> bool:
    """Resolve verify SSL (padrão True). source_key ex.: OPENMETEO_SSL_VERIFY."""
    if source_key:
        raw = env(source_key, env("ALERT_SSL_VERIFY", "true" if default else "false"))
    else:
        raw = env("ALERT_SSL_VERIFY", "true" if default else "false")
    return as_bool(raw, default)


def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | float = 30,
    verify: bool | None = None,
    ssl_env_key: str | None = None,
) -> requests.Response:
    """GET com headers institucionais. Sem bypass de WAF/CAPTCHA."""
    if verify is None:
        verify = ssl_verify(ssl_env_key, True)
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    return requests.get(url, params=params, headers=merged, timeout=timeout, verify=verify)


def http_post(
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int | float = 30,
    verify: bool | None = None,
) -> requests.Response:
    """POST com User-Agent institucional (alertas/LLM oficiais)."""
    if verify is None:
        verify = ssl_verify(None, True)
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    return requests.post(url, json=json, data=data, headers=merged, timeout=timeout, verify=verify)
