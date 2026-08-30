# -*- coding: utf-8 -*-
"""Cliente HTTP auditável para a rede SES.

Política: sem ofuscação, sem scrapers stealth, User-Agent institucional
identificável. Preferir APIs oficiais e SSL verificado por padrão.
"""
from __future__ import annotations

import time
from typing import Any

import requests
import urllib3

from sisclima.core.config import as_bool, env

RETRY_STATUS = {429, 500, 502, 503, 504}

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


def _retry_count() -> int:
    try:
        return max(0, int(env("HTTP_RETRY", "3") or 3))
    except (TypeError, ValueError):
        return 3


def _retry_wait(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return min(30.0, float(raw))
            except ValueError:
                pass
    return min(30.0, 1.5 * (2 ** attempt))


def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | float = 30,
    verify: bool | None = None,
    ssl_env_key: str | None = None,
    retries: int | None = None,
) -> requests.Response:
    """GET com headers institucionais. Sem bypass de WAF/CAPTCHA.

    Repete 429/5xx e falha de rede (Open-Meteo 503, proxy SES).
    """
    if verify is None:
        verify = ssl_verify(ssl_env_key, True)
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    attempts = _retry_count() if retries is None else max(0, int(retries))
    last_exc: Exception | None = None
    last_response: requests.Response | None = None
    for attempt in range(attempts + 1):
        try:
            last_response = requests.get(
                url, params=params, headers=merged, timeout=timeout, verify=verify
            )
        except (requests.RequestException, OSError) as exc:
            last_exc = exc
            if attempt >= attempts:
                raise
            time.sleep(_retry_wait(None, attempt))
            continue
        if last_response.status_code not in RETRY_STATUS or attempt >= attempts:
            return last_response
        time.sleep(_retry_wait(last_response, attempt))
    if last_response is not None:
        return last_response
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_get sem resposta")


def http_post(
    url: str,
    *,
    json: Any = None,
    data: Any = None,
    files: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int | float = 30,
    verify: bool | None = None,
    ssl_env_key: str | None = None,
) -> requests.Response:
    """POST com User-Agent institucional (alertas/LLM oficiais)."""
    if verify is None:
        verify = ssl_verify(ssl_env_key, True)
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    return requests.post(
        url,
        json=json,
        data=data,
        files=files,
        headers=merged,
        timeout=timeout,
        verify=verify,
    )
