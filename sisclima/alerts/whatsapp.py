# -*- coding: utf-8 -*-
"""Canal de WhatsApp para os alertas do SIS Clima-Saúde / VIGIA.

Reúne apenas provedores que operam sem custo de licença:

- ``meta_cloud``: WhatsApp Cloud API oficial da Meta (número de teste gratuito,
  mensagens de serviço e templates utilitários dentro da janela de 24h sem custo).
- ``evolution``: Evolution API v2 auto-hospedada (open source, não oficial).
- ``callmebot``: CallMeBot, gratuito e limitado a números que autorizaram o robô.
- ``webhook``: ponte genérica (n8n, Make, Zapier, Apps Script) que recebe o JSON
  do alerta e faz o envio final.

A escolha e as credenciais vêm de variáveis de ambiente. Use
``sisclima.alerts.whatsapp_agent`` para diagnosticar o que ainda falta configurar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote

import requests

from sisclima.core.config import SETTINGS, as_bool, env, env_name_used
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

TIMEOUT_SEGUNDOS = 30

PROVEDORES: tuple[str, ...] = ('meta_cloud', 'evolution', 'callmebot', 'webhook')

# Ordem usada quando WHATSAPP_PROVIDER=auto: oficial primeiro, ponte genérica por último.
ORDEM_AUTO: tuple[str, ...] = ('meta_cloud', 'evolution', 'callmebot', 'webhook')

VARIAVEIS_OBRIGATORIAS: dict[str, tuple[str, ...]] = {
    'meta_cloud': ('WHATSAPP_PHONE_NUMBER_ID', 'WHATSAPP_TOKEN', 'WHATSAPP_TO'),
    'evolution': ('EVOLUTION_API_URL', 'EVOLUTION_API_KEY', 'EVOLUTION_INSTANCE', 'WHATSAPP_TO'),
    'callmebot': ('CALLMEBOT_APIKEY', 'CALLMEBOT_PHONE'),
    'webhook': ('WHATSAPP_WEBHOOK_URL',),
}

VARIAVEIS_OPCIONAIS: dict[str, tuple[str, ...]] = {
    'meta_cloud': ('WHATSAPP_API_VERSION', 'WHATSAPP_TEMPLATE_NAME', 'WHATSAPP_TEMPLATE_LANG', 'WHATSAPP_DDI_PADRAO'),
    'evolution': ('WHATSAPP_DDI_PADRAO',),
    'callmebot': ('WHATSAPP_DDI_PADRAO',),
    'webhook': ('WHATSAPP_TO', 'WHATSAPP_WEBHOOK_TOKEN'),
}

VERSAO_API_META_PADRAO = 'v23.0'
DDI_PADRAO = '55'
LIMITE_CARACTERES_PADRAO = 4000

# Parâmetro de template da Meta não aceita quebra de linha, tabulação
# nem mais de quatro espaços seguidos.
_ESPACOS_SEGUIDOS = re.compile(r'\s{4,}')


@dataclass
class ResultadoEnvio:
    """Resultado de uma tentativa de envio para um destinatário."""

    ok: bool
    provedor: str
    destino: str = ''
    detalhe: str = ''
    status_http: int | None = None
    resposta: dict | str | None = field(default=None, repr=False)

    def __bool__(self) -> bool:
        return self.ok


def _conf() -> dict:
    return (SETTINGS.get('alertas', {}) or {}).get('whatsapp', {}) or {}


def ddi_padrao() -> str:
    return str(env('WHATSAPP_DDI_PADRAO', str(_conf().get('ddi_padrao', DDI_PADRAO))) or DDI_PADRAO).strip()


def limite_caracteres() -> int:
    try:
        return int(_conf().get('limite_caracteres', LIMITE_CARACTERES_PADRAO))
    except (TypeError, ValueError):
        return LIMITE_CARACTERES_PADRAO


def normalizar_numero(numero: str, ddi: str | None = None) -> str:
    """Converte um telefone escrito de qualquer jeito em dígitos no formato E.164 sem '+'.

    Números brasileiros com 10 ou 11 dígitos (DDD + telefone) recebem o DDI configurado.
    """
    ddi = (ddi or ddi_padrao()).lstrip('+')
    digitos = re.sub(r'\D', '', str(numero or ''))
    if not digitos:
        return ''
    if len(digitos) in (10, 11) and not digitos.startswith(ddi):
        digitos = f'{ddi}{digitos}'
    return digitos


def destinatarios(valor: str | list[str] | None = None) -> list[str]:
    """Lista de números normalizados a partir de WHATSAPP_TO (ou de um valor explícito)."""
    if valor is None:
        valor = env('WHATSAPP_TO') or ''
    if isinstance(valor, str):
        # Espaço não separa: números costumam ser escritos como "(65) 99999-8888".
        brutos = re.split(r'[,;|\n]+', valor)
    else:
        brutos = list(valor)
    numeros = [normalizar_numero(item) for item in brutos]
    unicos: list[str] = []
    for numero in numeros:
        if numero and numero not in unicos:
            unicos.append(numero)
    return unicos


def variaveis_faltantes(provedor: str) -> list[str]:
    """Variáveis obrigatórias do provedor que ainda não estão no ambiente."""
    return [nome for nome in VARIAVEIS_OBRIGATORIAS.get(provedor, ()) if not env(nome)]


def provedor_configurado(provedor: str) -> bool:
    return provedor in VARIAVEIS_OBRIGATORIAS and not variaveis_faltantes(provedor)


def provedores_configurados() -> list[str]:
    return [nome for nome in ORDEM_AUTO if provedor_configurado(nome)]


def provedor_ativo() -> str | None:
    """Provedor que será usado no envio, respeitando WHATSAPP_PROVIDER.

    Com ``auto`` (padrão), escolhe o primeiro provedor completamente configurado.
    """
    escolhido = (env('WHATSAPP_PROVIDER', 'auto') or 'auto').strip().lower()
    if escolhido in ('', 'auto'):
        configurados = provedores_configurados()
        return configurados[0] if configurados else None
    if escolhido not in PROVEDORES:
        log.warning('WHATSAPP_PROVIDER desconhecido: %s. Use um de %s.', escolhido, ', '.join(PROVEDORES))
        return None
    return escolhido


def whatsapp_habilitado() -> bool:
    """Canal ligado explicitamente ou por dedução, quando há provedor configurado."""
    if env_name_used('ALERT_WHATSAPP_ENABLED'):
        return as_bool(env('ALERT_WHATSAPP_ENABLED'), False)
    return bool(provedor_ativo() and provedor_configurado(provedor_ativo() or ''))


def _truncar(texto: str) -> str:
    limite = limite_caracteres()
    texto = str(texto or '')
    if len(texto) <= limite:
        return texto
    return texto[: limite - 3] + '...'


def _parametro_template(texto: str) -> str:
    """Adequa o texto às restrições de parâmetro de template da Meta."""
    achatado = str(texto or '').replace('\r', ' ').replace('\n', ' | ').replace('\t', ' ')
    achatado = _ESPACOS_SEGUIDOS.sub(' ', achatado).strip()
    return achatado[:1024]


def _resposta_json(resposta: requests.Response) -> dict | str:
    try:
        return resposta.json()
    except ValueError:
        return resposta.text[:500]


def _erro(provedor: str, destino: str, mensagem: str) -> ResultadoEnvio:
    log.warning('Falha WhatsApp (%s): %s', provedor, mensagem)
    return ResultadoEnvio(ok=False, provedor=provedor, destino=destino, detalhe=mensagem)


def _enviar_meta_cloud(texto: str, destino: str) -> ResultadoEnvio:
    phone_number_id = env('WHATSAPP_PHONE_NUMBER_ID')
    token = env('WHATSAPP_TOKEN')
    if not phone_number_id or not token:
        return _erro('meta_cloud', destino, 'WHATSAPP_PHONE_NUMBER_ID e WHATSAPP_TOKEN são obrigatórios.')
    versao = env('WHATSAPP_API_VERSION', VERSAO_API_META_PADRAO) or VERSAO_API_META_PADRAO
    template = env('WHATSAPP_TEMPLATE_NAME')

    if template:
        # Fora da janela de 24h a Meta só aceita template aprovado.
        corpo = {
            'messaging_product': 'whatsapp',
            'to': destino,
            'type': 'template',
            'template': {
                'name': template,
                'language': {'code': env('WHATSAPP_TEMPLATE_LANG', 'pt_BR') or 'pt_BR'},
                'components': [{
                    'type': 'body',
                    'parameters': [{'type': 'text', 'text': _parametro_template(texto)}],
                }],
            },
        }
    else:
        corpo = {
            'messaging_product': 'whatsapp',
            'to': destino,
            'type': 'text',
            'text': {'preview_url': False, 'body': _truncar(texto)},
        }

    url = f'https://graph.facebook.com/{versao}/{phone_number_id}/messages'
    try:
        resposta = requests.post(
            url,
            json=corpo,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except Exception as exc:  # noqa: BLE001 - falha de rede não deve derrubar o pipeline
        return _erro('meta_cloud', destino, f'erro de rede: {exc}')

    dados = _resposta_json(resposta)
    if resposta.ok:
        return ResultadoEnvio(True, 'meta_cloud', destino, 'mensagem aceita pela Cloud API', resposta.status_code, dados)
    detalhe = ''
    if isinstance(dados, dict):
        detalhe = str((dados.get('error') or {}).get('message') or '')
    return ResultadoEnvio(False, 'meta_cloud', destino, detalhe or f'HTTP {resposta.status_code}', resposta.status_code, dados)


def _enviar_evolution(texto: str, destino: str) -> ResultadoEnvio:
    base = (env('EVOLUTION_API_URL') or '').rstrip('/')
    chave = env('EVOLUTION_API_KEY')
    instancia = env('EVOLUTION_INSTANCE')
    if not base or not chave or not instancia:
        return _erro('evolution', destino, 'EVOLUTION_API_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE são obrigatórios.')

    url = f'{base}/message/sendText/{instancia}'
    cabecalhos = {'apikey': chave, 'Content-Type': 'application/json'}
    corpo_v2 = {'number': destino, 'text': _truncar(texto)}
    try:
        resposta = requests.post(url, json=corpo_v2, headers=cabecalhos, timeout=TIMEOUT_SEGUNDOS)
        if resposta.status_code == 400:
            # Instâncias na v1 esperam o texto aninhado em textMessage.
            corpo_v1 = {'number': destino, 'textMessage': {'text': _truncar(texto)}}
            resposta = requests.post(url, json=corpo_v1, headers=cabecalhos, timeout=TIMEOUT_SEGUNDOS)
    except Exception as exc:  # noqa: BLE001
        return _erro('evolution', destino, f'erro de rede: {exc}')

    dados = _resposta_json(resposta)
    if resposta.ok:
        return ResultadoEnvio(True, 'evolution', destino, 'mensagem enfileirada na instância', resposta.status_code, dados)
    return ResultadoEnvio(False, 'evolution', destino, f'HTTP {resposta.status_code}', resposta.status_code, dados)


def _enviar_callmebot(texto: str, destino: str) -> ResultadoEnvio:
    chave = env('CALLMEBOT_APIKEY')
    if not chave:
        return _erro('callmebot', destino, 'CALLMEBOT_APIKEY é obrigatório.')
    url = (
        'https://api.callmebot.com/whatsapp.php'
        f'?phone=%2B{destino}&text={quote(_truncar(texto))}&apikey={quote(chave)}'
    )
    try:
        resposta = requests.get(url, timeout=TIMEOUT_SEGUNDOS)
    except Exception as exc:  # noqa: BLE001
        return _erro('callmebot', destino, f'erro de rede: {exc}')

    corpo = (resposta.text or '')[:500]
    # O CallMeBot responde HTTP 200 mesmo em erro de chave, então o texto precisa ser inspecionado.
    falhou = any(marca in corpo.lower() for marca in ('apikey', 'error', 'not found', 'invalid'))
    if resposta.ok and not falhou:
        return ResultadoEnvio(True, 'callmebot', destino, 'mensagem enfileirada no CallMeBot', resposta.status_code, corpo)
    return ResultadoEnvio(False, 'callmebot', destino, corpo or f'HTTP {resposta.status_code}', resposta.status_code, corpo)


def _enviar_webhook(texto: str, destinos: list[str], extra: dict | None = None) -> ResultadoEnvio:
    url = env('WHATSAPP_WEBHOOK_URL')
    if not url:
        return _erro('webhook', '', 'WHATSAPP_WEBHOOK_URL é obrigatório.')
    corpo = {'canal': 'whatsapp', 'para': destinos, 'mensagem': _truncar(texto), **(extra or {})}
    cabecalhos = {'Content-Type': 'application/json'}
    token = env('WHATSAPP_WEBHOOK_TOKEN')
    if token:
        cabecalhos['Authorization'] = f'Bearer {token}'
    try:
        resposta = requests.post(url, json=corpo, headers=cabecalhos, timeout=TIMEOUT_SEGUNDOS)
    except Exception as exc:  # noqa: BLE001
        return _erro('webhook', ', '.join(destinos), f'erro de rede: {exc}')

    destino = ', '.join(destinos)
    if resposta.ok:
        return ResultadoEnvio(True, 'webhook', destino, 'payload entregue à ponte', resposta.status_code, _resposta_json(resposta))
    return ResultadoEnvio(False, 'webhook', destino, f'HTTP {resposta.status_code}', resposta.status_code, _resposta_json(resposta))


def enviar_whatsapp(
    texto: str,
    destinos: str | list[str] | None = None,
    provedor: str | None = None,
    extra: dict | None = None,
) -> list[ResultadoEnvio]:
    """Envia uma mensagem de texto e devolve um resultado por destinatário.

    Não levanta exceção: falhas viram ``ResultadoEnvio`` com ``ok=False`` para que o
    pipeline de alertas continue mesmo com o canal fora do ar.
    """
    provedor = (provedor or provedor_ativo() or '').strip().lower()
    if not provedor:
        return [_erro('nenhum', '', 'Nenhum provedor de WhatsApp configurado. Rode o agente de configuração.')]
    if provedor not in PROVEDORES:
        return [_erro(provedor, '', f'Provedor desconhecido. Use um de: {", ".join(PROVEDORES)}.')]

    if destinos is None and provedor == 'callmebot':
        destinos = env('CALLMEBOT_PHONE') or env('WHATSAPP_TO') or ''
    numeros = destinatarios(destinos)

    if provedor == 'webhook':
        return [_enviar_webhook(texto, numeros, extra)]
    if not numeros:
        return [_erro(provedor, '', 'Nenhum destinatário definido. Preencha WHATSAPP_TO.')]

    envio = {'meta_cloud': _enviar_meta_cloud, 'evolution': _enviar_evolution, 'callmebot': _enviar_callmebot}[provedor]
    resultados = [envio(texto, numero) for numero in numeros]
    log.info(
        'WhatsApp via %s: %s de %s destinatários com sucesso.',
        provedor,
        sum(1 for r in resultados if r.ok),
        len(resultados),
    )
    return resultados


def verificar_conexao(provedor: str | None = None) -> ResultadoEnvio:
    """Checagem somente leitura das credenciais, sem enviar mensagem a ninguém."""
    provedor = (provedor or provedor_ativo() or '').strip().lower()
    if not provedor:
        return _erro('nenhum', '', 'Nenhum provedor de WhatsApp configurado.')

    if provedor == 'meta_cloud':
        versao = env('WHATSAPP_API_VERSION', VERSAO_API_META_PADRAO) or VERSAO_API_META_PADRAO
        phone_number_id = env('WHATSAPP_PHONE_NUMBER_ID')
        token = env('WHATSAPP_TOKEN')
        if not phone_number_id or not token:
            return _erro('meta_cloud', '', 'WHATSAPP_PHONE_NUMBER_ID e WHATSAPP_TOKEN são obrigatórios.')
        try:
            resposta = requests.get(
                f'https://graph.facebook.com/{versao}/{phone_number_id}',
                params={'fields': 'display_phone_number,verified_name,quality_rating'},
                headers={'Authorization': f'Bearer {token}'},
                timeout=TIMEOUT_SEGUNDOS,
            )
        except Exception as exc:  # noqa: BLE001
            return _erro('meta_cloud', '', f'erro de rede: {exc}')
        dados = _resposta_json(resposta)
        if resposta.ok and isinstance(dados, dict):
            numero = dados.get('display_phone_number', '')
            nome = dados.get('verified_name', '')
            return ResultadoEnvio(True, 'meta_cloud', numero, f'Número {numero} ({nome}) acessível com o token atual.', resposta.status_code, dados)
        return ResultadoEnvio(False, 'meta_cloud', '', f'HTTP {resposta.status_code}', resposta.status_code, dados)

    if provedor == 'evolution':
        base = (env('EVOLUTION_API_URL') or '').rstrip('/')
        chave = env('EVOLUTION_API_KEY')
        instancia = env('EVOLUTION_INSTANCE')
        if not base or not chave or not instancia:
            return _erro('evolution', '', 'EVOLUTION_API_URL, EVOLUTION_API_KEY e EVOLUTION_INSTANCE são obrigatórios.')
        try:
            resposta = requests.get(
                f'{base}/instance/connectionState/{instancia}',
                headers={'apikey': chave},
                timeout=TIMEOUT_SEGUNDOS,
            )
        except Exception as exc:  # noqa: BLE001
            return _erro('evolution', '', f'erro de rede: {exc}')
        dados = _resposta_json(resposta)
        estado = ''
        if isinstance(dados, dict):
            estado = str((dados.get('instance') or {}).get('state') or dados.get('state') or '')
        if resposta.ok and estado == 'open':
            return ResultadoEnvio(True, 'evolution', instancia, f'Instância {instancia} conectada (state=open).', resposta.status_code, dados)
        if resposta.ok:
            return ResultadoEnvio(False, 'evolution', instancia, f'Instância respondeu com state={estado or "desconhecido"}. Leia o QR Code novamente.', resposta.status_code, dados)
        return ResultadoEnvio(False, 'evolution', instancia, f'HTTP {resposta.status_code}', resposta.status_code, dados)

    if provedor == 'callmebot':
        if not env('CALLMEBOT_APIKEY'):
            return _erro('callmebot', '', 'CALLMEBOT_APIKEY é obrigatório.')
        # O CallMeBot não expõe endpoint de verificação; só o envio real confirma a chave.
        return ResultadoEnvio(True, 'callmebot', env('CALLMEBOT_PHONE') or '', 'Credenciais presentes. Confirme com um envio de teste.')

    if not env('WHATSAPP_WEBHOOK_URL'):
        return _erro('webhook', '', 'WHATSAPP_WEBHOOK_URL é obrigatório.')
    return ResultadoEnvio(True, 'webhook', env('WHATSAPP_WEBHOOK_URL') or '', 'URL presente. Confirme com um envio de teste.')


def send_whatsapp(text: str, to: str | list[str] | None = None, payload: dict | None = None) -> bool:
    """Interface booleana usada por ``dispatch_alert``."""
    if not whatsapp_habilitado():
        return False
    resultados = enviar_whatsapp(text, destinos=to, extra=payload)
    return any(resultado.ok for resultado in resultados)
