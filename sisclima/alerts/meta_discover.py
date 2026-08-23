# -*- coding: utf-8 -*-
"""Descobre contas WhatsApp Business e Phone number IDs via Graph API.

Útil quando a interface da Meta não mostra a tela API Setup. Basta um token com
permissões ``whatsapp_business_management`` e ``business_management``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from sisclima.alerts import whatsapp
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

TIMEOUT = 30


@dataclass
class NumeroMeta:
    phone_number_id: str
    display: str = ''
    verified_name: str = ''
    waba_id: str = ''
    waba_name: str = ''
    business_id: str = ''
    business_name: str = ''


@dataclass
class ResultadoDescoberta:
    ok: bool
    token_valido: bool = False
    numeros: list[NumeroMeta] = field(default_factory=list)
    waba_ids: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    resposta_bruta: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def phone_number_id_sugerido(self) -> str | None:
        return self.numeros[0].phone_number_id if self.numeros else None


def _get(url: str, token: str, params: dict | None = None) -> tuple[int, dict | list | str]:
    try:
        resposta = requests.get(
            url,
            params=params,
            headers={'Authorization': f'Bearer {token}'},
            timeout=TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)
    try:
        dados = resposta.json()
    except ValueError:
        dados = resposta.text[:500]
    return resposta.status_code, dados


def _extrair_numeros_waba(
    waba_id: str,
    waba_name: str,
    token: str,
    business_id: str = '',
    business_name: str = '',
) -> tuple[list[NumeroMeta], list[str]]:
    versao = whatsapp.VERSAO_API_META_PADRAO
    status, dados = _get(
        f'https://graph.facebook.com/{versao}/{waba_id}/phone_numbers',
        token,
        {'fields': 'id,display_phone_number,verified_name,code_verification_status,quality_rating'},
    )
    avisos: list[str] = []
    numeros: list[NumeroMeta] = []
    if status != 200 or not isinstance(dados, dict):
        avisos.append(f'Não foi possível listar números da WABA {waba_id}: HTTP {status}')
        return numeros, avisos

    for item in dados.get('data') or []:
        if not isinstance(item, dict) or not item.get('id'):
            continue
        numeros.append(
            NumeroMeta(
                phone_number_id=str(item['id']),
                display=str(item.get('display_phone_number') or ''),
                verified_name=str(item.get('verified_name') or ''),
                waba_id=waba_id,
                waba_name=waba_name,
                business_id=business_id,
                business_name=business_name,
            )
        )
    if not numeros:
        avisos.append(
            f'WABA {waba_id} ({waba_name or "sem nome"}) não tem números. '
            'Clique em "Começar a usar a API" no app Meta ou adicione um número no WhatsApp Manager.'
        )
    return numeros, avisos


def descobrir(token: str) -> ResultadoDescoberta:
    """Lista WABAs e Phone number IDs acessíveis com o token informado."""
    token = (token or '').strip()
    resultado = ResultadoDescoberta(ok=False, token_valido=False)

    if not token:
        resultado.erros.append('Token vazio. Gere um em developers.facebook.com/tools/explorer')
        return resultado

    versao = whatsapp.VERSAO_API_META_PADRAO

    # Valida token
    status_debug, debug = _get(
        'https://graph.facebook.com/debug_token',
        token,
        {'input_token': token},
    )
    if status_debug == 200 and isinstance(debug, dict):
        info = (debug.get('data') or {})
        resultado.token_valido = bool(info.get('is_valid'))
        if not resultado.token_valido:
            resultado.erros.append(f'Token inválido: {info.get("error", {}).get("message", "desconhecido")}')
            return resultado
        escopos = set(info.get('scopes') or [])
        faltam = {'whatsapp_business_management', 'whatsapp_business_messaging'} - escopos
        if faltam:
            resultado.avisos.append(
                'Permissões recomendadas ausentes no token: '
                + ', '.join(sorted(faltam))
                + '. Gere novo token no Explorador da Graph API.'
            )
    else:
        resultado.avisos.append('Não foi possível validar o token (debug_token). Tentando listar contas mesmo assim.')

    vistos_waba: set[str] = set()
    vistos_numero: set[str] = set()

    def registrar_waba(waba_id: str, waba_name: str = '', business_id: str = '', business_name: str = '') -> None:
        if not waba_id or waba_id in vistos_waba:
            return
        vistos_waba.add(waba_id)
        resultado.waba_ids.append(waba_id)
        nums, avisos = _extrair_numeros_waba(waba_id, waba_name, token, business_id, business_name)
        resultado.avisos.extend(avisos)
        for numero in nums:
            if numero.phone_number_id not in vistos_numero:
                vistos_numero.add(numero.phone_number_id)
                resultado.numeros.append(numero)

    # Caminho 1: negócios do usuário → WABAs
    status, dados = _get(
        f'https://graph.facebook.com/{versao}/me/businesses',
        token,
        {
            'fields': (
                'id,name,owned_whatsapp_business_accounts{id,name,'
                'phone_numbers{id,display_phone_number,verified_name}}'
            ),
        },
    )
    resultado.resposta_bruta['me/businesses'] = dados

    if status == 200 and isinstance(dados, dict):
        for negocio in dados.get('data') or []:
            if not isinstance(negocio, dict):
                continue
            bid = str(negocio.get('id') or '')
            bname = str(negocio.get('name') or '')
            wabas = (negocio.get('owned_whatsapp_business_accounts') or {}).get('data') or []
            for waba in wabas:
                if not isinstance(waba, dict):
                    continue
                wid = str(waba.get('id') or '')
                wname = str(waba.get('name') or '')
                registrar_waba(wid, wname, bid, bname)
                # números aninhados (nem sempre vêm completos)
                for item in (waba.get('phone_numbers') or {}).get('data') or []:
                    if isinstance(item, dict) and item.get('id'):
                        pid = str(item['id'])
                        if pid not in vistos_numero:
                            vistos_numero.add(pid)
                            resultado.numeros.append(
                                NumeroMeta(
                                    phone_number_id=pid,
                                    display=str(item.get('display_phone_number') or ''),
                                    verified_name=str(item.get('verified_name') or ''),
                                    waba_id=wid,
                                    waba_name=wname,
                                    business_id=bid,
                                    business_name=bname,
                                )
                            )
    elif status == 403:
        resultado.avisos.append('Token sem acesso a me/businesses. Adicione permissão business_management.')
    elif status not in (0, 200):
        resultado.avisos.append(f'me/businesses retornou HTTP {status}')

    # Caminho 2: WABAs compartilhadas com o app (quando me/businesses falha)
    if not resultado.numeros:
        status2, dados2 = _get(
            f'https://graph.facebook.com/{versao}/me',
            token,
            {'fields': 'id,name'},
        )
        resultado.resposta_bruta['me'] = dados2
        if status2 == 200:
            resultado.avisos.append(
                'Nenhum número encontrado via negócios. Abra o app Meta → Painel → card WhatsApp → '
                '"Começar a usar a API" para criar a conta de teste, depois rode descobrir novamente.'
            )
        else:
            resultado.erros.append(f'Não foi possível consultar a Graph API (HTTP {status2}).')

    resultado.ok = bool(resultado.numeros)
    if not resultado.ok and not resultado.erros:
        resultado.erros.append(
            'Nenhum Phone number ID encontrado. Siga docs/META_ONDE_CLICAR.md → Caminho A ou C.'
        )
    return resultado


def resumo_texto(resultado: ResultadoDescoberta) -> str:
    linhas: list[str] = []
    linhas.append(f'Token válido: {"sim" if resultado.token_valido else "não confirmado"}')
    linhas.append(f'Números encontrados: {len(resultado.numeros)}')
    for idx, numero in enumerate(resultado.numeros, 1):
        linhas.append(
            f'  {idx}. Phone number ID: {numero.phone_number_id}'
            f' | {numero.display or "(sem display)"}'
            f' | WABA: {numero.waba_id}'
        )
    if resultado.waba_ids:
        linhas.append(f'WABA IDs: {", ".join(resultado.waba_ids)}')
    for aviso in resultado.avisos:
        linhas.append(f'Aviso: {aviso}')
    for erro in resultado.erros:
        linhas.append(f'Erro: {erro}')
    if resultado.phone_number_id_sugerido:
        linhas.append('')
        linhas.append('Sugestão para .env:')
        linhas.append(f'WHATSAPP_PHONE_NUMBER_ID={resultado.phone_number_id_sugerido}')
    return '\n'.join(linhas)
