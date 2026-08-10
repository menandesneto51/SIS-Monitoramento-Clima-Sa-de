# -*- coding: utf-8 -*-
"""Fixtures compartilhadas: isolam o ambiente das variáveis de WhatsApp da máquina."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.core.config import ENV_ALIASES  # noqa: E402

PREFIXOS_WHATSAPP = ('WHATSAPP', 'EVOLUTION', 'CALLMEBOT', 'ALERT_WHATSAPP')

VARIAVEIS_WHATSAPP = sorted({
    nome
    for chave, aliases in ENV_ALIASES.items()
    if chave.startswith(PREFIXOS_WHATSAPP)
    for nome in aliases
} | {'USE_WHATSAPP', 'USAR_WHATSAPP'})


@pytest.fixture(autouse=True)
def ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove qualquer configuração de WhatsApp herdada do ambiente real."""
    for nome in VARIAVEIS_WHATSAPP:
        monkeypatch.delenv(nome, raising=False)


class RespostaFalsa:
    """Substituto mínimo de ``requests.Response`` para os testes."""

    def __init__(self, status_code: int = 200, json_data: dict | None = None, text: str = ''):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text or json_data is None else ''

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        if self._json is None:
            raise ValueError('sem corpo JSON')
        return self._json


@pytest.fixture
def resposta_falsa():
    return RespostaFalsa
