# -*- coding: utf-8 -*-
"""Testes do descobridor de contas Meta (sem rede real)."""
from __future__ import annotations

import pytest

from sisclima.alerts import meta_discover
from tests.conftest import RespostaFalsa


class GraphFalso:
    def __init__(self, respostas: dict[str, RespostaFalsa]):
        self.respostas = respostas
        self.urls: list[str] = []

    def get(self, url: str, params=None, headers=None, timeout=None):  # noqa: ARG002
        self.urls.append(url)
        for chave, resposta in self.respostas.items():
            if chave in url:
                return resposta
        return RespostaFalsa(404, {'error': {'message': 'not found'}})


@pytest.fixture
def graph(monkeypatch):
    def _instalar(respostas: dict[str, RespostaFalsa]) -> GraphFalso:
        falso = GraphFalso(respostas)
        monkeypatch.setattr(meta_discover.requests, 'get', falso.get)
        return falso

    return _instalar


def test_descobrir_sem_token():
    resultado = meta_discover.descobrir('')
    assert resultado.ok is False
    assert 'Token vazio' in resultado.erros[0]


def test_descobrir_token_invalido(graph):
    graph({
        'debug_token': RespostaFalsa(200, {'data': {'is_valid': False, 'error': {'message': 'expired'}}}),
    })
    resultado = meta_discover.descobrir('token-invalido')
    assert resultado.token_valido is False
    assert resultado.ok is False


def test_descobrir_encontra_numeros_via_negocios(graph):
    graph({
        'debug_token': RespostaFalsa(200, {
            'data': {
                'is_valid': True,
                'scopes': ['whatsapp_business_management', 'whatsapp_business_messaging', 'business_management'],
            },
        }),
        'me/businesses': RespostaFalsa(200, {
            'data': [{
                'id': 'biz1',
                'name': 'SES MT',
                'owned_whatsapp_business_accounts': {
                    'data': [{
                        'id': 'waba123',
                        'name': 'VIGIA',
                        'phone_numbers': {'data': []},
                    }],
                },
            }],
        }),
        'waba123/phone_numbers': RespostaFalsa(200, {
            'data': [{
                'id': '999888777666555',
                'display_phone_number': '+1 555 025 3483',
                'verified_name': 'Test Number',
            }],
        }),
    })
    resultado = meta_discover.descobrir('EAA-token-teste')

    assert resultado.ok is True
    assert resultado.phone_number_id_sugerido == '999888777666555'
    assert resultado.numeros[0].display == '+1 555 025 3483'
    assert 'waba123' in resultado.waba_ids


def test_descobrir_avisa_quando_waba_sem_numeros(graph):
    graph({
        'debug_token': RespostaFalsa(200, {'data': {'is_valid': True, 'scopes': []}}),
        'me/businesses': RespostaFalsa(200, {
            'data': [{
                'id': 'biz1',
                'name': 'Teste',
                'owned_whatsapp_business_accounts': {'data': [{'id': 'waba_vazia', 'name': 'Vazia'}]},
            }],
        }),
        'waba_vazia/phone_numbers': RespostaFalsa(200, {'data': []}),
        '/me': RespostaFalsa(200, {'id': 'user1', 'name': 'Menandes'}),
    })
    resultado = meta_discover.descobrir('EAA-token')

    assert resultado.ok is False
    assert any('Começar a usar a API' in aviso for aviso in resultado.avisos)


def test_resumo_texto_lista_ids(graph):
    graph({
        'debug_token': RespostaFalsa(200, {'data': {'is_valid': True, 'scopes': []}}),
        'me/businesses': RespostaFalsa(200, {
            'data': [{
                'id': 'b1',
                'owned_whatsapp_business_accounts': {
                    'data': [{'id': 'w1', 'phone_numbers': {'data': [{'id': 'pid1', 'display_phone_number': '+55 65'}]}}],
                },
            }],
        }),
        'w1/phone_numbers': RespostaFalsa(200, {'data': []}),
    })
    texto = meta_discover.resumo_texto(meta_discover.descobrir('tok'))
    assert 'pid1' in texto
    assert 'WHATSAPP_PHONE_NUMBER_ID=pid1' in texto
